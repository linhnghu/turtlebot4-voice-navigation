import json
import math
import signal
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Point, Pose2D, Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .fusion import FusionEngine


class Controller(Node):
    def __init__(self):
        super().__init__('hri_fusion')
        self.engine = FusionEngine(float(self.declare_parameter('input_ttl', 3.0).value))
        if not math.isfinite(self.engine.ttl) or self.engine.ttl <= 0:
            raise ValueError('input_ttl must be finite and positive')
        self.pose, self.pose_time = None, 0.0
        self.camera_required = bool(self.declare_parameter('camera_required', False).value)
        self.max_speed = float(self.declare_parameter('max_speed', .65).value)
        self.enforce_bounds = bool(self.declare_parameter('enforce_bounds', False).value)
        self.camera_time = 0.
        self.camera_inhibit = True
        self.camera_label = 'waiting'
        self.target = Point(x=2.0, y=4.0)
        self.cmd = self.create_publisher(Twist, '/hri/cmd_vel', 10)
        self.status = self.create_publisher(String, '/hri/decision', 10)
        self.create_subscription(String, '/hri/input', self.snapshot, 10)
        self.create_subscription(String, '/hri/voice', lambda m: self.single('voice', m), 10)
        self.create_subscription(String, '/hri/gesture', lambda m: self.single('gesture', m), 10)
        self.create_subscription(Pose2D, '/hri/pose', self.on_pose, 10)
        self.create_subscription(Point, '/hri/target', self.on_target, 10)
        self.create_subscription(String, '/hri/camera_status', self.on_camera, 1)
        self.create_service(Trigger, '/hri/reset_stop', self.reset)
        self.create_timer(.05, self.tick)
        self.previous = None

    def decode(self, msg):
        if len(msg.data) > 4096:
            raise ValueError('input exceeds 4096 bytes')
        return json.loads(msg.data)

    def snapshot(self, msg):
        try:
            self.engine.snapshot(self.decode(msg))
        except (ValueError, TypeError):
            self.engine.fail_stop('invalid_json')
        self.tick()

    def single(self, channel, msg):
        try:
            self.engine.ingest(channel, self.decode(msg))
        except (ValueError, TypeError):
            self.engine.fail_stop('invalid_json')
        self.tick()

    def on_pose(self, msg):
        if all(math.isfinite(v) for v in (msg.x, msg.y, msg.theta)):
            self.pose, self.pose_time = msg, time.monotonic()

    def on_camera(self, msg):
        if not self.camera_required:
            return
        try:
            data = self.decode(msg)
            if (not isinstance(data, dict) or type(data.get('healthy')) is not bool
                    or type(data.get('motion_inhibit')) is not bool):
                raise ValueError('invalid camera health')
            self.camera_time = time.monotonic()
            self.camera_inhibit = data['motion_inhibit']
            self.camera_label = str(data.get('label', ''))
            if not data['healthy']:
                self.engine.fail_stop('camera_fault')
        except (ValueError, TypeError):
            self.engine.fail_stop('invalid_camera_status')
        self.tick()

    def on_target(self, msg):
        if all(math.isfinite(v) for v in (msg.x, msg.y)) and 0 <= msg.x <= 8 and 0 <= msg.y <= 6:
            self.target = msg

    def reset(self, request, response):
        if self.camera_required and (time.monotonic() - self.camera_time > .6
                                     or self.camera_label == 'Open Palm'):
            response.success = False
            response.message = 'Lower your palm and restore camera frames before reset.'
            return response
        self.engine.reset()
        self.tick()
        response.success, response.message = True, 'Reset complete; send a fresh command.'
        return response

    def tick(self):
        camera_stale = self.camera_required and time.monotonic() - self.camera_time > .6
        if camera_stale and self.camera_time:
            self.engine.fail_stop('camera_lost')
        result = self.engine.decision()
        velocity = Twist()
        behavior = result.action
        if result.action == 'stop':
            behavior = 'stop'
        elif self.camera_required and (camera_stale or self.camera_inhibit):
            behavior = 'waiting_for_camera' if camera_stale else 'checking_gesture'
        elif self.pose is None or time.monotonic() - self.pose_time > .5:
            behavior = 'waiting_for_pose'
        elif result.action == 'forward':
            velocity.linear.x = self.max_speed
        elif result.action == 'come':
            dx, dy = self.target.x - self.pose.x, self.target.y - self.pose.y
            distance = math.hypot(dx, dy)
            if distance < .4:
                behavior = 'arrived'
            else:
                angle = math.atan2(dy, dx) - self.pose.theta
                error = math.atan2(math.sin(angle), math.cos(angle))
                velocity.angular.z = max(-1.8, min(1.8, 2.5 * error))
                velocity.linear.x = min(self.max_speed, distance * .7) if abs(error) < .6 else 0.0
        if self.enforce_bounds and self.pose and velocity.linear.x > 0:
            x = self.pose.x + math.cos(self.pose.theta) * velocity.linear.x * .5
            y = self.pose.y + math.sin(self.pose.theta) * velocity.linear.x * .5
            if not (.35 < x < 7.65 and .35 < y < 5.65):
                velocity = Twist()
                behavior = 'boundary_stop'
        self.cmd.publish(velocity)
        active = self.engine.active()
        state = dict(action=result.action, reason=result.reason, behavior=behavior,
                     latched=self.engine.latched, linear=velocity.linear.x,
                     angular=velocity.angular.z,
                     camera=self.camera_label if self.camera_required else 'disabled',
                     voice=active.get('voice', ('', 0))[0],
                     gesture=active.get('gesture', ('', 0))[0])
        self.status.publish(String(data=json.dumps(state)))
        key = (result.action, result.reason, behavior)
        if key != self.previous:
            self.get_logger().info(json.dumps(state))
            self.previous = key


def main(args=None):
    rclpy.init(args=args)
    node = Controller()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if rclpy.ok():
            node.cmd.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
