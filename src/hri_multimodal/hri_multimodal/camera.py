"""Physical webcam -> MediaPipe inference -> HRI gesture and health topics."""
import json
import math
from pathlib import Path
import signal
import time

import cv2
import mediapipe as mp
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from .vision import GestureFilter

TITLE = 'HRI - Webcam Gesture Recognition'
CONNECTIONS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
               (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),
               (15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]


class Camera(Node):
    def __init__(self):
        super().__init__('hri_camera')
        self.capture = self.recognizer = self.log = None
        self.show = bool(self.declare_parameter('show_window', True).value)
        self.output = str(self.declare_parameter('output_dir', '').value)
        model = str(self.declare_parameter('model_path', '').value)
        index = int(self.declare_parameter('camera_index', 0).value)
        self.gesture_pub = self.create_publisher(String, '/hri/gesture', 1)
        self.health_pub = self.create_publisher(String, '/hri/camera_status', 1)
        self.image_pub = self.create_publisher(CompressedImage, '/hri/camera/image/compressed', 1)
        self.create_subscription(String, '/hri/decision', self.on_decision, 1)
        self.decision = 'WAITING FOR CONTROLLER'
        self.filter = GestureFilter()
        self.last_label = None
        self.timestamp = 0
        self.frame_count = 0
        self.start = time.monotonic()
        try:
            if self.output:
                Path(self.output).mkdir(parents=True, exist_ok=True)
                self.log = (Path(self.output) / 'camera.jsonl').open('w', buffering=1)
            self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(
                mp.tasks.vision.GestureRecognizerOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=model),
                    running_mode=mp.tasks.vision.RunningMode.VIDEO,
                    num_hands=2, min_hand_detection_confidence=.6,
                    min_hand_presence_confidence=.6, min_tracking_confidence=.6))
            self.capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture.set(cv2.CAP_PROP_FPS, 20)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.capture.isOpened():
                raise RuntimeError(f'Cannot open /dev/video{index}')
            if self.show:
                cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(TITLE, 800, 700)
            self.create_timer(.05, self.frame)
        except Exception:
            self.close()
            raise

    def on_decision(self, message):
        state = json.loads(message.data)
        self.decision = f"{state['behavior'].upper()} | {state['reason']} | latch={state['latched']}"

    def health(self, healthy, inhibit, label, score=0., hands=0):
        state = dict(healthy=healthy, motion_inhibit=inhibit, label=label,
                     confidence=score, hands=hands, frame=self.frame_count,
                     elapsed=round(time.monotonic() - self.start, 3))
        self.health_pub.publish(String(data=json.dumps(state)))
        if self.log:
            self.log.write(json.dumps(state) + '\n')

    def frame(self):
        try:
            ok, frame = self.capture.read()
            if not ok:
                raise RuntimeError('Camera frame unavailable')
            frame = cv2.flip(frame, 1)
            now = time.monotonic()
            self.timestamp = max(self.timestamp + 1, int(now * 1000))
            rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = self.recognizer.recognize_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self.timestamp)
            hands = result.hand_landmarks
            label, score, center, width = 'None', 0., .5, .15
            if len(hands) == 1 and result.gestures and result.gestures[0]:
                category = result.gestures[0][0]
                label, score = category.category_name, float(category.score)
                points = hands[0]
                center = sum(points[i].x for i in (0,5,9,13,17)) / 5
                width = math.hypot(points[5].x - points[17].x, points[5].y - points[17].y)
            elif len(hands) > 1:
                for categories in result.gestures:
                    if categories and categories[0].category_name == 'Open_Palm' and categories[0].score >= .5:
                        label, score = 'Open_Palm', float(categories[0].score)
                        break
            label, confidence, inhibit = self.filter.observe(now, label, score, len(hands), center, width)
            self.frame_count += 1
            self.health(True, inhibit, label, confidence, len(hands))
            if label in ('Thumb Up', 'Wave', 'Open Palm'):
                self.gesture_pub.publish(String(data=json.dumps(dict(text=label, confidence=confidence))))
            elif inhibit:
                # Forget old motion during palm classification; health also inhibits voice motion.
                self.gesture_pub.publish(String(data='null'))
            if label != self.last_label:
                self.get_logger().info(f'{label} ({confidence:.2f}), hands={len(hands)}')
                self.last_label = label
            h, w = frame.shape[:2]
            for hand in hands:
                coords = [(int(p.x*w), int(p.y*h)) for p in hand]
                for a,b in CONNECTIONS:
                    cv2.line(frame, coords[a], coords[b], (70,230,160), 2)
                for p in coords:
                    cv2.circle(frame, p, 3, (20,200,255), -1)
            panel = np.full((160,w,3), (34,27,18), dtype=np.uint8)
            for i,line in enumerate([
                    f'{label} | confidence={confidence:.2f} | hands={len(hands)}',
                    self.decision, 'Thumb Up: forward | Wave left-right: come here',
                    'Still Open Palm: STOP (0.4 s) | reset in dashboard',
                    'Palm pending / camera lost: motion is inhibited']):
                cv2.putText(panel, line, (10, 25+i*29), cv2.FONT_HERSHEY_SIMPLEX,
                            .47, (235,245,250), 1, cv2.LINE_AA)
            annotated = np.vstack([frame, panel])
            if self.frame_count % 4 == 0:
                ok, encoded = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    msg = CompressedImage()
                    msg.header.stamp = self.get_clock().now().to_msg()
                    msg.header.frame_id = 'webcam'
                    msg.format, msg.data = 'jpeg', encoded.tobytes()
                    self.image_pub.publish(msg)
                if self.output and self.frame_count % 40 == 0:
                    cv2.imwrite(str(Path(self.output) / 'webcam.jpg'), annotated)
            if self.show:
                cv2.imshow(TITLE, annotated)
                cv2.waitKey(1)
                if cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    raise RuntimeError('Camera window closed')
        except Exception as exc:
            self.health(False, True, 'Camera error')
            self.gesture_pub.publish(String(data=json.dumps(dict(text='Open Palm', confidence=1.))))
            self.get_logger().error(str(exc))
            raise

    def close(self):
        if rclpy.ok():
            self.health(False, True, 'Camera shutdown')
            self.gesture_pub.publish(String(data=json.dumps(dict(text='Open Palm', confidence=1.))))
        if self.capture:
            self.capture.release()
        if self.recognizer:
            self.recognizer.close()
        if self.log:
            self.log.close()
            self.log = None
        if self.show:
            cv2.destroyAllWindows()


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
