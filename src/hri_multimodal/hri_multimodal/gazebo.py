"""Gazebo odometry adapter, command watchdog, and visual caller target."""
from concurrent.futures import ThreadPoolExecutor
import math
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Point, Pose2D, Twist
from nav_msgs.msg import Odometry


class GazeboAdapter(Node):
    def __init__(self):
        super().__init__('hri_gazebo_adapter')
        self.last_cmd = self.last_odom = 0.
        self.velocity = Twist()
        self.publisher = self.create_publisher(Twist, '/hri/gazebo/cmd_vel', 1)
        self.pose_pub = self.create_publisher(Pose2D, '/hri/pose', 10)
        self.create_subscription(Twist, '/hri/cmd_vel', self.command, 1)
        self.create_subscription(Odometry, '/hri/gazebo/odom', self.odometry, 10)
        self.create_subscription(Point, '/hri/target', self.target, 1)
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.target_job = None
        self.create_timer(.05, self.tick)

    def command(self, msg):
        if all(math.isfinite(v) for v in (msg.linear.x, msg.angular.z)):
            self.velocity = msg
            self.last_cmd = time.monotonic()
        else:
            self.velocity = Twist()

    def odometry(self, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        if all(math.isfinite(v) for v in (p.x, p.y, yaw)):
            # Fortress DiffDrive odometry starts at zero at the model's spawn.
            self.pose_pub.publish(Pose2D(x=p.x+1.2, y=p.y+1.2, theta=yaw))
            self.last_odom = time.monotonic()

    def target(self, msg):
        if not all(math.isfinite(v) for v in (msg.x, msg.y)) or not (0 <= msg.x <= 8 and 0 <= msg.y <= 6):
            return
        if self.target_job and not self.target_job.done():
            return
        self.target_job = self.worker.submit(subprocess.run, [
            'ign', 'service', '-s', '/world/hri_lab/set_pose',
            '--reqtype', 'ignition.msgs.Pose', '--reptype', 'ignition.msgs.Boolean',
            '--timeout', '1000', '--req',
            f'name: "caller" position {{x: {msg.x} y: {msg.y} z: 0}}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

    def tick(self):
        now = time.monotonic()
        fresh = now-self.last_cmd < .3 and now-self.last_odom < .5
        self.publisher.publish(self.velocity if fresh else Twist())

    def close(self):
        if rclpy.ok():
            self.publisher.publish(Twist())
        self.worker.shutdown(wait=True, cancel_futures=True)


def main(args=None):
    rclpy.init(args=args)
    node = GazeboAdapter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
