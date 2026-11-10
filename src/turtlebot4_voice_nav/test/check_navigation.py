#!/usr/bin/env python3
"""Exercise the running Gazebo/Nav2 system via text; never labels this as ASR."""
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from irobot_create_msgs.msg import HazardDetectionVector
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from turtlebot4_voice_nav.navigator import latched


def main():
    rclpy.init()
    node = Node('check_voice_navigation')
    pub = node.create_publisher(String, '/voice_nav/command', 10)
    events, records = [], []
    latest = dict(bumpers=0, odom=None, scan=None)
    node.create_subscription(String, '/voice_nav/status', lambda m: events.append(json.loads(m.data)), latched())
    node.create_subscription(Odometry, '/odom', lambda m: latest.update(odom=m), qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan', lambda m: latest.update(scan=m), qos_profile_sensor_data)
    node.create_subscription(HazardDetectionVector, '/hazard_detection',
                             lambda m: latest.update(bumpers=latest['bumpers'] + sum(d.type == 1 for d in m.detections)),
                             qos_profile_sensor_data)
    output = Path('artifacts/voice_nav/navigation_validation.json')

    def wait(predicate, timeout):
        end = time.monotonic()+timeout
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.1)
            if predicate():
                return
        raise RuntimeError('Timeout; last events: ' + str(events[-3:]))

    def send(text, state, timeout=240):
        start = len(events)
        pub.publish(String(data=text))
        wait(lambda: any(d['state'] == state for d in events[start:]), timeout)
        found = events[start:]
        records.append(dict(text=text, expected=state, events=found))
        return found

    try:
        wait(lambda: events and events[-1]['state'] == 'READY' and latest['scan'] is not None
             and pub.get_subscription_count() > 0, 150)
        ranges = [r for r in latest['scan'].ranges if math.isfinite(r) and r > latest['scan'].range_min+.03]
        assert len(ranges) > 100, 'LiDAR is not providing useful map ranges'
        send('Đi đến khu vực Z', 'UNKNOWN_REGION', 5)
        send('không đi đến A', 'UNKNOWN_COMMAND', 5)
        route = send('Di chuyển từ khu vực A đến khu vực B', 'SUCCEEDED', 300)
        reached = [d['completed'][-1] for d in route if d['state'] == 'WAYPOINT_SUCCEEDED']
        assert reached == ['A', 'B'], reached
        assert len([d for d in route if d['state'] == 'ACCEPTED']) == 1
        send('Đi đến phòng thí nghiệm', 'SUCCEEDED')
        send('Đi đến hành lang', 'SUCCEEDED')
        # Start another route, then cancel and observe the matching action finish.
        send('Đi từ A đến B', 'NAVIGATING', 10)
        send('Đi đến C', 'BUSY', 5)
        send('dừng lại', 'CANCELED', 20)
        odom = latest['odom']
        wait(lambda: latest['odom'] is not odom and
             abs(latest['odom'].twist.twist.linear.x) < .03 and
             abs(latest['odom'].twist.twist.angular.z) < .05, 10)
        assert latest['bumpers'] == 0, 'Bumper contact occurred during navigation'
        report = dict(passed=True, input='text_topic_not_speech', useful_scan_ranges=len(ranges),
                      bumper_detections=latest['bumpers'], checks=records)
    except Exception as exc:
        pub.publish(String(data='dừng lại'))
        report = dict(passed=False, input='text_topic_not_speech', error=str(exc), checks=records)
        raise
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False))
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
