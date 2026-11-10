#!/usr/bin/env python3
"""Wait for a live simulation and undock before starting keyboard teleop."""
import time

import rclpy
from action_msgs.msg import GoalStatus
from irobot_create_msgs.action import Undock
from irobot_create_msgs.msg import DockStatus
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan


def main():
    rclpy.init()
    node = rclpy.create_node('turtlebot4_teleop_prepare')
    latest = {}
    stamps = {}
    clock_values = set()

    def receive(name, msg):
        latest[name] = msg
        stamps[name] = time.monotonic()
        if name == 'clock':
            clock_values.add((msg.clock.sec, msg.clock.nanosec))

    subscriptions = [node.create_subscription(
        message, '/' + name, lambda msg, name=name: receive(name, msg),
        qos_profile_sensor_data)
        for name, message in [('scan', LaserScan), ('odom', Odometry),
                              ('clock', Clock), ('dock_status', DockStatus)]]
    action = ActionClient(node, Undock, '/undock')

    def wait(future, seconds):
        deadline = time.monotonic() + seconds
        while not future.done():
            rclpy.spin_once(node, timeout_sec=0.1)
            if time.monotonic() >= deadline:
                raise RuntimeError('Undock timed out. Check Gazebo is running and not paused.')
        return future.result()

    try:
        print('Waiting for live sensors and the robot /cmd_vel subscriber...', flush=True)
        deadline = time.monotonic() + 40
        while True:
            rclpy.spin_once(node, timeout_sec=0.1)
            now = time.monotonic()
            accepts_twist = any(info.topic_type == 'geometry_msgs/msg/Twist'
                                for info in node.get_subscriptions_info_by_topic('/cmd_vel'))
            if (all(now - stamps.get(name, 0) < 2 for name in
                    ('scan', 'odom', 'clock', 'dock_status')) and len(clock_values) > 1
                    and accepts_twist):
                break
            if now >= deadline:
                raise RuntimeError('No live simulator. Keep ./run_turtlebot4.bash '
                                   'mode:=mapping running in another terminal and press Play in Gazebo.')
        if not latest['dock_status'].is_docked:
            print('Robot is already undocked.', flush=True)
            return
        if not action.wait_for_server(timeout_sec=10):
            raise RuntimeError('/undock is unavailable. Check simulator and ROS domain.')
        print('Undocking robot...', flush=True)
        handle = wait(action.send_goal_async(Undock.Goal()), 10)
        if not handle.accepted:
            raise RuntimeError('Robot rejected the undock goal.')
        future = handle.get_result_async()
        try:
            result = wait(future, 60)
        except RuntimeError:
            wait(handle.cancel_goal_async(), 10)
            raise
        if result.status != GoalStatus.STATUS_SUCCEEDED or result.result.is_docked:
            raise RuntimeError(f'Undock failed (status {result.status}). Try restarting mapping.')
        print('Undock SUCCEEDED.', flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyboardInterrupt) as error:
        raise SystemExit(str(error) or 'Teleop preparation canceled.')
