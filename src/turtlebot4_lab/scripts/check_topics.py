#!/usr/bin/env python3
"""Check actual messages, simulation time and transforms without moving the robot."""
import argparse
import json
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=10.0)
    parser.add_argument('--require-map', action='store_true')
    args = parser.parse_args()
    rclpy.init()
    node = Node('turtlebot4_lab_check')
    counts = {'scan': 0, 'odom': 0, 'clock': 0, 'map': 0}
    last = {}
    def receive(name, msg):
        counts[name] += 1
        last[name] = msg
    subscriptions = []
    map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
    for name, message, qos in [('scan', LaserScan, qos_profile_sensor_data),
                               ('odom', Odometry, qos_profile_sensor_data),
                               ('clock', Clock, qos_profile_sensor_data),
                               ('map', OccupancyGrid, map_qos)]:
        subscriptions.append(node.create_subscription(
            message, '/' + name, lambda msg, name=name: receive(name, msg), qos))
    tf = Buffer()
    listener = TransformListener(tf, node)
    start = time.monotonic()
    while time.monotonic() - start < args.duration:
        rclpy.spin_once(node, timeout_sec=0.1)
    scan = last.get('scan')
    valid_ranges = sum(math.isfinite(r) and scan.range_min <= r <= scan.range_max
                       for r in scan.ranges) if scan else 0
    useful_ranges = sum(math.isfinite(r) and scan.range_min + 0.05 < r <= scan.range_max
                        for r in scan.ranges) if scan else 0
    odom = last.get('odom')
    odom_valid = bool(odom and all(math.isfinite(v) for v in
                                 (odom.pose.pose.position.x, odom.pose.pose.position.y)))
    subscribers = node.get_subscriptions_info_by_topic('/cmd_vel')
    accepts_twist = any(info.topic_type == 'geometry_msgs/msg/Twist' for info in subscribers)
    transforms = {'odom_to_base_link': bool(tf.can_transform('odom', 'base_link', rclpy.time.Time()))}
    if args.require_map:
        transforms['map_to_base_link'] = bool(tf.can_transform('map', 'base_link', rclpy.time.Time()))
    grid = last.get('map')
    known = sum(cell >= 0 for cell in grid.data) if grid else 0
    clock = last.get('clock')
    clock_ok = bool(clock and (clock.clock.sec > 0 or clock.clock.nanosec > 0))
    passed = (counts['scan'] > 1 and useful_ranges > 0 and counts['odom'] > 1
              and odom_valid and counts['clock'] > 1 and clock_ok
              and accepts_twist and all(transforms.values())
              and (not args.require_map or known > 0))
    print(json.dumps({'passed': passed, 'duration_wall_s': args.duration,
                      'messages': counts, 'finite_lidar_ranges': valid_ranges,
                      'lidar_ranges_above_minimum': useful_ranges,
                      'cmd_vel_twist_subscribers': sum(
                          info.topic_type == 'geometry_msgs/msg/Twist' for info in subscribers),
                      'transforms': transforms, 'map_known_cells': known,
                      'odom_xy': [odom.pose.pose.position.x, odom.pose.pose.position.y]
                      if odom else None}, indent=2))
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
