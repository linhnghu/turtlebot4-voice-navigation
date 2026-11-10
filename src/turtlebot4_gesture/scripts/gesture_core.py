"""ROS-independent temporal gesture filtering and odometry-based motion controller."""
from collections import deque
import math

GESTURES = {'Wave', 'Pointing_Up', 'Victory', 'Thumb_Up', 'Open_Palm', 'Closed_Fist'}
FRAME_LABELS = GESTURES | {'No_Hand', 'Unknown', 'Multiple_Hands'}
SELECTIONS = {'Wave': 'greeting', 'Pointing_Up': 'back_and_forth', 'Victory': 'circle'}


class WaveDetector:
    """Open palm with three alternating horizontal strokes, normalized to hand size."""
    def __init__(self):
        self.strokes = deque()
        self.anchor = None
        self.direction = 0
        self.last_palm = -math.inf
        self.latched_until = -math.inf

    def update(self, now, label, x=0.0, palm_width=0.1):
        if label != 'Open_Palm':
            self.strokes.clear()
            self.anchor = None
            self.direction = 0
            self.latched_until = -math.inf
            return label
        if now - self.last_palm > 0.25:
            self.strokes.clear()
            self.anchor = None
            self.direction = 0
        self.last_palm = now
        if self.anchor is None:
            self.anchor = x
        delta = x - self.anchor
        if abs(delta) >= max(0.045, palm_width * 0.6):
            direction = 1 if delta > 0 else -1
            if direction != self.direction:
                self.strokes.append(now)
                self.direction = direction
            self.anchor = x
        while self.strokes and now - self.strokes[0] > 1.6:
            self.strokes.popleft()
        if len(self.strokes) >= 3:
            self.latched_until = now + 0.6
            self.strokes.clear()
        return 'Wave' if now < self.latched_until else label


class Controller:
    def __init__(self, signal_timeout=0.8, stable_time=0.3):
        self.signal_timeout = signal_timeout
        self.stable_time = stable_time
        self.last_signal = -math.inf
        self.last_frame = -math.inf
        self.candidate = None
        self.candidate_since = 0.0
        self.edge = None
        self.selected = None
        self.active = None
        self.segments = deque()
        self.progress = 0.0
        self.previous_pose = None
        self.status = 'WAITING: select a gesture'

    def stop(self, reason, clear=False):
        self.active = None
        self.segments.clear()
        self.progress = 0.0
        self.previous_pose = None
        if clear:
            self.selected = None
        self.status = reason

    def observe(self, label, now):
        # A healthy camera still sends frames after the user lowers their hand.
        if label in FRAME_LABELS:
            self.last_frame = now
        if label in GESTURES:
            self.last_signal = now
        # Stop/cancel bypass the selection debounce.
        if label == 'Open_Palm':
            self.stop('STOPPED: open palm; select/confirm to move')
        elif label == 'Closed_Fist':
            self.stop('WAITING: cancelled', clear=True)
        if label != self.candidate:
            self.candidate, self.candidate_since = label, now
        if now - self.candidate_since < self.stable_time or label == self.edge:
            return
        self.edge = label
        if label in SELECTIONS and self.active is None:
            self.selected = SELECTIONS[label]
            self.status = f'SELECTED: {self.selected}; show Thumb Up'
        elif label == 'Thumb_Up' and self.selected and self.active is None:
            self.active, self.selected = self.selected, None
            if self.active == 'back_and_forth':
                # Stay below the Create 3 default 0.15 m backup limit.
                self.segments = deque([('line', 0.12, 0.10), ('line', 0.12, -0.10)] * 4)
            elif self.active == 'circle':
                self.segments = deque([('circle', 2 * math.pi, 0.30)])
            else:
                self.segments = deque([('turn', 0.4, 0.5), ('turn', 0.8, -0.5),
                                       ('turn', 0.4, 0.5)])
            self.progress = 0.0
            self.previous_pose = None
            self.status = f'RUNNING: {self.active}'

    def tick(self, now, pose, safe=True, reason='sensor safety stop'):
        if now - self.last_frame > self.signal_timeout:
            self.stop('SIGNAL LOST: camera data unavailable; select and confirm again', clear=True)
            # A returning held Thumb Up must never resume a previous action.
            self.edge = None
            return 0.0, 0.0
        if not self.active and self.selected and now - self.last_signal > self.signal_timeout:
            self.stop('WAITING: selection expired; select again', clear=True)
            self.edge = None
            return 0.0, 0.0
        if not safe or pose is None:
            self.stop('BLOCKED: ' + reason, clear=True)
            return 0.0, 0.0
        if not self.active:
            return 0.0, 0.0
        kind, target, speed = self.segments[0]
        if self.previous_pose is not None:
            x, y, yaw = pose
            px, py, pyaw = self.previous_pose
            if kind == 'line':
                # Signed projection prevents backwards slip from completing a segment.
                self.progress += ((x-px)*math.cos(pyaw) + (y-py)*math.sin(pyaw)) * (1 if speed > 0 else -1)
            else:
                self.progress += math.atan2(math.sin(yaw-pyaw), math.cos(yaw-pyaw)) * (1 if speed > 0 else -1)
        self.previous_pose = pose
        if self.progress >= target:
            self.segments.popleft()
            self.progress = 0.0
            self.previous_pose = None
            if not self.segments:
                self.stop('COMPLETE: select next behavior')
            return 0.0, 0.0
        if kind == 'line':
            return speed, 0.0
        if kind == 'circle':
            return 0.12, speed  # R = v/w = 0.4 m; one full odometry revolution.
        return 0.0, speed
