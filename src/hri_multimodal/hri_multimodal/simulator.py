"""Kinematic 2D simulation: metres, radians, bounded lab, velocity watchdog."""
import math
import signal
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Pose2D, Twist


class Simulator(Node):
    def __init__(self):
        super().__init__('hri_simulator')
        self.pose = Pose2D(x=1.2, y=1.2, theta=0.0)
        self.velocity = Twist()
        self.last_command = 0.0
        self.last_tick = time.monotonic()
        self.publisher = self.create_publisher(Pose2D, '/hri/pose', 10)
        self.create_subscription(Twist, '/hri/cmd_vel', self.command, 10)
        self.create_timer(.02, self.tick)

    def command(self, msg):
        if not all(math.isfinite(v) for v in (msg.linear.x, msg.angular.z)):
            self.velocity = Twist()
            return
        self.velocity = msg
        self.last_command = time.monotonic()

    def tick(self):
        now = time.monotonic()
        dt = min(.1, now - self.last_tick)
        self.last_tick = now
        if now - self.last_command <= .3:
            v = max(-.65, min(.65, self.velocity.linear.x))
            w = max(-1.8, min(1.8, self.velocity.angular.z))
            self.pose.theta = math.atan2(math.sin(self.pose.theta + w * dt),
                                         math.cos(self.pose.theta + w * dt))
            x = self.pose.x + math.cos(self.pose.theta) * v * dt
            y = self.pose.y + math.sin(self.pose.theta) * v * dt
            # A circular robot of radius .22m cannot leave the lab.
            if .22 <= x <= 7.78 and .22 <= y <= 5.78:
                self.pose.x, self.pose.y = x, y
        self.publisher.publish(self.pose)


def main(args=None):
    rclpy.init(args=args)
    node = Simulator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
