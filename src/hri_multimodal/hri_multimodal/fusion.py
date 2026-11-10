"""Pure fusion rules; no ROS or GUI dependencies. Times use a monotonic clock."""
from dataclasses import dataclass
import math
import re
import time
import unicodedata


def normalize(value):
    text = unicodedata.normalize('NFD', str(value or '').lower().replace('đ', 'd'))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def voice_intent(text):
    return {
        'come here': 'come', 'come': 'come', 'lai day': 'come',
        'move forward': 'forward', 'forward': 'forward', 'di thang': 'forward',
        'tien len': 'forward', 'stop': 'stop', 'dung': 'stop', 'dung lai': 'stop',
        'emergency stop': 'stop',
    }.get(normalize(text))


def gesture_intent(label):
    return {
        'open palm': 'stop', 'thumb up': 'forward', 'thumbs up': 'forward',
        'wave': 'come', 'none': None,
    }.get(normalize(label))


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


def valid_confidence(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def fusion_decision(intent, gesture, conf_voice=1.0, conf_gesture=1.0):
    """STOP wins at any nonzero confidence; motion requires >= 0.65.

    A confidence of zero means no usable signal. Two confident but different
    movement commands cause a latched stop. Unknown phrases never mean motion.
    """
    if not all(valid_confidence(c) for c in (conf_voice, conf_gesture)):
        return Decision('stop', 'invalid_confidence')
    voice, hand = voice_intent(intent), gesture_intent(gesture)
    if (voice == 'stop' and conf_voice > 0) or (hand == 'stop' and conf_gesture > 0):
        return Decision('stop', 'stop_priority')
    voice = voice if conf_voice >= .65 else None
    hand = hand if conf_gesture >= .65 else None
    if voice and hand:
        return (Decision(voice, 'agreement') if voice == hand
                else Decision('stop', 'conflict'))
    if voice or hand:
        return Decision(voice or hand, 'voice_only' if voice else 'gesture_only')
    return Decision('idle', 'no_reliable_input')


class FusionEngine:
    def __init__(self, ttl=3.0, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.channels = {}
        self.latched = False
        self.stop_reason = ''

    def fail_stop(self, reason):
        self.latched, self.stop_reason = True, reason

    def ingest(self, channel, payload):
        if channel not in ('voice', 'gesture'):
            raise ValueError('unknown channel')
        if payload is None:
            self.channels.pop(channel, None)
        elif (not isinstance(payload, dict) or not isinstance(payload.get('text'), str)
              or not valid_confidence(payload.get('confidence', 1.0))):
            self.fail_stop('invalid_input')
        else:
            self.channels[channel] = (payload['text'], payload.get('confidence', 1.0),
                                      self.clock())
        # Evaluate each callback so a STOP cannot disappear between timer ticks.
        self.decision()

    def snapshot(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'voice', 'gesture'}:
            self.fail_stop('invalid_input')
            return
        # Replace both channels atomically; never fuse against the old snapshot.
        self.channels.clear()
        for channel in ('voice', 'gesture'):
            data = payload.get(channel)
            if data is not None:
                if (not isinstance(data, dict) or not isinstance(data.get('text'), str)
                        or not valid_confidence(data.get('confidence', 1.0))):
                    self.fail_stop('invalid_input')
                    return
                self.channels[channel] = (data['text'], data.get('confidence', 1.0),
                                          self.clock())
        self.decision()

    def active(self):
        now = self.clock()
        return {k: v for k, v in self.channels.items() if now - v[2] < self.ttl}

    def decision(self):
        if self.latched:
            return Decision('stop', self.stop_reason)
        active = self.active()
        voice = active.get('voice', ('', 0, 0))
        hand = active.get('gesture', ('', 0, 0))
        result = fusion_decision(voice[0], hand[0], voice[1], hand[1])
        if result.action == 'stop':
            self.fail_stop(result.reason)
        return result

    def reset(self):
        self.channels.clear()
        self.latched, self.stop_reason = False, ''
