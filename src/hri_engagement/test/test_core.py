import math
import unittest

from hri_engagement.core import Config, EngagementEngine, is_greeting
from hri_engagement.replay import SCENARIOS, run_scenario
from hri_engagement.trials import summarize


class EngineTest(unittest.TestCase):
    def feed(self, engine, start, end, *, head=True, hand=False, face=True):
        result = None
        for step in range(round((end - start) / .05) + 1):
            now = round(start + step * .05, 6)
            engine.observe(now, healthy=True, face_present=face, facing=head, hand_raised=hand)
            result = engine.update(now)
        return result

    def test_fifteen_scenarios(self):
        for name, expected in SCENARIOS:
            with self.subTest(scenario=name):
                states = run_scenario(name)
                self.assertEqual(any(s['state'] == 'ENGAGED' for s in states), expected)
                self.assertEqual(states[-1]['greeting_count'], int(expected))
                if expected:
                    self.assertIn('ATTENTION', [s['state'] for s in states])

    def test_head_alone_never_greets(self):
        engine = EngagementEngine()
        self.assertEqual(self.feed(engine, 0., 10.)['state'], 'ATTENTION')
        self.assertEqual(engine.greeting_count, 0)

    def test_hand_without_head_never_greets(self):
        engine = EngagementEngine()
        self.assertEqual(self.feed(engine, 0., 4., head=False, hand=True)['state'], 'ATTENTION')
        self.assertEqual(engine.greeting_count, 0)

    def test_camera_timeout_clears_cues(self):
        engine = EngagementEngine()
        self.feed(engine, 0., .5)
        engine.speech(.5, 'Hello robot')
        self.assertEqual(engine.update(1.3)['state'], 'IDLE')
        self.assertFalse(engine.update(1.3)['camera_fresh'])
        self.assertEqual(self.feed(engine, 1.4, 2.)['state'], 'ATTENTION')

    def test_explicit_camera_fault(self):
        engine = EngagementEngine()
        self.feed(engine, 0., 1., hand=True)
        engine.observe(1.1, healthy=False, face_present=False, facing=False, hand_raised=False)
        result = engine.update(1.1)
        self.assertEqual(result['state'], 'IDLE')
        self.assertEqual(result['reason'], 'camera_unavailable')

    def test_camera_gap_clears_speech_even_without_timer_tick(self):
        engine = EngagementEngine()
        self.feed(engine, 0., .5)
        engine.speech(.5, 'Hello robot')
        self.feed(engine, 1.3, 2.)
        self.assertEqual(engine.greeting_count, 0)
        self.assertEqual(engine.state, 'ATTENTION')

    def test_valid_no_face_frames_are_healthy(self):
        engine = EngagementEngine()
        result = self.feed(engine, 0., 2., head=False, face=False)
        self.assertTrue(result['camera_fresh'])
        self.assertEqual(result['state'], 'IDLE')

    def test_attention_expires(self):
        engine = EngagementEngine()
        self.feed(engine, 0., 1.)
        self.assertEqual(self.feed(engine, 1.05, 5., head=False, face=False)['state'], 'IDLE')

    def test_engaged_hold_disengage_and_cooldown(self):
        engine = EngagementEngine()
        self.feed(engine, 0., 1., hand=True)
        self.assertEqual(engine.state, 'ENGAGED')
        self.feed(engine, 1.05, 2., head=False, face=False)
        self.assertEqual(engine.state, 'ENGAGED')
        self.feed(engine, 2.05, 3.1, head=False, face=False)
        self.assertEqual(engine.state, 'IDLE')
        self.feed(engine, 3.15, 4.5, hand=True)
        self.assertEqual(engine.greeting_count, 1)
        self.feed(engine, 4.55, 7., hand=True)
        self.assertEqual(engine.greeting_count, 2)

    def test_same_person_not_greeted_repeatedly(self):
        engine = EngagementEngine()
        self.feed(engine, 0., 15., hand=True)
        self.assertEqual(engine.greeting_count, 1)

    def test_expired_speech_cannot_trigger(self):
        engine = EngagementEngine()
        self.feed(engine, 0., .2, head=False)
        engine.speech(.2, 'hello robot')
        self.feed(engine, .25, 3., head=False)
        self.feed(engine, 3.05, 4.)
        self.assertEqual(engine.greeting_count, 0)

    def test_low_confidence_and_non_greeting(self):
        engine = EngagementEngine()
        self.assertFalse(engine.speech(0., 'hello robot', .4))
        self.assertFalse(engine.speech(0., 'please do not hello robot'))
        self.feed(engine, 0., 1.)
        self.assertEqual(engine.greeting_count, 0)

    def test_greeting_normalization(self):
        for text in ('Hello robot!', 'EXCUSE ME', 'Xin chào robot', 'Xin chào'):
            self.assertTrue(is_greeting(text))
        for text in ('shelloworld', 'not hello', '', None, 3, 'I heard hello robot on TV'):
            self.assertFalse(is_greeting(text))

    def test_invalid_payload_and_config(self):
        engine = EngagementEngine()
        with self.assertRaises(ValueError):
            engine.observe(0., healthy=True, face_present=True, facing='false', hand_raised=False)
        for value in (math.nan, math.inf, -1., True, '1'):
            with self.assertRaises(ValueError):
                engine.speech(0., 'hello robot', value)
        for options in ({'window': .1}, {'camera_timeout': math.nan}, {'stable_ratio': .4},
                        {'min_frames': 1}, {'min_frames': 4.5}, {'speech_confidence': math.nan}):
            with self.assertRaises(ValueError):
                Config(**options)

    def test_recovery_needs_new_multiframe_evidence(self):
        engine = EngagementEngine()
        self.feed(engine, 0., .5)
        engine.update(2.)
        engine.observe(2.05, healthy=True, face_present=True, facing=True, hand_raised=True)
        self.assertEqual(engine.update(2.05)['state'], 'IDLE')

    def test_metrics_use_negative_trials_as_denominator(self):
        rows = [dict(camera_valid=valid, expected_engaged=expected, observed_engaged=observed)
                for valid, expected, observed in ((1, 1, 1), (1, 1, 0), (1, 0, 1),
                                                  (1, 0, 0), (1, 0, 0), (0, 0, 0))]
        result = summarize(rows)
        self.assertAlmostEqual(result['false_greeting_rate'], 1 / 3)
        self.assertEqual(result['invalid'], 1)
        self.assertIsNone(summarize([])['accuracy'])


if __name__ == '__main__':
    unittest.main()
