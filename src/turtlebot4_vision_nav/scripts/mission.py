#!/usr/bin/env python3
"""Send at least three NavigateToPose goals in sequence, with no manual driving."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from irobot_create_msgs.action import Undock
from irobot_create_msgs.msg import DockStatus, HazardDetectionVector
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformListener
from visualization_msgs.msg import Marker, MarkerArray
import yaml


class Mission(Node):
    def __init__(self):
        super().__init__('autonomous_vision_mission')
        self.goals_file = Path(self.declare_parameter('goals_file', '').value)
        self.output = Path(self.declare_parameter('output_dir', 'artifacts/vision_demo').value)
        self.timeout = float(self.declare_parameter('goal_timeout', 180.0).value)
        self.dwell = float(self.declare_parameter('dwell_seconds', 4.0).value)
        self.require_yolo = self.declare_parameter('require_yolo', True).value
        self.output.mkdir(parents=True, exist_ok=True)
        config = yaml.safe_load(self.goals_file.read_text())
        self.goals = config['goals']
        if config.get('frame_id') != 'map' or len(self.goals) < 3:
            raise ValueError('Provide at least 3 goals in frame map.')
        for goal in self.goals:
            if not all(math.isfinite(float(goal[k])) for k in ('x', 'y', 'yaw')):
                raise ValueError('Goal coordinates and yaw must be finite.')
        self.latest = {}
        self.bump_count = 0
        self.monitor_collisions = False
        self.state_pub = self.create_publisher(String, '/mission/state', self.latched())
        self.marker_pub = self.create_publisher(MarkerArray, '/mission/goals', self.latched())
        for key, topic, message, qos in [
                ('map', '/map', OccupancyGrid, self.latched()),
                ('amcl', '/amcl_pose', PoseWithCovarianceStamped, self.latched()),
                ('dock', '/dock_status', DockStatus, qos_profile_sensor_data),
                ('ground_truth', '/sim_ground_truth_pose', Odometry, qos_profile_sensor_data),
                ('yolo', '/yolo/ready', Bool, self.latched())]:
            self.create_subscription(message, topic,
                                     lambda msg, key=key: self.latest.__setitem__(key, msg), qos)
        self.create_subscription(HazardDetectionVector, '/hazard_detection', self.hazard,
                                 qos_profile_sensor_data)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.navigation = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.undock = ActionClient(self, Undock, '/undock')
        self.current_handle = None
        self.last_feedback = 0.0
        self.report = dict(started=datetime.now(timezone.utc).isoformat(),
                           goals_file=str(self.goals_file), frame_id='map', goals=[],
                           navigation_interface='/navigate_to_pose', manual_velocity_commands=False)

    @staticmethod
    def latched():
        return QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def hazard(self, msg):
        self.bump_count += sum(d.type == 1 for d in msg.detections)

    def state(self, state, **fields):
        data = dict(state=state, **fields)
        self.state_pub.publish(String(data=json.dumps(data)))
        self.get_logger().info(json.dumps(data))

    def save(self):
        self.report['bumper_detections'] = self.bump_count
        path = self.output / 'mission_results.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.report, indent=2))
        temp.replace(path)

    def wait(self, future, timeout=15):
        deadline = time.monotonic() + timeout
        while rclpy.ok() and not future.done():
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.monitor_collisions and self.bump_count:
                raise RuntimeError('Bumper contact detected; canceling mission.')
            if time.monotonic() >= deadline:
                raise RuntimeError('Timed out waiting for action/service response.')
        if not rclpy.ok():
            raise KeyboardInterrupt
        return future.result()

    def pause(self, seconds):
        end = time.monotonic() + seconds
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)

    def ready(self):
        self.state('WAITING_FOR_LOCALIZATION_AND_NAV2')
        for name in ('amcl', 'map_server', 'controller_server', 'planner_server', 'bt_navigator'):
            client = self.create_client(GetState, f'/{name}/get_state')
            if not client.wait_for_service(timeout_sec=90):
                raise RuntimeError(f'{name} is unavailable. Keep simulation running.')
            deadline = time.monotonic() + 90
            while self.wait(client.call_async(GetState.Request())).current_state.id != 3:
                self.pause(0.3)
                if time.monotonic() > deadline:
                    raise RuntimeError(f'{name} did not become active.')
            self.destroy_client(client)
        deadline = time.monotonic() + 120
        while True:
            rclpy.spin_once(self, timeout_sec=0.1)
            localized = (all(k in self.latest for k in ('map', 'amcl', 'dock')) and
                         self.buffer.can_transform('map', 'base_link', rclpy.time.Time()))
            vision_ready = not self.require_yolo or (self.latest.get('yolo') and self.latest['yolo'].data)
            if localized and vision_ready:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('No localization/map/camera YOLO readiness. Check node logs.')
        grid = self.latest['map']
        for goal in self.goals:
            x = math.floor((goal['x'] - grid.info.origin.position.x) / grid.info.resolution)
            y = math.floor((goal['y'] - grid.info.origin.position.y) / grid.info.resolution)
            if not (0 <= x < grid.info.width and 0 <= y < grid.info.height):
                raise ValueError(f'Goal outside map: {goal}')
            value = grid.data[y * grid.info.width + x]
            if value < 0 or value >= 50:
                raise ValueError(f'Goal is unknown/occupied on the loaded map: {goal}')
        self.mark_goals()
        self.state('READY', goals=len(self.goals))

    def mark_goals(self):
        markers = MarkerArray()
        for i, goal in enumerate(self.goals):
            for text in (False, True):
                m = Marker()
                m.header.frame_id = 'map'
                m.ns = 'mission_goals'
                m.id = i * 2 + int(text)
                m.type = Marker.TEXT_VIEW_FACING if text else Marker.SPHERE
                m.action = Marker.ADD
                m.pose.position.x, m.pose.position.y = float(goal['x']), float(goal['y'])
                m.pose.position.z = 0.5 if text else 0.12
                m.pose.orientation.w = 1.0
                m.scale.x = m.scale.y = m.scale.z = 0.28
                m.color.r, m.color.g, m.color.b, m.color.a = 0.1, 1.0, 0.3, 1.0
                m.text = str(goal.get('name', f'Goal {i + 1}'))
                markers.markers.append(m)
        self.marker_pub.publish(markers)

    def feedback(self, msg):
        if time.monotonic() - self.last_feedback > 2:
            self.last_feedback = time.monotonic()
            self.state('NAVIGATING', goal=self.goal_number, total=len(self.goals),
                       distance_remaining=round(msg.feedback.distance_remaining, 2))

    def run(self):
        self.ready()
        if self.latest['dock'].is_docked:
            self.state('UNDOCKING')
            if not self.undock.wait_for_server(timeout_sec=15):
                raise RuntimeError('Undock action is unavailable.')
            handle = self.wait(self.undock.send_goal_async(Undock.Goal()))
            if not handle.accepted:
                raise RuntimeError('Undock was rejected.')
            self.current_handle = handle
            result = self.wait(handle.get_result_async(), 75)
            self.current_handle = None
            if result.status != 4 or result.result.is_docked:
                raise RuntimeError(f'Undock failed: status {result.status}')
        self.bump_count = 0
        self.monitor_collisions = True
        if not self.navigation.wait_for_server(timeout_sec=15):
            raise RuntimeError('NavigateToPose action is unavailable.')
        for i, target in enumerate(self.goals):
            self.goal_number = i + 1
            goal = NavigateToPose.Goal()
            goal.pose = PoseStamped()
            goal.pose.header.frame_id = 'map'
            goal.pose.header.stamp = self.get_clock().now().to_msg()
            goal.pose.pose.position.x = float(target['x'])
            goal.pose.pose.position.y = float(target['y'])
            goal.pose.pose.orientation.z = math.sin(float(target['yaw']) / 2)
            goal.pose.pose.orientation.w = math.cos(float(target['yaw']) / 2)
            self.state('SENDING_GOAL', goal=i + 1, total=len(self.goals), target=target)
            handle = self.wait(self.navigation.send_goal_async(goal, feedback_callback=self.feedback))
            if not handle.accepted:
                raise RuntimeError(f'Goal {i + 1} was rejected.')
            self.current_handle = handle
            started = time.monotonic()
            result = self.wait(handle.get_result_async(), self.timeout)
            self.current_handle = None
            transform = self.buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            p = transform.transform.translation
            record = dict(goal=i + 1, target=target, status=result.status,
                          result='SUCCEEDED' if result.status == 4 else 'FAILED',
                          wall_seconds=round(time.monotonic() - started, 2),
                          localized_xy=[p.x, p.y])
            if 'ground_truth' in self.latest:
                g = self.latest['ground_truth'].pose.pose.position
                record['gazebo_xy'] = [g.x, g.y]
                record['goal_error_gazebo_m'] = math.hypot(g.x - target['x'], g.y - target['y'])
            self.report['goals'].append(record)
            self.save()
            if result.status != 4:
                raise RuntimeError(f'Goal {i + 1} failed with status {result.status}; mission stopped.')
            self.state('GOAL_SUCCEEDED', goal=i + 1, total=len(self.goals))
            self.pause(self.dwell)
        self.report['passed'] = True
        self.report['finished'] = datetime.now(timezone.utc).isoformat()
        self.save()
        self.state('MISSION_COMPLETE', succeeded=len(self.goals), total=len(self.goals))
        self.pause(1)


def main():
    rclpy.init()
    node = None
    try:
        node = Mission()
        node.run()
    except (Exception, KeyboardInterrupt) as error:
        if node:
            if node.current_handle and rclpy.ok():
                try:
                    node.wait(node.current_handle.cancel_goal_async(), 10)
                except Exception:
                    pass
            node.report.update(passed=False, error=str(error) or 'Interrupted')
            node.save()
            if rclpy.ok():
                node.state('MISSION_FAILED', error=node.report['error'])
        else:
            print(f'Mission setup failed: {error}', file=sys.stderr)
        raise SystemExit(1)
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
