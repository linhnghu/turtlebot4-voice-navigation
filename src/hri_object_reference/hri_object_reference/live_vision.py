"""Temporal interpretation of real hand landmarks and colored object detections."""
from collections import deque
import math

import cv2
import numpy as np

from .core import COLORS, Ray


def square_frame(image, size=640):
    height, width = image.shape[:2]
    scale = size / max(height, width)
    resized = cv2.resize(image, (round(width * scale), round(height * scale)))
    square = np.full((size, size, 3), 40, dtype=np.uint8)
    y, x = (size - resized.shape[0]) // 2, (size - resized.shape[1]) // 2
    square[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return square


def index_ray(points):
    """Index MCP -> tip in the image plane, with other fingers folded.

    No depth inference: the finger must point along the visible tabletop plane.
    All landmarks are in the same square image frame as object centroids.
    """
    if len(points) != 21:
        return None
    if not all(math.isfinite(p.x) and math.isfinite(p.y) for p in points):
        return None
    def distance(a, b):
        return math.hypot(points[a].x - points[b].x, points[a].y - points[b].y)
    if distance(8, 0) < 1.2 * distance(6, 0) or distance(8, 5) < .045:
        return None
    straight_a = np.array([points[6].x - points[5].x, points[6].y - points[5].y])
    straight_b = np.array([points[8].x - points[6].x, points[8].y - points[6].y])
    lengths = np.linalg.norm(straight_a) * np.linalg.norm(straight_b)
    if lengths < 1e-6 or np.dot(straight_a, straight_b) / lengths < .7:
        return None
    folded = sum(distance(tip, 0) < 1.15 * distance(pip, 0) for tip, pip in ((12, 10), (16, 14), (20, 18)))
    if folded < 2:
        return None
    origin = [float(points[8].x), float(points[8].y)]
    data = dict(origin=origin, direction=[points[8].x - points[5].x, points[8].y - points[5].y])
    try:
        ray = Ray.decode(data)
    except ValueError:
        return None
    return dict(origin=list(ray.origin), direction=list(ray.direction))


class PointingFilter:
    def __init__(self, hold=.2):
        self.hold = hold
        self.samples = deque()

    def observe(self, now, hands):
        ray = index_ray(hands[0]) if len(hands) == 1 else None
        if ray is None:
            self.samples.clear()
            return None
        if self.samples and now - self.samples[-1][0] > .25:
            self.samples.clear()
        self.samples.append((now, ray))
        while self.samples and now - self.samples[0][0] > .5:
            self.samples.popleft()
        if len(self.samples) < 3 or now - self.samples[0][0] < self.hold:
            return None
        vectors = np.array([r['direction'] for _, r in self.samples])
        mean = vectors.mean(axis=0)
        length = np.linalg.norm(mean)
        if length < .95:
            return None
        mean /= length
        angles = np.degrees(np.arccos(np.clip(vectors @ mean, -1., 1.)))
        if max(angles) > 12.:
            return None
        # Use the latest tip, average only direction to reduce delay during hand movement.
        return dict(origin=ray['origin'], direction=mean.tolist())


class SceneFilter:
    """Lock only stable measured scenes; tolerate small pixel noise, never missing objects."""
    def __init__(self, frames=3, tolerance=.025):
        self.frames, self.tolerance = frames, tolerance
        self.samples = deque(maxlen=frames)
        self.locked = None
        self.last_time = -math.inf

    def near(self, a, b):
        by_id = {obj['id']: obj for obj in b}
        return len(a) == len(b) and all(obj['id'] in by_id
            and math.hypot(obj['x'] - by_id[obj['id']]['x'], obj['y'] - by_id[obj['id']]['y']) <= self.tolerance
            and abs(obj['radius'] - by_id[obj['id']]['radius']) <= self.tolerance for obj in a)

    def observe(self, now, objects):
        if now - self.last_time > .5:
            self.locked = None
            self.samples.clear()
        self.last_time = now
        # Require one component of each color; extra blobs are unknown, not an arbitrary choice.
        if (len(objects) != 3 or {o['color'] for o in objects} != set(COLORS)
                or any(not .015 <= o['radius'] <= .15 for o in objects)):
            self.samples.clear()
            self.locked = None
            return None
        if self.locked is not None and self.near(objects, self.locked):
            return [dict(obj) for obj in self.locked]
        self.locked = None
        if self.samples and not self.near(objects, self.samples[-1]):
            self.samples.clear()
        self.samples.append(objects)
        if len(self.samples) < self.frames or not all(self.near(objects, old) for old in self.samples):
            return None
        # A locked center is anchored to a stable, observed image. It is renewed
        # only while every current detection remains close to that same anchor.
        self.locked = [dict(obj) for obj in objects]
        self.samples.clear()
        return [dict(obj) for obj in self.locked]


def without_hands(image, hands):
    masked = image.copy()
    size = image.shape[0]
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for hand in hands:
        points = np.array([(round(p.x * size), round(p.y * size)) for p in hand], dtype=np.int32)
        cv2.fillConvexPoly(mask, cv2.convexHull(points), 255)
        wrist, knuckle = points[0], points[9]
        forearm = wrist + 4 * (wrist - knuckle)
        width = max(20, round(float(np.linalg.norm(points[5] - points[17])) * 1.6))
        cv2.line(mask, tuple(wrist), tuple(forearm), 255, width)
    mask = cv2.dilate(mask, np.ones((19, 19), dtype=np.uint8))
    masked[mask > 0] = 40
    return masked
