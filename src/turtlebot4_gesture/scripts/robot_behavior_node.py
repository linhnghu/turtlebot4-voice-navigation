#!/usr/bin/env python3
"""Confirm gesture selections and control bounded motion using odometry feedback."""
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from irobot_create_msgs.msg import HazardDetection, HazardDetectionVector

from gesture_core import Controller


class RobotBehaviorNode(Node):
    def __init__(self):
        super().__init__('robot_behavior_node')
        self.declare_parameter('output_dir', '')
        self.declare_parameter('signal_timeout', 0.8)
        self.controller = Controller(float(self.get_parameter('signal_timeout').value))
        self.pose = None
        self.odom_at = self.scan_at = -math.inf
        self.sim_stamp = None
        self.clearance = 0.0
        self.hazard_active = False
        self.started_at = None
        self.last_status = ''
        self.velocity = self.create_publisher(Twist, '/cmd_vel', 1)
        self.state = self.create_publisher(String, '/gesture_behavior/status', 1)
        self.create_subscription(String, '/detected_gesture', self.gesture,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.create_subscription(Odometry, '/odom', self.odometry, qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.scan, qos_profile_sensor_data)
        self.create_subscription(HazardDetectionVector, '/hazard_detection', self.hazard,
                                 qos_profile_sensor_data)
        output = self.get_parameter('output_dir').value
        self.log_file = None
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            self.log_file = (Path(output) / 'behavior.jsonl').open('a', buffering=1)
        # Wall-clock timer/watchdog continues when Gazebo /clock pauses.
        self.create_timer(0.05, self.control)

    def gesture(self, message):
        self.controller.observe(message.data, time.monotonic())
        if message.data in ('Open_Palm', 'Closed_Fist', 'Camera_Error', 'Shutdown'):
            if message.data in ('Camera_Error', 'Shutdown'):
                self.controller.stop('SIGNAL LOST: camera stopped', clear=True)
            self.velocity.publish(Twist())

    def odometry(self, message):
        stamp = (message.header.stamp.sec, message.header.stamp.nanosec)
        if stamp == self.sim_stamp:
            return  # Replayed/frozen simulation data is not fresh feedback.
        self.sim_stamp = stamp
        p, q = message.pose.pose.position, message.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1-2*(q.y*q.y + q.z*q.z))
        if all(math.isfinite(v) for v in (p.x, p.y, yaw)):
            self.pose = p.x, p.y, yaw
            self.odom_at = time.monotonic()

    def scan(self, message):
        valid = [r for r in message.ranges if math.isfinite(r) and message.range_min <= r <= message.range_max]
        # Positive infinity means no return within range. NaN/-inf alone is invalid.
        free = any(r == math.inf for r in message.ranges)
        self.clearance = min(valid) if valid else (message.range_max if free else 0.0)
        self.scan_at = time.monotonic()

    def hazard(self, message):
        # BACKUP_LIMIT is an early warning at <= 0.05 m remaining buffer,
        # also present at startup. Upstream motion_control enforces the actual
        # zero-buffer reverse limit; the warning must not prohibit all motion.
        self.hazard_active = any(d.type != HazardDetection.BACKUP_LIMIT for d in message.detections)
        if self.hazard_active:
            self.controller.stop('BLOCKED: bumper/cliff hazard', clear=True)
            self.velocity.publish(Twist())

    def control(self):
        now = time.monotonic()
        reason = ''
        if now-self.odom_at > 0.6 or now-self.scan_at > 0.8:
            reason = 'waiting for fresh odometry / lidar'
        elif self.clearance < 0.55:
            reason = 'obstacle closer than 0.55 m'
        elif self.hazard_active:
            reason = 'bumper/cliff hazard'
        elif self.pose and math.hypot(*self.pose[:2]) > 4.0:
            reason = '4 m workspace limit'
        if self.controller.active and self.started_at is None:
            self.started_at = now
        if self.started_at is not None and now-self.started_at > 70:
            reason = 'behavior exceeded 70 seconds'
        linear, angular = self.controller.tick(now, self.pose, not reason, reason)
        if not self.controller.active:
            self.started_at = None
        message = Twist()
        message.linear.x, message.angular.z = linear, angular
        self.velocity.publish(message)
        status = self.controller.status
        self.state.publish(String(data=status))
        if status != self.last_status:
            self.get_logger().info(status)
            if self.log_file:
                self.log_file.write(json.dumps({'wall_time': time.time(), 'status': status,
                                               'pose': self.pose}) + '\n')
            self.last_status = status


def main():
    rclpy.init()
    node = RobotBehaviorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.velocity.publish(Twist())
        if node.log_file:
            node.log_file.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
