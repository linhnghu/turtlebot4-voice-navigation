"""ROS-independent temporal interpretation of MediaPipe hand observations."""
from collections import deque
import math


class GestureFilter:
    """Moving palm is Wave; a stationary palm for .4s is latched STOP.

    Every unclassified palm frame inhibits motion immediately. A stationary
    palm never becomes Wave. Movement commands require one hand and .2s
    stability; stop is allowed with multiple hands.
    """
    def __init__(self):
        self.samples = deque()
        self.strokes = deque()
        self.anchor = None
        self.direction = 0
        self.last_palm = -math.inf
        self.last_motion = -math.inf
        self.palm_since = None
        self.wave_until = -math.inf
        self.candidate = None
        self.candidate_since = 0.

    def observe(self, now, label, score, hands=1, x=.5, width=.15):
        # Tracking may briefly miss a moving palm. Keep the temporal evidence
        # for at most 150 ms while continuing to inhibit motion.
        if label in ('None', 'Unknown') and hands <= 1 and now - self.last_palm <= .15:
            return 'Palm pending', 0., True
        if label == 'Open_Palm' and score >= .5:
            self.candidate = None
            if now - self.last_palm > .2:
                self.samples.clear()
                self.strokes.clear()
                self.anchor = x
                self.direction = 0
                self.palm_since = now
                self.last_motion = now
                self.wave_until = -math.inf
            self.last_palm = now
            self.samples.append((now, x))
            while self.samples and now - self.samples[0][0] > .2:
                self.samples.popleft()
            movement = max(v for _, v in self.samples) - min(v for _, v in self.samples)
            if movement > max(.012, width * .12):
                self.last_motion = now
            delta = x - self.anchor
            if abs(delta) >= max(.045, width * .55):
                direction = 1 if delta > 0 else -1
                if direction != self.direction:
                    self.strokes.append(now)
                    self.direction = direction
                self.anchor = x
            while self.strokes and now - self.strokes[0] > 1.5:
                self.strokes.popleft()
            if len(self.strokes) >= 3 and hands == 1:
                self.wave_until = now + .65
                self.strokes.clear()
            stationary = now - self.last_motion >= .4
            if stationary or hands > 1:
                return 'Open Palm', score, False
            if now < self.wave_until and hands == 1:
                return 'Wave', score, False
            return 'Palm pending', score, True
        # Unknown frames do not build motion evidence or sustain a wave.
        self.samples.clear()
        self.strokes.clear()
        self.anchor = None
        self.last_palm = -math.inf
        self.wave_until = -math.inf
        if label == 'Thumb_Up' and score >= .65 and hands == 1:
            if self.candidate != label:
                self.candidate, self.candidate_since = label, now
            if now - self.candidate_since >= .2:
                return 'Thumb Up', score, False
            return 'Thumb pending', score, False
        self.candidate = None
        return ('Multiple hands' if hands > 1 else 'No hand' if hands == 0 else 'Unknown'), 0., hands > 1
