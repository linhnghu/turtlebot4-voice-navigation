"""Head pose and raised open-hand geometry from MediaPipe landmarks.

Pose uses an approximate camera matrix and a generic six-point face model.
It measures head orientation, not eye gaze or a person's identity.
"""
import math

import cv2
import numpy as np

FACE_INDICES = (1, 152, 33, 263, 61, 291)
FACE_MODEL = np.array([
    (0., 0., 0.), (0., 330., 65.), (-225., -170., 135.),
    (225., -170., 135.), (-150., 150., 125.), (150., 150., 125.),
], dtype=np.float64)


def head_pose(face, width, height):
    image = np.array([(face[i].x * width, face[i].y * height)
                      for i in FACE_INDICES], dtype=np.float64)
    camera = np.array([[width, 0., width / 2], [0., width, height / 2], [0., 0., 1.]])
    if not np.isfinite(image).all() or np.ptp(image[:, 0]) < 20:
        return None
    ok, rotation, translation = cv2.solvePnP(FACE_MODEL, image, camera, np.zeros((4, 1)),
                                           flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok or not np.isfinite(rotation).all() or translation[2, 0] <= 0:
        return None
    matrix, _ = cv2.Rodrigues(rotation)
    pitch, yaw, roll = cv2.RQDecomp3x3(matrix)[0]
    return float(pitch), float(yaw), float(roll)


def raised_open_hand(hand, face):
    """Four extended fingers, palm near this face, and wrist above the chin."""
    def distance(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    if len(hand) != 21 or len(face) < 292:
        return False
    extended = sum(distance(hand[tip], hand[0]) > 1.15 * distance(hand[pip], hand[0])
                   for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)))
    face_width = abs(face[263].x - face[33].x)
    center = (face[263].x + face[33].x) / 2
    palm_width = distance(hand[5], hand[17])
    return (extended == 4 and palm_width > .025
            and hand[0].y < face[152].y
            and abs(hand[9].x - center) < max(.2, face_width * 2.5)
            and hand[9].y > face[10].y - .5)
