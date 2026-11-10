import math
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import yaml

from turtlebot4_voice_nav.commands import CommandError, CommandParser
from turtlebot4_voice_nav.segmentation import GridMap, load_regions, partition, segment


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def parser():
    cfg = yaml.safe_load((ROOT / 'src/turtlebot4_voice_nav/config/seeds.yaml').read_text())
    return CommandParser(cfg['regions'])


@pytest.mark.parametrize('text,route', [
    ('Đi đến khu vực A.', ('A',)),
    ('Di chuyển từ khu vực A đến khu vực B.', ('A', 'B')),
    ('Đi đến phòng thí nghiệm.', ('B',)),
    ('Robot hãy đi đến hành lang!', ('C',)),
    ('di chuyen tu phong hoc toi hanh lang', ('A', 'C')),
    ('đi đến khu vực bê', ('B',)),
    ('đi đến khu vực xê', ('C',)),
    ('đi từ B tới A', ('B', 'A')),
])
def test_vietnamese_commands(parser, text, route):
    assert parser.parse(text).route == route


@pytest.mark.parametrize('text', ['Đi đến khu vực Z', 'Đi từ A đến Z',
                                       'Đi từ Z đến B', 'Đi đến phòng bếp',
                                       'Đi đến A rồi đến C', 'Đi đến A hoặc B'])
def test_unknown_region_does_not_fallback(parser, text):
    with pytest.raises(CommandError) as e:
        parser.parse(text)
    assert e.value.code == 'UNKNOWN_REGION'


@pytest.mark.parametrize('text', ['không đi đến A', 'đừng đi đến B', 'A', '',
                                       'Đi đến A và dừng', 'đến phòng học'])
def test_unsupported_or_negated_command(parser, text):
    with pytest.raises(CommandError):
        parser.parse(text)


@pytest.mark.parametrize('text', ['dừng lại', 'Hủy điều hướng', 'stop'])
def test_stop(parser, text):
    assert parser.parse(text).kind == 'stop'


def map_fixture(tmp_path, image, **overrides):
    Image.fromarray(np.array(image, dtype='uint8')).save(tmp_path / 'test.pgm')
    config = dict(image='test.pgm', mode='trinary', resolution=.2,
                  origin=[-2., 3., math.pi/2], negate=0,
                  occupied_thresh=.65, free_thresh=.196)
    config.update(overrides)
    p = tmp_path / 'test.yaml'
    p.write_text(yaml.safe_dump(config))
    return p


def test_pixel_world_round_trip_with_rotated_origin(tmp_path):
    grid = GridMap(map_fixture(tmp_path, np.full((9, 13), 254)))
    for u, v in [(0, 0), (12, 8), (4, 6)]:
        assert grid.world_to_pixel(*grid.pixel_to_world(u, v)) == (u, v)
    x, y = grid.pixel_to_world(0, 8)
    assert x == pytest.approx(-2.1)
    assert y == pytest.approx(3.1)


def test_unknown_is_never_free_and_negate_is_respected(tmp_path):
    path = map_fixture(tmp_path, [[0, 205, 254]])
    grid = GridMap(path)
    assert grid.free.tolist() == [[False, False, True]]
    assert grid.occupied.tolist() == [[True, False, False]]
    config = yaml.safe_load(path.read_text())
    config['negate'] = 1
    path.write_text(yaml.safe_dump(config))
    grid = GridMap(path)
    assert grid.free.tolist() == [[True, False, False]]


def test_wall_does_not_leak_and_unseeded_component_stays_unassigned():
    free = np.ones((8, 10), dtype=bool)
    free[:, 4] = False
    labels = partition(free, [(1, 2), (6, 2)])
    assert np.all(labels[:, :4] == 1)
    assert np.all(labels[:, 4] == 0)
    assert np.all(labels[:, 5:] == 2)
    labels = partition(free, [(1, 2)])
    assert np.all(labels[:, 5:] == 0)


def test_partition_follows_doorway_instead_of_euclidean_distance():
    free = np.ones((9, 9), dtype=bool)
    free[:8, 4] = False
    labels = partition(free, [(3, 0), (7, 6)])
    # (5,0) is geometrically close to left seed, but the wall forces a detour.
    assert labels[0, 5] == 2


def test_unknown_space_and_image_boundary_reduce_clearance(tmp_path):
    im = np.full((25, 25), 254, dtype='uint8')
    im[:, 12] = 205
    grid = GridMap(map_fixture(tmp_path, im))
    assert not grid.safe(*grid.pixel_to_world(12, 10), .01)
    assert not grid.safe(*grid.pixel_to_world(11, 10), .30)
    assert not grid.safe(*grid.pixel_to_world(0, 10), .30)
    assert grid.safe(*grid.pixel_to_world(5, 10), .30)


def test_saved_maze_has_three_safe_goals_and_fingerprint(tmp_path):
    result = segment(ROOT / 'maps/map.yaml', ROOT / 'src/turtlebot4_voice_nav/config/seeds.yaml', tmp_path)
    cfg, grid, labels = load_regions(tmp_path / 'regions.yaml')
    assert len(result['regions']) == 3
    assert set(np.unique(labels)) == {0, 1, 2, 3}
    assert np.all(labels[~grid.free] == 0)
    for r in cfg['regions']:
        assert r['area_m2'] > 5
        assert r['clearance_m'] >= .30
    cfg['map_sha256'] = 'changed'
    (tmp_path / 'regions.yaml').write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match='Map changed'):
        load_regions(tmp_path / 'regions.yaml')


def test_unsafe_seed_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='Unsafe seed'):
        segment(ROOT / 'maps/map.yaml', ROOT / 'src/turtlebot4_voice_nav/config/seeds.yaml', tmp_path, 20)
