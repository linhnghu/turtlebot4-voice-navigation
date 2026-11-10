"""ROS adapters; emits a target only after resolution or explicit confirmation."""
import json
from pathlib import Path
import signal
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .core import Decision, ReferenceEngine
from .voice_core import confirmation_color


class Controller(Node):
    def __init__(self):
        super().__init__('reference_controller')
        values = {name: float(self.declare_parameter(name, default).value) for name, default in
                  (('cue_ttl', 3.), ('scene_ttl', 1.), ('confirmation_ttl', 15.),
                   ('cone_degrees', 12.), ('ambiguity_degrees', 8.))}
        self.engine = ReferenceEngine(**values)
        self.camera_required = bool(self.declare_parameter('camera_required', False).value)
        self.mic_required = bool(self.declare_parameter('mic_required', False).value)
        self.camera_time = self.mic_time = -float('inf')
        self.camera_ready = self.mic_ready = False
        self.log = None
        output = str(self.declare_parameter('log_dir', '').value)
        if output:
            directory = Path(output).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            self.log = (directory / f'events_{time.time_ns()}.jsonl').open('w', buffering=1)
        self.status = self.create_publisher(String, '/reference/state', 10)
        self.events = self.create_publisher(String, '/reference/events', 10)
        self.targets = self.create_publisher(String, '/reference/target', 10)
        self.questions = self.create_publisher(String, '/reference/clarification', 10)
        self.create_subscription(String, '/reference/scene', self.on_scene, 1)
        self.create_subscription(String, '/reference/pointing', self.on_point, 1)
        self.create_subscription(String, '/reference/speech', self.on_speech, 10)
        self.create_subscription(String, '/reference/request', self.on_request, 10)
        self.create_subscription(String, '/reference/confirm', self.on_confirm, 10)
        self.create_subscription(String, '/reference/camera_status', self.on_camera, 1)
        self.create_subscription(String, '/reference/mic_status', self.on_mic, 1)
        self.create_service(Trigger, '/reference/reset', self.reset)
        self.create_timer(.05, self.tick)
        self.previous = None
        self.last_selection = 0

    @staticmethod
    def decode(message):
        if len(message.data) > 16384:
            raise ValueError('message exceeds 16 KiB')
        data = json.loads(message.data)
        if not isinstance(data, dict):
            raise ValueError('expected a JSON object')
        return data

    def record(self, kind, **data):
        if self.log:
            self.log.write(json.dumps(dict(kind=kind, wall_time=time.time(), **data), ensure_ascii=False) + '\n')

    def invalid(self, exc, scene=False):
        if scene:
            self.engine.fault()
        else:
            self.engine.intent, self.engine.ray = None, None
            self.engine.decision = Decision('WAITING', 'invalid_input', 'Tín hiệu không hợp lệ. Hãy gửi lại.')
        self.get_logger().warning(str(exc))

    def on_scene(self, message):
        try:
            self.engine.scene(time.monotonic(), self.decode(message))
        except (ValueError, TypeError, KeyError) as exc:
            self.invalid(exc, scene=True)
        self.tick()

    def on_point(self, message):
        try:
            self.engine.update(time.monotonic())
            data = self.decode(message)
            self.engine.point(time.monotonic(), data)
            self.record('pointing', ray=data)
        except (ValueError, TypeError, KeyError) as exc:
            self.invalid(exc)
        self.tick()

    def on_speech(self, message):
        try:
            if message.data.lstrip().startswith('{'):
                data = self.decode(message)
                text, confidence = data['text'], data.get('confidence', 0.)
                if (type(confidence) not in (int, float) or not .6 <= confidence <= 1
                        or data.get('accepted') is not True):
                    self.record('speech_rejected', payload=data)
                    return
            else:
                text = message.data
            if not isinstance(text, str) or len(text) > 512:
                raise ValueError('speech must be a string <= 512 characters')
            now = time.monotonic()
            self.engine.update(now)
            color = confirmation_color(text)
            if color and self.engine.decision.state == 'CLARIFY':
                obj = next((o for o in self.engine.objects if o.color == color
                            and o.id in self.engine.decision.candidates), None)
                accepted = bool(obj and self.engine.confirm(now, self.engine.request_id, obj.id))
                self.record('voice_confirmation', text=text, accepted=accepted, request_id=self.engine.request_id)
            else:
                self.engine.request(now, text)
                self.record('speech', text=text, request_id=self.engine.request_id)
        except (ValueError, TypeError, KeyError) as exc:
            self.invalid(exc)
        self.tick()

    def on_camera(self, message):
        try:
            data = self.decode(message)
            if type(data.get('healthy')) is not bool or type(data.get('scene_ready')) is not bool:
                raise ValueError('invalid camera health')
            self.camera_time = time.monotonic()
            self.camera_ready = data['healthy'] and data['scene_ready']
        except (ValueError, TypeError):
            self.camera_ready = False
        self.tick()

    def on_mic(self, message):
        try:
            data = self.decode(message)
            if type(data.get('healthy')) is not bool:
                raise ValueError('invalid microphone health')
            self.mic_time = time.monotonic()
            self.mic_ready = data['healthy']
        except (ValueError, TypeError):
            self.mic_ready = False
        self.tick()

    def on_request(self, message):
        try:
            data = self.decode(message)
            if 'ray' not in data:
                raise ValueError('atomic requests must contain ray (object or null)')
            # Explicit null must not reuse an earlier independent gesture.
            self.engine.ray = None
            self.engine.request(time.monotonic(), data['text'], data['ray'])
            self.record('request', text=data['text'], ray=data['ray'], request_id=self.engine.request_id)
        except (ValueError, TypeError, KeyError) as exc:
            self.invalid(exc)
        self.tick()

    def on_confirm(self, message):
        try:
            data = self.decode(message)
            accepted = self.engine.confirm(time.monotonic(), data['request_id'], data['object_id'])
            self.record('confirmation', accepted=accepted, **data)
            if not accepted:
                self.get_logger().warning('Confirmation rejected: stale request, scene or candidate')
        except (ValueError, TypeError, KeyError) as exc:
            self.get_logger().warning(f'Invalid confirmation: {exc}')
        self.tick()

    def reset(self, request, response):
        self.engine.intent, self.engine.ray = None, None
        self.engine.request_id += 1  # Old confirmation buttons can never match a reset session.
        self.engine.decision = Decision('WAITING', 'reset', 'Đã xóa yêu cầu. Hãy chỉ và gửi lời nói mới.')
        self.tick()
        response.success, response.message = True, 'Reference request reset'
        return response

    def tick(self):
        now = time.monotonic()
        camera_ok = self.camera_ready and now - self.camera_time <= .7
        mic_ok = self.mic_ready and now - self.mic_time <= .7
        problem = ('camera_not_ready' if self.camera_required and not camera_ok
                   else 'microphone_not_ready' if self.mic_required and not mic_ok else '')
        self.engine.update(now)
        if problem:
            self.engine.intent, self.engine.ray = None, None
            self.engine.decision = Decision('WAITING', problem,
                'Đang chờ camera và cảnh sẵn sàng.' if problem == 'camera_not_ready' else 'Chờ microphone hoạt động.')
        elif self.engine.decision.reason in ('camera_not_ready', 'microphone_not_ready'):
            self.engine.decision = Decision('WAITING', 'ready', 'Camera và mic sẵn sàng. Giữ hướng chỉ rồi nói “Lấy vật này”.')
        state = self.engine.snapshot()
        state.update(camera_ready=camera_ok, microphone_ready=mic_ok)
        self.status.publish(String(data=json.dumps(state, ensure_ascii=False)))
        key = (state['request_id'], state['state'], state['reason'], state['target'], tuple(state['candidates']))
        if key != self.previous:
            self.events.publish(String(data=json.dumps(state, ensure_ascii=False)))
            self.record('decision', **state)
            self.get_logger().info(f"{state['state']} / {state['reason']}: {state['message']}")
            if state['state'] == 'CLARIFY':
                self.questions.publish(String(data=json.dumps(state, ensure_ascii=False)))
            self.previous = key
        if state['selection_id'] != self.last_selection:
            obj = next((o for o in state['objects'] if o['id'] == state['target']), None)
            if state['state'] == 'SELECTED' and obj:
                self.targets.publish(String(data=json.dumps(dict(request_id=state['request_id'],
                    selection_id=state['selection_id'], object=obj, reason=state['reason']))))
            self.last_selection = state['selection_id']


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = Controller()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if node:
            if node.log:
                node.log.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
