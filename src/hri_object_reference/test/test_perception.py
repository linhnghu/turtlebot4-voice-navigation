import unittest

import cv2
import numpy as np

from hri_object_reference.perception import detect_objects, make_table


class PerceptionTest(unittest.TestCase):
    def test_three_colors_extracted_from_pixels(self):
        objects = detect_objects(make_table())
        self.assertEqual([o['color'] for o in objects], ['red', 'blue', 'yellow'])
        for obj, expected_x in zip(objects, (.22, .5, .78)):
            self.assertAlmostEqual(obj['x'], expected_x, delta=.002)
            self.assertAlmostEqual(obj['y'], .35, delta=.002)

    def test_moving_pixels_changes_detected_center(self):
        image = np.full((640, 640, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (400, 400), (470, 470), (0, 0, 255), -1)
        obj = detect_objects(image)[0]
        self.assertEqual(obj['color'], 'red')
        self.assertAlmostEqual(obj['x'], 435 / 640, places=5)
        self.assertAlmostEqual(obj['y'], 435 / 640, places=5)

    def test_noise_is_not_an_object(self):
        image = np.full((640, 640, 3), 255, dtype=np.uint8)
        image[10:12, 10:12] = (0, 0, 255)
        self.assertEqual(detect_objects(image), [])

    def test_duplicate_colors_have_distinct_ids(self):
        image = np.full((640, 640, 3), 255, dtype=np.uint8)
        for x in (100, 300):
            cv2.rectangle(image, (x, 100), (x + 60, 160), (255, 0, 0), -1)
        self.assertEqual([o['id'] for o in detect_objects(image)], ['blue_1', 'blue_2'])

    def test_shuffle_still_detects_three_colors(self):
        for seed in range(1, 5):
            self.assertEqual({o['color'] for o in detect_objects(make_table(seed))}, {'red', 'blue', 'yellow'})


if __name__ == '__main__':
    unittest.main()
