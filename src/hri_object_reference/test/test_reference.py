import math
import unittest

from hri_object_reference.core import Intent, Object, Ray, ReferenceEngine, parse_speech, resolve

OBJECTS = [Object('red_1', 'red', .22, .35, .055), Object('blue_1', 'blue', .5, .35, .055),
           Object('yellow_1', 'yellow', .78, .35, .055)]
SCENE = dict(objects=[vars(o) for o in OBJECTS])
BLUE = dict(origin=[.5, .9], direction=[0., -1.])


def bisector(a, b):
    vectors = [(o.x - .5, o.y - .9) for o in (a, b)]
    return dict(origin=[.5, .9], direction=[sum(v[i] / math.hypot(*v) for v in vectors) for i in range(2)])


class ResolveTest(unittest.TestCase):
    def test_correct_point(self):
        result = resolve(OBJECTS, Ray.decode(BLUE), parse_speech('Pick up this object'))
        self.assertEqual(result.state, 'SELECTED')
        self.assertEqual(result.target, 'blue_1')

    def test_point_between_two_objects_asks(self):
        result = resolve(OBJECTS, Ray.decode(bisector(OBJECTS[0], OBJECTS[1])), Intent(True))
        self.assertEqual(result.reason, 'ambiguous_pointing')
        self.assertEqual(set(result.candidates), {'red_1', 'blue_1'})
        self.assertFalse(result.target)

    def test_spoken_red_pointed_blue_is_conflict(self):
        result = resolve(OBJECTS, Ray.decode(BLUE), parse_speech('Pick up the red object'))
        self.assertEqual(result.reason, 'speech_pointing_conflict')
        self.assertEqual(set(result.candidates), {'red_1', 'blue_1'})
        self.assertFalse(result.target)

    def test_color_alone_still_needs_pointing(self):
        result = resolve(OBJECTS, None, parse_speech('red'))
        self.assertEqual(result.reason, 'need_pointing')

    def test_point_away_does_not_select_behind(self):
        ray = Ray.decode(dict(origin=[.5, .9], direction=[0., 1.]))
        self.assertEqual(resolve(OBJECTS, ray, Intent(True)).reason, 'pointing_miss')

    def test_empty_scene(self):
        self.assertEqual(resolve([], Ray.decode(BLUE), Intent(True)).reason, 'no_objects')

    def test_object_with_missing_color(self):
        self.assertEqual(resolve(OBJECTS[:1], Ray.decode(BLUE), Intent(True, 'blue')).reason, 'color_not_found')

    def test_valid_english_and_vietnamese(self):
        for text in ('Pick up this object', 'Pick up that one', 'Please select the blue block',
                     'Gắp vật này', 'Gắp vật đó', 'Chọn vật màu đỏ', 'Lấy vật màu vàng', 'blue'):
            with self.subTest(text=text):
                self.assertTrue(parse_speech(text).valid)
        self.assertEqual(parse_speech('Chọn vật màu ĐỎ').color, 'red')
        self.assertEqual(parse_speech('Gắp vật đó').color, '')

    def test_unrelated_negated_unknown_and_multiple_colors(self):
        for text in ('Do not pick up this object', 'Đừng gắp vật này', 'Pick up green object',
                     'red or blue', 'red blue', 'I heard someone say pick up this object',
                     'drop the red object', 'xanh', ''):
            with self.subTest(text=text):
                self.assertFalse(parse_speech(text).valid)

    def test_invalid_geometry(self):
        for data in (dict(origin=[0, 0], direction=[0, 0]), dict(origin=[2, .5], direction=[1, 0]),
                     dict(origin=[0, 0], direction=[math.nan, 1]),
                     dict(origin=[True, 0], direction=[1, 0]), {}, None):
            with self.assertRaises(ValueError):
                Ray.decode(data)

    def test_overlapping_ray_bearings_ask(self):
        aligned = [Object('a', 'red', .5, .3, .04), Object('b', 'blue', .5, .5, .04)]
        self.assertEqual(resolve(aligned, Ray.decode(BLUE), Intent(True)).state, 'CLARIFY')


class EngineTest(unittest.TestCase):
    def engine(self):
        engine = ReferenceEngine()
        engine.scene(0., SCENE)
        return engine

    def test_point_then_speech(self):
        engine = self.engine()
        engine.point(.1, BLUE)
        engine.request(.2, 'Pick up this object')
        self.assertEqual(engine.snapshot()['target'], 'blue_1')

    def test_speech_then_point(self):
        engine = self.engine()
        engine.request(.1, 'Pick up this object')
        self.assertEqual(engine.snapshot()['reason'], 'need_pointing')
        engine.point(.2, BLUE)
        self.assertEqual(engine.snapshot()['target'], 'blue_1')

    def test_confirmation_selects_once(self):
        engine = self.engine()
        engine.request(.1, 'red', BLUE)
        request = engine.request_id
        self.assertFalse(engine.confirm(.2, request - 1, 'blue_1'))
        self.assertFalse(engine.confirm(.2, request, 'yellow_1'))
        self.assertTrue(engine.confirm(.2, request, 'blue_1'))
        self.assertFalse(engine.confirm(.3, request, 'blue_1'))
        self.assertEqual(engine.selection_id, 1)
        self.assertEqual(engine.snapshot()['reason'], 'explicit_confirmation')

    def test_scene_change_invalidates_confirmation(self):
        engine = self.engine()
        engine.request(.1, 'red', BLUE)
        request = engine.request_id
        changed = dict(objects=[dict(vars(o), x=o.x + .01) for o in OBJECTS])
        engine.scene(.2, changed)
        self.assertFalse(engine.confirm(.3, request, 'blue_1'))
        self.assertEqual(engine.snapshot()['reason'], 'scene_changed')

    def test_scene_timeout_clears_selection(self):
        engine = self.engine()
        engine.request(.1, 'blue', BLUE)
        self.assertEqual(engine.update(1.2)['reason'], 'scene_unavailable')
        self.assertFalse(engine.snapshot()['target'])

    def test_expired_point_does_not_pair(self):
        engine = self.engine()
        engine.point(.1, BLUE)
        for now in (.8, 1.6, 2.4, 3.2):
            engine.scene(now, SCENE)
        engine.scene(3.5, SCENE)
        engine.request(3.5, 'blue')
        self.assertEqual(engine.snapshot()['reason'], 'need_pointing')

    def test_expired_speech_does_not_pair_even_without_timer(self):
        engine = self.engine()
        engine.request(.1, 'blue')
        for now in (.8, 1.6, 2.4, 3.2):
            engine.scene(now, SCENE)
        engine.scene(3.5, SCENE)
        engine.point(3.5, BLUE)
        self.assertEqual(engine.selection_id, 0)
        self.assertEqual(engine.snapshot()['reason'], 'request_expired')

    def test_confirmation_timeout(self):
        engine = self.engine()
        engine.request(.1, 'red', BLUE)
        for now in range(1, 16):
            engine.scene(float(now), SCENE)
        engine.scene(16., SCENE)
        self.assertFalse(engine.confirm(16., engine.request_id, 'blue_1'))
        self.assertEqual(engine.update(16.)['reason'], 'request_expired')

    def test_scene_gap_invalidates_confirmation_without_timer(self):
        engine = self.engine()
        engine.request(.1, 'red', BLUE)
        request_id = engine.request_id
        engine.scene(2., SCENE)
        self.assertFalse(engine.confirm(2.1, request_id, 'blue_1'))
        self.assertEqual(engine.snapshot()['reason'], 'scene_restored')

    def test_unchanged_scene_and_point_do_not_repeat_selection(self):
        engine = self.engine()
        engine.request(.1, 'blue', BLUE)
        for i in range(2, 20):
            engine.scene(i / 10, SCENE)
            engine.point(i / 10, BLUE)
        self.assertEqual(engine.selection_id, 1)

    def test_consumed_ray_requires_fresh_gesture_for_new_command(self):
        engine = self.engine()
        engine.request(.1, 'blue', BLUE)
        engine.request(.2, 'blue')
        self.assertEqual(engine.snapshot()['reason'], 'need_pointing')

    def test_invalid_speech_cannot_be_confirmed(self):
        engine = self.engine()
        engine.request(.1, 'Do not pick up this object', BLUE)
        self.assertFalse(engine.confirm(.2, engine.request_id, 'blue_1'))

    def test_scene_validation(self):
        engine = self.engine()
        for scene in ({}, dict(objects=[vars(OBJECTS[0])] * 2),
                      dict(objects=[dict(vars(OBJECTS[0]), x=math.nan)]),
                      dict(objects=[dict(vars(OBJECTS[0]), color='green')])):
            with self.assertRaises(ValueError):
                engine.scene(.1, scene)

    def test_config_validation(self):
        for options in ({'cue_ttl': -1}, {'scene_ttl': math.nan}, {'cone_degrees': 90}, {'cue_ttl': True}):
            with self.assertRaises(ValueError):
                ReferenceEngine(**options)


if __name__ == '__main__':
    unittest.main()
