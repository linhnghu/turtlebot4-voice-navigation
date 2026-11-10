"""Geodesic Voronoi regions over known free cells; no flood across walls."""
import argparse
import hashlib
import heapq
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import yaml


class GridMap:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.meta = yaml.safe_load(self.path.read_text())
        if self.meta.get('mode', 'trinary') != 'trinary':
            raise ValueError('Only trinary map YAML is supported')
        self.resolution = float(self.meta['resolution'])
        self.origin = [float(v) for v in self.meta['origin']]
        if (len(self.origin) != 3 or self.resolution <= 0 or
                not all(math.isfinite(v) for v in [self.resolution, *self.origin])):
            raise ValueError('Invalid map resolution/origin')
        self.image = np.asarray(Image.open(self.path.parent / self.meta['image']).convert('L'))
        self.height, self.width = self.image.shape
        occ = self.image.astype(float) / 255
        if not self.meta.get('negate', 0):
            occ = 1 - occ
        free_thresh = float(self.meta['free_thresh'])
        occupied_thresh = float(self.meta['occupied_thresh'])
        if not 0 <= free_thresh < occupied_thresh <= 1:
            raise ValueError('Invalid occupancy thresholds')
        self.free = occ < free_thresh
        self.occupied = occ > occupied_thresh
        # Padding makes the area outside the image an obstacle too.
        padded = np.pad(self.free.astype('uint8'), 1)
        self.clearance = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        # Conservative cell-edge distance rather than obstacle-center distance.
        self.clearance = np.maximum(0, self.clearance - math.sqrt(.5)) * self.resolution
        self.fingerprint = hashlib.sha256(
            self.image.tobytes() + yaml.safe_dump(self.meta, sort_keys=True).encode()).hexdigest()

    def pixel_to_world(self, u, v):
        x = (u + .5) * self.resolution
        y = (self.height - v - .5) * self.resolution
        c, s = math.cos(self.origin[2]), math.sin(self.origin[2])
        return (self.origin[0] + c*x - s*y, self.origin[1] + s*x + c*y)

    def world_to_pixel(self, x, y):
        x, y = x - self.origin[0], y - self.origin[1]
        c, s = math.cos(self.origin[2]), math.sin(self.origin[2])
        return (math.floor((c*x + s*y) / self.resolution),
                self.height - 1 - math.floor((-s*x + c*y) / self.resolution))

    def safe(self, x, y, clearance):
        u, v = self.world_to_pixel(x, y)
        return (0 <= u < self.width and 0 <= v < self.height and
                self.free[v, u] and self.clearance[v, u] >= clearance)


def partition(free, seeds):
    """Four-connected shortest path in pixels; unreachable components stay 0."""
    h, w = free.shape
    labels = np.zeros((h, w), dtype=np.int32)
    distance = np.full((h, w), np.inf)
    heap = []
    for index, (u, v) in enumerate(seeds, 1):
        if not (0 <= u < w and 0 <= v < h and free[v, u]):
            raise ValueError('Region seed must be in a known free cell')
        if labels[v, u]:
            raise ValueError('Region seeds must occupy distinct cells')
        distance[v, u], labels[v, u] = 0, index
        heapq.heappush(heap, (0, index, v, u))
    while heap:
        d, label, v, u = heapq.heappop(heap)
        if d != distance[v, u] or label != labels[v, u]:
            continue
        for nu, nv in ((u-1, v), (u+1, v), (u, v-1), (u, v+1)):
            if 0 <= nu < w and 0 <= nv < h and free[nv, nu] and d+1 < distance[nv, nu]:
                distance[nv, nu], labels[nv, nu] = d+1, label
                heapq.heappush(heap, (d+1, label, nv, nu))
    return labels


def segment(map_file, seed_file, output, clearance=.30):
    if not math.isfinite(clearance) or clearance <= 0:
        raise ValueError('Clearance must be positive')
    grid = GridMap(map_file)
    config = yaml.safe_load(Path(seed_file).read_text())
    regions = config['regions']
    if len(regions) < 3 or len({r['id'] for r in regions}) != len(regions):
        raise ValueError('Provide at least three distinct region IDs')
    seeds = []
    for r in regions:
        x, y = map(float, r['seed'])
        if not grid.safe(x, y, clearance):
            raise ValueError(f"Unsafe seed for {r['id']}: {(x, y)}; choose known free space with {clearance}m clearance")
        seeds.append(grid.world_to_pixel(x, y))
    labels = partition(grid.free, seeds)
    # Every goal must belong to the same traversable component.
    _, components = cv2.connectedComponents(grid.free.astype('uint8'), connectivity=4)
    if len({components[v, u] for u, v in seeds}) != 1:
        raise ValueError('Region goals are in disconnected free-space components')
    rgb = np.repeat(grid.image[:, :, None], 3, axis=2).copy()
    for index, r in enumerate(regions, 1):
        mask = labels == index
        rgb[mask] = np.array(r['color'], dtype='uint8')
        u, v = seeds[index-1]
        # Keep the selected seed as goal: a geometric centroid may lie in a wall.
        r['goal'] = dict(x=float(r['seed'][0]), y=float(r['seed'][1]), yaw=float(r.get('yaw', 0)))
        r['label'] = index
        r['area_m2'] = round(int(mask.sum()) * grid.resolution**2, 3)
        r['clearance_m'] = round(float(grid.clearance[v, u]), 3)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    np.save(output / 'labels.npy', labels)
    Image.fromarray(rgb).save(output / 'regions.png')
    preview = Image.fromarray(rgb).resize((808, 808), Image.NEAREST)
    canvas = Image.new('RGB', (1100, 850), '#142130')
    canvas.paste(preview, (12, 30))
    draw = ImageDraw.Draw(canvas)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 17)
    large = ImageFont.truetype(font_path, 24)
    draw.text((12, 4), 'BÀI 7 · PHÂN VÙNG BẢN ĐỒ', font=font, fill='white')
    for index, r in enumerate(regions):
        u, v = seeds[index]
        px, py = 12 + (u+.5)*808/grid.width, 30 + (v+.5)*808/grid.height
        draw.ellipse((px-14, py-14, px+14, py+14), fill='#142130', outline='white', width=2)
        draw.text((px-8, py-14), r['id'], font=large, fill='white')
        y = 60 + 145*index
        draw.rectangle((840, y, 860, y+20), fill=tuple(r['color']))
        draw.text((870, y-3), r['id'], font=large, fill='white')
    draw.text((840, 550), 'Xám: chưa biết\nĐen: vật cản', font=font, fill='white', spacing=9)
    canvas.save(output / 'segmented_map.png')
    data = dict(version=1, frame_id='map', map_yaml=str(grid.path),
                map_sha256=grid.fingerprint, method='seeded_geodesic_voronoi_4_connected',
                labels='labels.npy', overlay='regions.png', minimum_clearance_m=clearance,
                unassigned_free_cells=int(np.sum(grid.free & (labels == 0))), regions=regions)
    (output / 'regions.yaml').write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return data


def load_regions(path, map_file=None):
    path = Path(path).expanduser().resolve()
    config = yaml.safe_load(path.read_text())
    grid = GridMap(map_file or config['map_yaml'])
    if config['frame_id'] != 'map' or config['map_sha256'] != grid.fingerprint:
        raise ValueError('Map changed: regenerate segmentation for this map')
    labels = np.load(path.parent / config['labels'], allow_pickle=False)
    if labels.shape != grid.image.shape:
        raise ValueError('Segmentation dimensions differ from map')
    for r in config['regions']:
        g = r['goal']
        if not all(math.isfinite(float(g[k])) for k in ('x', 'y', 'yaw')):
            raise ValueError('Non-finite region goal')
        if not grid.safe(g['x'], g['y'], config['minimum_clearance_m']):
            raise ValueError(f"Unsafe goal in region {r['id']}")
        u, v = grid.world_to_pixel(g['x'], g['y'])
        if labels[v, u] != r['label']:
            raise ValueError('Goal is not in its labelled region')
    return config, grid, labels


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map', required=True)
    p.add_argument('--seeds', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--clearance', type=float, default=.30)
    args = p.parse_args()
    config = segment(args.map, args.seeds, args.output, args.clearance)
    for r in config['regions']:
        print(r['id'], r['name'], r['goal'], 'clearance:', r['clearance_m'])


if __name__ == '__main__':
    main()
