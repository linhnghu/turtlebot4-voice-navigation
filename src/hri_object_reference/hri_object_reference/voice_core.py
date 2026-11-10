"""Speech result validation shared by live microphone and audio replay tests."""
import math
import re

from .core import normalize


def confirmation_color(text):
    value = normalize(text)
    value = re.sub(r'^(?:xac nhan|confirm|yes|dung roi|dung)\s+', '', value)
    value = re.sub(r'^(?:vat |mau |vat mau )+', '', value)
    return {'red': 'red', 'do': 'red', 'blue': 'blue', 'xanh duong': 'blue', 'xanh lam': 'blue',
            'yellow': 'yellow', 'vang': 'yellow'}.get(value, '')


def transcript(result, minimum=.6):
    text = result.get('text', '')
    words = result.get('result', [])
    confidence = sum(float(w.get('conf', 0.)) for w in words) / len(words) if words else 0.
    accepted = (isinstance(text, str) and 0 < len(text) <= 512 and math.isfinite(confidence)
                and minimum <= confidence <= 1.)
    return dict(text=text, confidence=round(confidence, 4), accepted=bool(accepted), source='microphone')
