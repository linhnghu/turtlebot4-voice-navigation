"""Safety and command protocol regression tests, independent of ROS/webcam."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gesture_core import Controller, WaveDetector


class ControllerTests(unittest.TestCase):
    def stable(self, controller, label, now):
        controller.observe(label, now)
        controller.observe(label, now+0.31)
        return now+0.31

    def start(self, label='Pointing_Up'):
        c = Controller()
        self.stable(c, label, 0)
        self.stable(c, 'Thumb_Up', 0.4)
        return c

    def test_selection_does_not_move(self):
        for label in ('Wave', 'Pointing_Up', 'Victory', 'Thumb_Up'):
            c = Controller()
            t = self.stable(c, label, 0)
            self.assertEqual(c.tick(t, (0,0,0)), (0,0))

    def test_noise_does_not_select(self):
        c = Controller()
        for i in range(20):
            c.observe('Pointing_Up' if i%2 else 'Victory', i*0.05)
        self.assertIsNone(c.selected)

    def test_confirmation_consumes_selection_and_held_thumb_does_not_repeat(self):
        c = self.start()
        self.assertEqual(len(c.segments), 8)
        self.assertIsNone(c.selected)
        c.stop('COMPLETE')
        self.stable(c, 'Thumb_Up', 1)
        self.assertIsNone(c.active)

    def test_open_palm_stop_bypasses_debounce(self):
        c = self.start()
        c.observe('Open_Palm', 0.72)
        self.assertEqual(c.tick(0.72, (0,0,0)), (0,0))
        self.assertIsNone(c.active)

    def test_fist_clears_selection_and_running_behavior(self):
        c = self.start()
        c.observe('Closed_Fist', 0.72)
        self.assertIsNone(c.active)
        self.assertIsNone(c.selected)

    def test_signal_timeout_and_no_auto_resume(self):
        c = self.start()
        self.assertNotEqual(c.tick(0.72, (0,0,0)), (0,0))
        self.assertEqual(c.tick(1.6, (0,0,0)), (0,0))
        self.stable(c, 'Thumb_Up', 2)
        self.assertIsNone(c.active)

    def test_lowering_hand_or_unknown_gesture_keeps_confirmed_motion_running(self):
        for label in ('No_Hand', 'Unknown', 'Multiple_Hands'):
            c = self.start()
            for i in range(30):
                now = 0.75+i*.2
                c.observe(label, now)
                self.assertEqual(c.tick(now, (0,0,0)), (0.10,0))
            self.assertEqual(c.active, 'back_and_forth')

    def test_unconfirmed_selection_expires_when_hand_lowered(self):
        c = Controller()
        self.stable(c, 'Victory', 0)
        c.observe('No_Hand', 1.2)
        self.assertEqual(c.tick(1.2, (0,0,0)), (0,0))
        self.assertIsNone(c.selected)
        self.stable(c, 'Thumb_Up', 1.3)
        self.assertIsNone(c.active)

    def test_no_hand_does_not_start_motion_or_repeat_completed_action(self):
        c = Controller()
        c.observe('No_Hand', 1)
        self.assertEqual(c.tick(1, (0,0,0)), (0,0))
        c = self.start()
        c.stop('COMPLETE')
        c.observe('No_Hand', 2)
        self.assertEqual(c.tick(2, (0,0,0)), (0,0))
        self.assertEqual(c.status, 'COMPLETE')

    def test_sensor_failure_discards_command(self):
        c = self.start()
        self.assertEqual(c.tick(0.72, (0,0,0), False), (0,0))
        self.assertIsNone(c.active)
        self.assertIsNone(c.selected)

    def test_four_complete_forward_backward_cycles(self):
        c = self.start()
        now, x = 0.72, 0.0
        self.assertEqual(c.tick(now, (x,0,0)), (0.10,0))
        for index in range(8):
            now += 0.1
            c.observe('No_Hand', now)
            c.tick(now, (x,0,0))
            x += 0.13 if index%2 == 0 else -0.13
            now += 0.1
            c.observe('No_Hand', now)
            self.assertEqual(c.tick(now, (x,0,0)), (0,0))
        self.assertIsNone(c.active)
        self.assertTrue(c.status.startswith('COMPLETE'))

    def test_circle_uses_unwrapped_odometry(self):
        c = self.start('Victory')
        for i in range(66):
            t = 0.72+i*0.05
            c.observe('No_Hand', t)
            yaw = math.atan2(math.sin(i*0.1), math.cos(i*0.1))
            c.tick(t, (0,0,yaw))
        self.assertIsNone(c.active)
        self.assertTrue(c.status.startswith('COMPLETE'))

    def test_opposite_motion_does_not_complete_segment(self):
        c = self.start()
        c.tick(0.72, (0,0,0))
        c.tick(0.73, (-0.4,0,0))
        self.assertEqual(len(c.segments), 8)

    def test_greeting_requires_confirmation(self):
        c = self.start('Wave')
        self.assertEqual(len(c.segments), 3)
        self.assertEqual(c.tick(0.72, (0,0,0)), (0,0.5))


class WaveTests(unittest.TestCase):
    def test_stationary_palm_is_stop(self):
        w = WaveDetector()
        for i in range(40):
            self.assertEqual(w.update(i*.05, 'Open_Palm', .5, .1), 'Open_Palm')

    def test_jitter_is_not_wave(self):
        w = WaveDetector()
        for i in range(30):
            self.assertEqual(w.update(i*.05, 'Open_Palm', .5+(.01 if i%2 else 0), .1), 'Open_Palm')

    def test_three_alternating_strokes_are_wave(self):
        w = WaveDetector()
        labels = [w.update(i*.15, 'Open_Palm', x, .1)
                  for i,x in enumerate((.5,.62,.48,.63))]
        self.assertEqual(labels[-1], 'Wave')
        self.assertEqual(w.update(.5, 'Thumb_Up'), 'Thumb_Up')

    def test_old_movements_and_nonpalm_reset_wave(self):
        w = WaveDetector()
        for i,x in enumerate((.5,.62,.48,.63)):
            self.assertEqual(w.update(i*2, 'Open_Palm', x,.1), 'Open_Palm')
        w.update(6.1,'No_Hand')
        self.assertEqual(w.update(6.2,'Open_Palm',.5,.1), 'Open_Palm')


if __name__ == '__main__':
    unittest.main()
