"""Terminal alternative to an STT adapter; publishes exactly one utterance per line."""
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main(args=None):
    rclpy.init(args=args)
    node = Node('engagement_text_input')
    publisher = node.create_publisher(String, '/engagement/speech', 10)
    try:
        while rclpy.ok():
            text = input('Lời chào (Hello robot / Excuse me / Xin chào; Ctrl-D để thoát): ')
            deadline = time.monotonic() + 2.
            while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.05)
            if publisher.get_subscription_count() == 0:
                print('Chưa có controller nhận topic /engagement/speech.')
                continue
            publisher.publish(String(data=text))
            rclpy.spin_once(node, timeout_sec=.1)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
