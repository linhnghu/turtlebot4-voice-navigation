"""Pure geometry, utterance constraints, temporal pairing and clarification."""
from dataclasses import dataclass, field
import math
import re
import unicodedata

COLORS = ('red', 'blue', 'yellow')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize(text):
    if not isinstance(text, str) or len(text) > 512:
        raise ValueError('text must be a string of at most 512 characters')
    value = unicodedata.normalize('NFKD', text.casefold().replace('đ', 'd'))
    return ' '.join(re.findall(r'[a-z]+', ''.join(c for c in value if not unicodedata.combining(c))))


@dataclass(frozen=True)
class Intent:
    valid: bool
    color: str = ''
    reason: str = ''


def parse_speech(text):
    value = normalize(text)
    # Vietnamese "đó" (that) and "đỏ" (red) lose their distinction after
    # accent removal. Preserve that distinction before applying the grammar.
    if re.search(r'\bđó\b', text.casefold()):
        value = normalize(re.sub(r'\bđó\b', 'nay', text.casefold()))
    # A small explicit grammar avoids treating quoted, negated or unrelated
    # occurrences of "pick" or a color as an instruction.
    if re.search(r'\b(no|not|never|dont|don t|khong|dung)\b', value):
        return Intent(False, reason='negated_command')
    if re.search(r'\b(green|orange|purple|white|black|xanh la|tim|trang|den)\b', value):
        return Intent(False, reason='unsupported_color')
    found = set()
    for color, aliases in {'red': ('red', 'do'), 'blue': ('blue', 'xanh duong', 'xanh lam'),
                           'yellow': ('yellow', 'vang')}.items():
        if any(re.search(r'\b' + alias + r'\b', value) for alias in aliases):
            found.add(color)
    if len(found) > 1 or re.search(r'\b(or|hoac)\b', value):
        return Intent(False, reason='multiple_colors')
    color = next(iter(found), '')
    if value == 'xanh' or ('xanh' in value.split() and not color):
        return Intent(False, reason='ambiguous_color')
    color_names = {'red', 'blue', 'yellow', 'do', 'vang', 'xanh duong', 'xanh lam'}
    if re.sub(r'^mau ', '', value) in color_names:
        return Intent(True, color)
    # Match complete commands, rather than a phrase buried in a sentence.
    english = re.fullmatch(
        r'(?:please )?(?:pick up|pick|take|select|choose)(?: the)? '
        r'(?:(?:this|that)(?: object| one)?|(?:red|blue|yellow)(?: object| one| block)?|object)(?: please)?', value)
    vietnamese = re.fullmatch(
        r'(?:hay |vui long )?(?:gap|lay|chon)(?: giup toi)? '
        r'(?:(?:vat|khoi)(?: mau)? )?(?:nay|do|vang|xanh duong|xanh lam)(?: giup toi)?', value)
    return Intent(bool(english or vietnamese), color, '' if english or vietnamese else 'unknown_command')


@dataclass(frozen=True)
class Object:
    id: str
    color: str
    x: float
    y: float
    radius: float

    @classmethod
    def decode(cls, data):
        if not isinstance(data, dict):
            raise ValueError('object must be a dictionary')
        values = [data.get(k) for k in ('x', 'y', 'radius')]
        if (not all(number(v) for v in values) or not 0 <= values[0] <= 1
                or not 0 <= values[1] <= 1 or not 0 < values[2] <= .25
                or data.get('color') not in COLORS or not isinstance(data.get('id'), str)
                or not 0 < len(data['id']) <= 64):
            raise ValueError('invalid object id/color/center/radius')
        return cls(data['id'], data['color'], *values)


@dataclass(frozen=True)
class Ray:
    origin: tuple
    direction: tuple

    @classmethod
    def decode(cls, data):
        if not isinstance(data, dict):
            raise ValueError('pointing ray must be an object')
        origin, direction = data.get('origin'), data.get('direction')
        if (not isinstance(origin, (list, tuple)) or not isinstance(direction, (list, tuple))
                or len(origin) != 2 or len(direction) != 2
                or not all(number(v) for v in (*origin, *direction))
                or not all(0 <= v <= 1 for v in origin)):
            raise ValueError('ray needs normalized origin [x,y] and finite direction [dx,dy]')
        length = math.hypot(*direction)
        if not math.isfinite(length) or length < 1e-6:
            raise ValueError('pointing direction has zero or invalid length')
        return cls(tuple(origin), tuple(v / length for v in direction))


@dataclass
class Decision:
    state: str
    reason: str
    message: str
    target: str = ''
    candidates: list = field(default_factory=list)
    angles: dict = field(default_factory=dict)


def resolve(objects, ray, intent, cone_degrees=12., ambiguity_degrees=8.):
    if not intent.valid:
        return Decision('CLARIFY', intent.reason, 'Tôi chưa hiểu. Hãy nói “Pick up this object” hoặc chọn một màu rõ ràng.')
    if not objects:
        return Decision('WAITING', 'no_objects', 'Chưa phát hiện được vật trên bàn.')
    available = [obj for obj in objects if not intent.color or obj.color == intent.color]
    if not available:
        return Decision('CLARIFY', 'color_not_found', f'Không thấy vật {intent.color.upper()}. Vui lòng kiểm tra lại.')
    if ray is None:
        return Decision('WAITING', 'need_pointing', 'Hãy kéo chuột từ một điểm trên bàn về phía vật muốn chọn.')
    scored = []
    for obj in objects:
        dx, dy = obj.x - ray.origin[0], obj.y - ray.origin[1]
        distance = math.hypot(dx, dy)
        projection = dx * ray.direction[0] + dy * ray.direction[1]
        if projection <= 0 or distance <= obj.radius:
            continue
        angle = math.degrees(math.acos(max(-1., min(1., projection / distance))))
        radius_angle = math.degrees(math.asin(min(1., obj.radius / distance)))
        if angle <= cone_degrees + radius_angle:
            scored.append((angle, obj))
    scored.sort(key=lambda item: (item[0], item[1].id))
    angles = {obj.id: round(angle, 2) for angle, obj in scored}
    if not scored:
        return Decision('CLARIFY', 'pointing_miss', 'Tia chỉ chưa hướng vào vật nào. Bạn muốn vật nào?',
                        candidates=[o.id for o in available], angles=angles)
    best = scored[0][1]
    if len(scored) > 1 and scored[1][0] - scored[0][0] <= ambiguity_degrees:
        candidates = [o.id for angle, o in scored if angle - scored[0][0] <= ambiguity_degrees]
        return Decision('CLARIFY', 'ambiguous_pointing',
                        'Tia chỉ nằm giữa nhiều vật. Hãy chỉ lại hoặc xác nhận một vật.',
                        candidates=candidates, angles=angles)
    if intent.color and best.color != intent.color:
        return Decision('CLARIFY', 'speech_pointing_conflict',
                        f'Bạn nói {intent.color.upper()} nhưng chỉ {best.color.upper()}. Bạn muốn vật nào?',
                        candidates=list(dict.fromkeys([best.id] + [o.id for o in available])), angles=angles)
    return Decision('SELECTED', 'speech_and_pointing_agree', f'Tôi chọn vật {best.color.upper()}.',
                    target=best.id, candidates=[best.id], angles=angles)


class ReferenceEngine:
    """One request, one selection event; confirmation is bound to a request and scene."""
    def __init__(self, cue_ttl=3., scene_ttl=1., confirmation_ttl=15., cone_degrees=12., ambiguity_degrees=8.):
        for value in (cue_ttl, scene_ttl, confirmation_ttl, cone_degrees, ambiguity_degrees):
            if not number(value) or value <= 0:
                raise ValueError('timeouts and angular thresholds must be finite and positive')
        if cone_degrees >= 90 or ambiguity_degrees >= 90:
            raise ValueError('angular thresholds must be < 90 degrees')
        self.cue_ttl, self.scene_ttl, self.confirmation_ttl = cue_ttl, scene_ttl, confirmation_ttl
        self.cone, self.margin = cone_degrees, ambiguity_degrees
        self.objects = []
        self.scene_at = self.ray_at = -math.inf
        self.ray = None
        self.signature = None
        self.request_id = self.selection_id = 0
        self.intent = None
        self.request_at = -math.inf
        self.decision = Decision('WAITING', 'waiting_for_scene', 'Đang chờ ảnh mặt bàn…')

    def scene(self, now, data):
        if not isinstance(data, dict) or not isinstance(data.get('objects'), list) or len(data['objects']) > 30:
            raise ValueError('scene needs a list of at most 30 objects')
        objects = [Object.decode(item) for item in data['objects']]
        if len({o.id for o in objects}) != len(objects):
            raise ValueError('duplicate object IDs')
        signature = tuple(sorted((o.id, o.color, o.x, o.y, o.radius) for o in objects))
        changed = self.signature is not None and signature != self.signature
        expired = self.signature is not None and now - self.scene_at > self.scene_ttl
        self.signature, self.objects, self.scene_at = signature, objects, now
        if changed or expired:
            self.intent, self.ray = None, None
            self.decision = Decision('WAITING', 'scene_changed' if changed else 'scene_restored',
                                     'Mặt bàn đã đổi hoặc vừa khôi phục. Hãy chỉ và gửi lệnh mới.')
        elif self.decision.reason in ('waiting_for_scene', 'scene_unavailable', 'invalid_scene'):
            self.decision = Decision('WAITING', 'ready', 'Kéo chuột để chỉ vật, sau đó gửi lời nói.')

    def fault(self, reason='invalid_scene'):
        self.objects, self.intent, self.ray = [], None, None
        self.scene_at = -math.inf
        self.decision = Decision('WAITING', reason, 'Dữ liệu mặt bàn không hợp lệ; đang chờ ảnh mới.')

    def point(self, now, data):
        ray = Ray.decode(data)
        self.update(now)
        self.ray, self.ray_at = ray, now
        if self.intent is not None:
            self._evaluate(now)

    def request(self, now, text, ray_data=None):
        intent = parse_speech(text)
        # An atomic request can supply a ray or explicitly clear an old one.
        if ray_data is not None:
            ray = Ray.decode(ray_data)
            self.ray, self.ray_at = ray, now
        self.request_id += 1
        self.intent, self.request_at = intent, now
        self._evaluate(now)

    def _evaluate(self, now):
        if now - self.scene_at > self.scene_ttl or not self.objects:
            self.decision = Decision('WAITING', 'scene_unavailable', 'Chưa có ảnh mặt bàn mới và vật hợp lệ.')
            return
        ray = self.ray if now - self.ray_at <= self.cue_ttl else None
        self.decision = resolve(self.objects, ray, self.intent, self.cone, self.margin)
        if self.decision.state == 'SELECTED':
            self.selection_id += 1
            self.intent = None
            self.ray = None  # A later request must carry a fresh gesture.

    def confirm(self, now, request_id, object_id):
        if (type(request_id) is not int or request_id != self.request_id
                or self.decision.state != 'CLARIFY' or self.intent is None
                or now - self.request_at > self.confirmation_ttl
                or now - self.scene_at > self.scene_ttl):
            return False
        # Unsupported/negated commands require a new utterance, not a color click.
        if not self.intent.valid or object_id not in self.decision.candidates:
            return False
        obj = next((o for o in self.objects if o.id == object_id), None)
        if obj is None:
            return False
        self.decision = Decision('SELECTED', 'explicit_confirmation', f'Đã xác nhận: chọn {obj.color.upper()}.',
                                 target=obj.id, candidates=[obj.id])
        self.selection_id += 1
        self.intent, self.ray = None, None
        return True

    def update(self, now):
        if now - self.scene_at > self.scene_ttl:
            self.intent, self.ray = None, None
            self.decision = Decision('WAITING', 'scene_unavailable', 'Không còn ảnh mặt bàn mới. Hãy khôi phục nguồn ảnh.')
        elif self.intent is not None:
            ttl = self.confirmation_ttl if self.decision.state == 'CLARIFY' else self.cue_ttl
            if now - self.request_at > ttl:
                self.intent, self.ray = None, None
                self.decision = Decision('WAITING', 'request_expired', 'Yêu cầu đã hết hạn. Hãy gửi lời nói và tia chỉ mới.')
        return self.snapshot()

    def snapshot(self):
        return dict(state=self.decision.state, reason=self.decision.reason,
                    message=self.decision.message, target=self.decision.target,
                    candidates=self.decision.candidates, angles=self.decision.angles,
                    request_id=self.request_id, selection_id=self.selection_id,
                    cue_ttl=self.cue_ttl, cone_degrees=self.cone,
                    objects=[vars(obj) for obj in self.objects])
