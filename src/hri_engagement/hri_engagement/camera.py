"""Webcam observation, annotated preview, and optional local recording."""
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

from .vision import head_pose, raised_open_hand

TITLE = 'Bai 02 - Interaction intent'


class Camera(Node):
    def __init__(self):
        super().__init__('engagement_camera')
        self.capture = self.face_mesh = self.hands = self.writer = self.log = None
        self.show = self.declare_parameter('show_window', True).value
        index = self.declare_parameter('camera_index', 0).value
        self.yaw_limit = float(self.declare_parameter('yaw_limit', 22.).value)
        self.pitch_limit = float(self.declare_parameter('pitch_limit', 22.).value)
        if not 0 < self.yaw_limit < 90 or not 0 < self.pitch_limit < 90:
            raise ValueError('yaw_limit and pitch_limit must be between 0 and 90 degrees')
        output = self.declare_parameter('output_dir', '').value
        self.publisher = self.create_publisher(String, '/engagement/vision', 1)
        self.images = self.create_publisher(CompressedImage, '/engagement/image/compressed', 1)
        self.create_subscription(String, '/engagement/state', self.on_state, 1)
        self.create_subscription(String, '/engagement/response', self.on_response, 10)
        self.state, self.reason = 'IDLE', 'waiting_for_controller'
        self.head_stable = self.hand_recent = False
        self.response_until = 0.
        self.frame_count = 0
        self.output = Path(output).expanduser() if output else None
        try:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=2, min_detection_confidence=.6, min_tracking_confidence=.6)
            self.hands = mp.solutions.hands.Hands(
                max_num_hands=2, min_detection_confidence=.6, min_tracking_confidence=.6)
            self.capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.capture.isOpened():
                raise RuntimeError(f'Cannot open /dev/video{index}; check camera_index and camera ownership')
            if self.output:
                self.output.mkdir(parents=True, exist_ok=True)
                # A unique run subdirectory prevents overwriting an earlier recording.
                self.output = self.output / time.strftime('%Y%m%d_%H%M%S')
                self.output.mkdir(exist_ok=False)
                self.log = (self.output / 'observations.jsonl').open('w', buffering=1)
            self.create_timer(1 / 15., self.frame)
            self.get_logger().info('Camera ready. Face camera + raise open hand, or send Hello robot.')
        except Exception:
            self.close()
            raise

    def on_state(self, message):
        try:
            data = json.loads(message.data)
            self.state, self.reason = data['state'], data['reason']
            self.head_stable, self.hand_recent = data['head_stable'], data['hand_recent']
        except (ValueError, TypeError, KeyError):
            pass

    def on_response(self, message):
        self.response_until = time.monotonic() + 3.
        if self.log:
            self.log.write(json.dumps(dict(kind='response', text=message.data, wall_time=time.time()),
                                      ensure_ascii=False) + '\n')

    def publish(self, data):
        self.publisher.publish(String(data=json.dumps(data)))
        if self.log:
            self.log.write(json.dumps(dict(kind='vision', wall_time=time.time(),
                                          state=self.state, **data)) + '\n')

    def frame(self):
        ok, frame = self.capture.read()
        if not ok:
            self.publish(dict(healthy=False, face_present=False, facing=False, hand_raised=False))
            raise RuntimeError('Camera stream lost')
        height, width = frame.shape[:2]
        # Infer on the unmirrored image so the head coordinate system stays consistent.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = self.face_mesh.process(rgb).multi_face_landmarks or []
        hands = self.hands.process(rgb).multi_hand_landmarks or []
        pose, facing, raised = None, False, False
        if len(faces) == 1:
            face = faces[0].landmark
            pose = head_pose(face, width, height)
            facing = bool(pose and abs(pose[0]) <= self.pitch_limit and abs(pose[1]) <= self.yaw_limit)
            raised = any(raised_open_hand(hand.landmark, face) for hand in hands)
        for face in faces:
            mp.solutions.drawing_utils.draw_landmarks(
                frame, face, mp.solutions.face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp.solutions.drawing_utils.DrawingSpec((80, 200, 180), 1, 1))
        for hand in hands:
            mp.solutions.drawing_utils.draw_landmarks(frame, hand, mp.solutions.hands.HAND_CONNECTIONS)
        data = dict(healthy=True, face_present=len(faces) == 1, facing=facing,
                    hand_raised=bool(raised), faces=len(faces), hands=len(hands),
                    pitch=round(pose[0], 1) if pose else None,
                    yaw=round(pose[1], 1) if pose else None)
        self.publish(data)
        frame = cv2.flip(frame, 1)
        color = (80, 230, 100) if self.state == 'ENGAGED' else (30, 200, 255)
        lines = [f'{self.state} | {self.reason}',
                 f'faces={len(faces)} head={facing} stable={self.head_stable} hand={raised}',
                 f'pitch={data["pitch"]} yaw={data["yaw"]} (approx. degrees)',
                 'Face robot + raised open hand OR Hello robot',
                 'ROBOT: HELLO! How can I help?' if time.monotonic() < self.response_until
                 else 'Head direction alone: wait for more signals']
        cv2.rectangle(frame, (0, 0), (width, 135), (30, 30, 30), -1)
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (8, 23 + i * 25), cv2.FONT_HERSHEY_SIMPLEX,
                        .48, color if i == 0 or i == 4 else (240, 240, 240), 1, cv2.LINE_AA)
        self.frame_count += 1
        if self.output:
            if self.writer is None:
                self.writer = cv2.VideoWriter(str(self.output / 'webcam.avi'),
                                              cv2.VideoWriter_fourcc(*'MJPG'), 15., (width, height))
                if not self.writer.isOpened():
                    raise RuntimeError('Cannot create video recording')
            self.writer.write(frame)
        if self.frame_count % 3 == 0:
            ok, encoded = cv2.imencode('.jpg', frame)
            if ok:
                message = CompressedImage()
                message.header.stamp = self.get_clock().now().to_msg()
                message.header.frame_id, message.format = 'engagement_webcam', 'jpeg'
                message.data = encoded.tobytes()
                self.images.publish(message)
        if self.show:
            cv2.imshow(TITLE, frame)
            if cv2.waitKey(1) & 0xff in (27, ord('q')):
                raise KeyboardInterrupt
            if cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                raise KeyboardInterrupt

    def close(self):
        if rclpy.ok():
            self.publish(dict(healthy=False, face_present=False, facing=False, hand_raised=False))
        for obj, method in ((self.capture, 'release'), (self.writer, 'release'),
                            (self.face_mesh, 'close'), (self.hands, 'close'), (self.log, 'close')):
            if obj is not None:
                getattr(obj, method)()
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
