"""ROS-independent FSM. All time values use the receiver's monotonic clock."""
from collections import deque
from dataclasses import dataclass
import math
import re
import unicodedata


def is_greeting(text):
    if not isinstance(text, str) or len(text) > 512:
        return False
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    words = re.findall(r'[a-z]+', text)
    return ' '.join(words) in {
        'hello', 'hello robot', 'hi robot', 'hey robot', 'excuse me',
        'xin chao', 'chao robot', 'xin chao robot',
    }


@dataclass(frozen=True)
class Config:
    window: float = .6
    head_hold: float = .4
    hand_hold: float = .3
    stable_ratio: float = .75
    min_frames: int = 4
    camera_timeout: float = .7
    cue_ttl: float = 2.5
    attention_timeout: float = 3.
    disengage_timeout: float = 1.5
    cooldown: float = 5.
    speech_confidence: float = .65

    def __post_init__(self):
        for name in ('window', 'head_hold', 'hand_hold', 'camera_timeout',
                     'cue_ttl', 'attention_timeout', 'disengage_timeout', 'cooldown'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if max(self.head_hold, self.hand_hold) >= self.window:
            raise ValueError('window must exceed the head and hand hold durations')
        if type(self.min_frames) is not int or self.min_frames < 2:
            raise ValueError('min_frames must be an integer >= 2')
        if not .5 < self.stable_ratio <= 1:
            raise ValueError('stable_ratio must be in (.5, 1]')
        if not 0 <= self.speech_confidence <= 1:
            raise ValueError('speech_confidence must be in [0, 1]')


class EngagementEngine:
    def __init__(self, config=None):
        self.config = config or Config()
        self.reset()

    def reset(self):
        self.state = 'IDLE'
        self.reason = 'waiting_for_signals'
        self.history = deque()
        self.last_frame = -math.inf
        self.healthy = self.face_present = False
        self.speech_at = self.hand_at = -math.inf
        self.last_attention = self.last_facing = -math.inf
        self.last_greeting = -math.inf
        self.hand_active = False
        self.greeting_count = 0
        self.sequence = 0

    def _clear_visual(self):
        self.history.clear()
        self.hand_at = -math.inf
        self.hand_active = False
        self.face_present = False

    def observe(self, now, *, healthy, face_present, facing, hand_raised):
        if not math.isfinite(now):
            raise ValueError('now must be finite')
        if any(type(v) is not bool for v in (healthy, face_present, facing, hand_raised)):
            raise ValueError('vision fields must be booleans')
        if now < self.last_frame:
            raise ValueError('vision time moved backwards')
        if now - self.last_frame > self.config.camera_timeout:
            self._clear_visual()
            self.speech_at = -math.inf
        self.last_frame, self.healthy = now, healthy
        self.face_present = healthy and face_present
        if not healthy:
            self._clear_visual()
            # Never let a verbal cue bridge a camera outage.
            self.speech_at = -math.inf
            return
        self.history.append((now, face_present and facing, face_present and hand_raised))
        while self.history and now - self.history[0][0] > self.config.window:
            self.history.popleft()
        stable_hand = self._stable(now, 2, self.config.hand_hold)
        if stable_hand and not self.hand_active:
            self.hand_at = now
        self.hand_active = stable_hand

    def speech(self, now, text, confidence=1.):
        if (not math.isfinite(now) or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('invalid speech timestamp or confidence')
        accepted = is_greeting(text) and confidence >= self.config.speech_confidence
        if accepted:
            self.speech_at = now
        return accepted

    def _stable(self, now, index, hold):
        samples = [sample for sample in self.history if now - sample[0] <= self.config.window]
        positives = [sample for sample in samples if sample[index]]
        return (len(positives) >= self.config.min_frames
                and positives[-1][0] - positives[0][0] >= hold - 1e-9
                and len(positives) / len(samples) >= self.config.stable_ratio
                and now - positives[-1][0] <= self.config.camera_timeout)

    def update(self, now):
        if not math.isfinite(now):
            raise ValueError('now must be finite')
        fresh = self.healthy and 0 <= now - self.last_frame <= self.config.camera_timeout
        if not fresh:
            self._clear_visual()
            self.speech_at = -math.inf
            self.state, self.reason = 'IDLE', 'camera_unavailable'
            return self.snapshot(now, False, False)
        head = self.face_present and self._stable(now, 1, self.config.head_hold)
        hand = 0 <= now - self.hand_at <= self.config.cue_ttl
        speech = 0 <= now - self.speech_at <= self.config.cue_ttl
        if head:
            self.last_facing = now
        if self.state == 'ENGAGED':
            if now - self.last_facing >= self.config.disengage_timeout:
                self.state, self.reason = 'IDLE', 'person_disengaged'
                self.speech_at = self.hand_at = -math.inf
            else:
                self.reason = 'interaction_active'
        elif self.state == 'IDLE':
            if head or hand or speech:
                self.state, self.reason = 'ATTENTION', 'waiting_for_confirmation'
                self.last_attention = now
        else:
            if head or hand or speech:
                self.last_attention = now
            if head and (hand or speech):
                if now - self.last_greeting >= self.config.cooldown:
                    self.state, self.reason = 'ENGAGED', 'head_and_speech' if speech else 'head_and_hand'
                    self.last_greeting = now
                    self.greeting_count += 1
                    self.sequence += 1
                    self.speech_at = self.hand_at = -math.inf
                else:
                    self.reason = 'greeting_cooldown'
            elif now - self.last_attention >= self.config.attention_timeout:
                self.state, self.reason = 'IDLE', 'attention_expired'
            else:
                self.reason = 'head_only' if head else 'waiting_for_facing_person'
        return self.snapshot(now, head, hand, speech)

    def snapshot(self, now, head=False, hand=False, speech=False):
        return dict(state=self.state, reason=self.reason, head_stable=head,
                    hand_recent=hand, speech_recent=speech,
                    camera_fresh=self.healthy and 0 <= now - self.last_frame <= self.config.camera_timeout,
                    face_present=self.face_present, greeting_count=self.greeting_count,
                    sequence=self.sequence)
