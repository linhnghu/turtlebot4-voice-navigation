#!/usr/bin/env python3
"""Record RViz Publish Point clicks as map goals without moving the robot."""
from pathlib import Path
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PointStamped
import yaml


class GoalRecorder(Node):
    def __init__(self):
        super().__init__('record_map_goals')
        self.path = Path(self.declare_parameter('output_file', 'my_goals.yaml').value).expanduser()
        self.yaw = float(self.declare_parameter('yaw', 0.0).value)
        self.goals = []
        self.create_subscription(PointStamped, '/clicked_point', self.clicked, 10)
        self.get_logger().info('Use Publish Point in RViz (fixed frame map). Each click saves a goal.')

    def clicked(self, msg):
        if msg.header.frame_id != 'map' or not all(math.isfinite(v) for v in
                                                    (msg.point.x, msg.point.y, self.yaw)):
            self.get_logger().error('Click must contain finite coordinates in frame map.')
            return
        goal = dict(name=f'Goal {len(self.goals) + 1}', x=round(msg.point.x, 3),
                    y=round(msg.point.y, 3), yaw=self.yaw)
        self.goals.append(goal)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(dict(frame_id='map', goals=self.goals), sort_keys=False))
        self.get_logger().info(f'{goal} -> {self.path}')


def main():
    rclpy.init()
    node = GoalRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
