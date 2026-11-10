"""ROS transport and greeting events for the pure engagement engine."""
from dataclasses import fields
import json
import signal
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .core import Config, EngagementEngine


class Controller(Node):
    def __init__(self):
        super().__init__('engagement_controller')
        defaults = Config()
        values = {f.name: self.declare_parameter(f.name, getattr(defaults, f.name)).value
                  for f in fields(defaults)}
        self.engine = EngagementEngine(Config(**values))
        self.greeting = self.declare_parameter('greeting', 'Xin chào! Tôi có thể giúp gì cho bạn?').value
        self.status = self.create_publisher(String, '/engagement/state', 10)
        self.response = self.create_publisher(String, '/engagement/response', 10)
        self.events = self.create_publisher(String, '/engagement/events', 10)
        self.create_subscription(String, '/engagement/vision', self.on_vision, 1)
        self.create_subscription(String, '/engagement/speech', self.on_speech, 10)
        self.create_service(Trigger, '/engagement/reset', self.reset)
        self.create_timer(.05, self.tick)
        self.previous = None
        self.last_sequence = 0

    def reset(self, request, response):
        self.engine.reset()
        self.last_sequence = 0
        self.previous = None
        self.tick()
        response.success, response.message = True, 'FSM reset; waiting for fresh observations.'
        return response

    @staticmethod
    def decode(message):
        if len(message.data) > 4096:
            raise ValueError('message exceeds 4096 characters')
        payload = json.loads(message.data)
        if not isinstance(payload, dict):
            raise ValueError('expected a JSON object')
        return payload

    def on_vision(self, message):
        now = time.monotonic()
        try:
            data = self.decode(message)
            self.engine.observe(now, **{k: data[k] for k in
                                      ('healthy', 'face_present', 'facing', 'hand_raised')})
        except (ValueError, TypeError, KeyError) as exc:
            self.engine.observe(now, healthy=False, face_present=False, facing=False, hand_raised=False)
            self.get_logger().warning(f'Invalid vision observation: {exc}')
        self.tick()

    def on_speech(self, message):
        try:
            # Plain text is the text-mode contract; STT adapters may send a JSON object.
            if len(message.data) > 4096:
                raise ValueError('speech exceeds 4096 characters')
            if message.data.lstrip().startswith('{'):
                data = self.decode(message)
                text, confidence = data.get('text'), data.get('confidence', 1.)
            else:
                text, confidence = message.data, 1.
            accepted = self.engine.speech(time.monotonic(), text, confidence)
            if accepted:
                self.get_logger().info(f'Greeting detected: {text}')
        except (ValueError, TypeError) as exc:
            self.get_logger().warning(f'Invalid speech input: {exc}')
        self.tick()

    def tick(self):
        state = self.engine.update(time.monotonic())
        state['stamp'] = self.get_clock().now().nanoseconds / 1e9
        self.status.publish(String(data=json.dumps(state)))
        key = (state['state'], state['reason'])
        if key != self.previous:
            self.events.publish(String(data=json.dumps(state)))
            self.get_logger().info(f"{state['state']}: {state['reason']}")
            self.previous = key
        if state['sequence'] != self.last_sequence:
            self.response.publish(String(data=self.greeting))
            self.get_logger().info(self.greeting)
            self.last_sequence = state['sequence']


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
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
