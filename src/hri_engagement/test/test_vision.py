from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from hri_engagement.vision import FACE_INDICES, FACE_MODEL, head_pose, raised_open_hand


class VisionTest(unittest.TestCase):
    def test_head_pose_from_projected_face(self):
        camera = np.array([[640., 0., 320.], [0., 640., 240.], [0., 0., 1.]])
        for yaw in (0., 15., -30.):
            rotation = np.array([0., np.radians(yaw), 0.])
            projected, _ = cv2.projectPoints(FACE_MODEL, rotation, np.array([0., 0., 1800.]),
                                             camera, np.zeros(4))
            face = [SimpleNamespace(x=.5, y=.5) for _ in range(468)]
            for index, (x, y) in zip(FACE_INDICES, projected.reshape(-1, 2)):
                face[index] = SimpleNamespace(x=x / 640., y=y / 480.)
            pose = head_pose(face, 640, 480)
            self.assertIsNotNone(pose)
            self.assertAlmostEqual(pose[0], 0., places=4)
            self.assertAlmostEqual(pose[1], yaw, places=4)

    def test_tiny_face_is_rejected(self):
        self.assertIsNone(head_pose([SimpleNamespace(x=.5, y=.5)] * 468, 640, 480))

    def test_raised_open_hand_and_lowered_hand(self):
        face = [SimpleNamespace(x=.5, y=.4) for _ in range(468)]
        face[33].x, face[263].x, face[152].y, face[10].y = .4, .6, .7, .2
        hand = [SimpleNamespace(x=.65, y=.5) for _ in range(21)]
        hand[5].x, hand[17].x = .60, .70
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
            hand[pip].y, hand[tip].y = .4, .25
        self.assertTrue(raised_open_hand(hand, face))
        for point in hand:
            point.y += .5
        self.assertFalse(raised_open_hand(hand, face))


if __name__ == '__main__':
    unittest.main()
