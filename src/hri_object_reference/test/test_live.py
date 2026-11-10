from types import SimpleNamespace
import unittest

from hri_object_reference.live_vision import PointingFilter, SceneFilter, index_ray
from hri_object_reference.perception import detect_objects, make_table
from hri_object_reference.voice_core import confirmation_color, transcript
from hri_object_reference.core import parse_speech


def hand(open_palm=False):
    points = [SimpleNamespace(x=.5, y=.85) for _ in range(21)]
    for index, y in ((0, .9), (5, .7), (6, .6), (7, .52), (8, .45)):
        points[index].y = y
    for tip, pip in ((12, 10), (16, 14), (20, 18)):
        points[pip].y = .65
        points[tip].y = .4 if open_palm else .8
    return points


class LiveInputTest(unittest.TestCase):
    def test_index_ray_is_tip_toward_extended_index(self):
        ray = index_ray(hand())
        self.assertIsNotNone(ray)
        self.assertEqual(ray['origin'], [.5, .45])
        self.assertEqual(ray['direction'], [0., -1.])

    def test_open_palm_is_not_a_point(self):
        self.assertIsNone(index_ray(hand(True)))

    def test_multiframe_pointing_and_no_hand_reset(self):
        tracker = PointingFilter()
        self.assertIsNone(tracker.observe(0., [hand()]))
        self.assertIsNone(tracker.observe(.1, [hand()]))
        self.assertIsNotNone(tracker.observe(.21, [hand()]))
        self.assertIsNone(tracker.observe(.22, []))
        self.assertIsNone(tracker.observe(.3, [hand()]))

    def test_two_hands_are_ambiguous(self):
        self.assertIsNone(PointingFilter().observe(0., [hand(), hand()]))

    def test_pointing_gap_restarts_filter(self):
        tracker = PointingFilter()
        for now in (0., .1, .21):
            tracker.observe(now, [hand()])
        self.assertIsNone(tracker.observe(1., [hand()]))

    def test_measured_scene_locks_after_three_frames(self):
        tracker = SceneFilter()
        objects = detect_objects(make_table())
        self.assertIsNone(tracker.observe(0., objects))
        self.assertIsNone(tracker.observe(.1, objects))
        self.assertEqual(tracker.observe(.2, objects), objects)

    def test_small_jitter_does_not_change_scene_signature(self):
        tracker = SceneFilter()
        objects = detect_objects(make_table())
        for now in (0., .1, .2):
            tracker.observe(now, objects)
        jittered = [dict(o, x=o['x'] + .003) for o in objects]
        self.assertEqual(tracker.observe(.3, jittered), objects)

    def test_moved_object_requires_new_stability(self):
        tracker = SceneFilter()
        objects = detect_objects(make_table())
        for now in (0., .1, .2):
            tracker.observe(now, objects)
        moved = [dict(o, x=o['x'] + .06) for o in objects]
        self.assertIsNone(tracker.observe(.3, moved))
        self.assertIsNone(tracker.observe(.4, moved))
        self.assertEqual(tracker.observe(.5, moved), moved)

    def test_missing_or_duplicate_color_is_unknown(self):
        objects = detect_objects(make_table())
        for detections in (objects[:2], objects + [dict(objects[0], id='red_2')]):
            self.assertIsNone(SceneFilter().observe(0., detections))

    def test_scene_gap_and_occlusion_do_not_keep_old_lock(self):
        tracker = SceneFilter()
        objects = detect_objects(make_table())
        for now in (0., .1, .2):
            tracker.observe(now, objects)
        self.assertIsNone(tracker.observe(1., objects))
        self.assertIsNone(tracker.observe(1.1, []))

    def test_vietnamese_commands_and_color_confirmation(self):
        for text in ('Gắp vật này', 'Lấy vật màu đỏ', 'màu vàng', 'màu xanh dương'):
            self.assertTrue(parse_speech(text).valid, text)
        for text, color in (('xác nhận màu đỏ', 'red'), ('màu xanh dương', 'blue'), ('màu vàng', 'yellow')):
            self.assertEqual(confirmation_color(text), color)
        for text in ('không lấy màu đỏ', 'xanh', 'đỏ hoặc vàng', 'lấy vật màu đỏ'):
            self.assertFalse(confirmation_color(text))

    def test_transcript_confidence(self):
        self.assertFalse(transcript(dict(text='lấy vật này', result=[dict(conf=.3)]))['accepted'])
        self.assertTrue(transcript(dict(text='lấy vật này', result=[dict(conf=.9)]))['accepted'])
        self.assertFalse(transcript(dict(text='', result=[]))['accepted'])


if __name__ == '__main__':
    unittest.main()
