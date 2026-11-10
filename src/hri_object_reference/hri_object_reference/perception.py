"""Extract colored components from a generated square tabletop image."""
import cv2
import numpy as np

PALETTE = {'red': (65, 65, 225), 'blue': (220, 125, 45), 'yellow': (45, 195, 240)}


def make_table(seed=0, size=640):
    image = np.full((size, size, 3), (246, 244, 240), dtype=np.uint8)
    cv2.rectangle(image, (20, 70), (size - 20, size - 30), (210, 206, 203), 2)
    for line in range(100, size - 30, 60):
        cv2.line(image, (25, line), (size - 25, line), (233, 229, 226), 1)
    # Render positions are used only to create pixels. All published centers
    # and colors are recovered from those pixels by detect_objects().
    import random
    rng = random.Random(seed)
    colors = list(PALETTE)
    if seed:
        rng.shuffle(colors)
    for index, color in enumerate(colors):
        x = int((.22 + index * .28) * size)
        y = int((.35 + (rng.uniform(-.06, .1) if seed else 0)) * size)
        half = int(.055 * size)
        cv2.rectangle(image, (x - half, y - half), (x + half, y + half), PALETTE[color], -1)
    return image


def detect_objects(image):
    if image is None or image.ndim != 3 or image.shape[2] != 3 or image.shape[0] != image.shape[1]:
        raise ValueError('expected a square BGR tabletop image')
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    bands = {'red': [((0, 100, 90), (10, 255, 255)), ((170, 100, 90), (179, 255, 255))],
             'blue': [((95, 100, 90), (130, 255, 255))],
             'yellow': [((18, 100, 90), (38, 255, 255))]}
    objects = []
    size = image.shape[0]
    for color, ranges in bands.items():
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, np.array(lower), np.array(upper)))
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        components = [(stats[i], centers[i]) for i in range(1, count)
                      if stats[i, cv2.CC_STAT_AREA] >= size * size * .001]
        components.sort(key=lambda item: (item[1][0], item[1][1]))
        for index, (box, center) in enumerate(components, 1):
            objects.append(dict(id=f'{color}_{index}', color=color,
                                x=round(float(center[0] / size), 6),
                                y=round(float(center[1] / size), 6),
                                radius=round(float(max(box[2], box[3]) / (2 * size)), 6)))
    return sorted(objects, key=lambda obj: obj['x'])
