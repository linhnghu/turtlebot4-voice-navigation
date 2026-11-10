"""Physical webcam -> measured colored scene + stable index-finger ray."""
import json
from pathlib import Path
import signal
import time

import cv2
import mediapipe as mp
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from .live_vision import PointingFilter, SceneFilter, square_frame, without_hands
from .perception import detect_objects


class Camera(Node):
    def __init__(self):
        super().__init__('reference_camera')
        self.capture = self.hands = self.log = None
        self.source = str(self.declare_parameter('scene_source', 'camera').value)
        if self.source not in ('camera', 'simulation'):
            raise ValueError('scene_source must be camera or simulation')
        index = int(self.declare_parameter('camera_index', 0).value)
        self.scene_pub = self.create_publisher(String, '/reference/scene', 1)
        self.point_pub = self.create_publisher(String, '/reference/pointing', 1)
        self.status_pub = self.create_publisher(String, '/reference/camera_status', 1)
        self.image_pub = self.create_publisher(CompressedImage, '/reference/image/compressed', 1)
        self.scene_filter, self.point_filter = SceneFilter(), PointingFilter()
        self.frames = 0
        output = str(self.declare_parameter('output_dir', '').value)
        try:
            if output:
                folder = Path(output).expanduser() / f'camera_{time.time_ns()}'
                folder.mkdir(parents=True, exist_ok=False)
                self.log = (folder / 'camera.jsonl').open('w', buffering=1)
            self.hands = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=.65,
                                                 min_tracking_confidence=.65)
            self.capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.capture.isOpened():
                raise RuntimeError(f'Cannot open /dev/video{index}; close the other camera application')
            self.create_timer(1 / 15., self.frame)
            self.get_logger().info(f'Webcam ready: /dev/video{index}; scene_source={self.source}')
        except Exception:
            self.close()
            raise

    def health(self, healthy, scene_ready=False, **values):
        data = dict(healthy=healthy, scene_ready=scene_ready, source=self.source, frame=self.frames, **values)
        self.status_pub.publish(String(data=json.dumps(data)))
        if self.log:
            self.log.write(json.dumps(dict(wall_time=time.time(), **data)) + '\n')

    def frame(self):
        ok, raw = self.capture.read()
        if not ok:
            self.health(False, reason='camera_frame_lost')
            raise RuntimeError('Camera stream lost')
        frame = square_frame(raw)
        result = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        hands = [hand.landmark for hand in result.multi_hand_landmarks or []]
        now = time.monotonic()
        ray = self.point_filter.observe(now, hands)
        objects = detect_objects(without_hands(frame, hands)) if self.source == 'camera' else []
        measured = self.scene_filter.observe(now, objects) if self.source == 'camera' else None
        ready = self.source == 'simulation' or measured is not None
        if measured is not None:
            self.scene_pub.publish(String(data=json.dumps(dict(objects=measured))))
        if ray and ready:
            self.point_pub.publish(String(data=json.dumps(ray)))
        for hand in result.multi_hand_landmarks or []:
            mp.solutions.drawing_utils.draw_landmarks(frame, hand, mp.solutions.hands.HAND_CONNECTIONS)
        self.frames += 1
        self.health(True, ready, pointing=bool(ray and ready), hands=len(hands), objects=objects,
                    ray=ray if ready else None, reason='ready' if ready else 'need_three_stable_colors')
        if self.frames % 2 == 0:
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                message = CompressedImage()
                message.header.stamp = self.get_clock().now().to_msg()
                message.header.frame_id, message.format = 'reference_camera_square', 'jpeg'
                message.data = encoded.tobytes()
                self.image_pub.publish(message)

    def close(self):
        if rclpy.ok():
            self.health(False, reason='camera_shutdown')
        if self.capture:
            self.capture.release()
        if self.hands:
            self.hands.close()
        if self.log:
            self.log.close()
            self.log = None


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = Camera()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if node:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
