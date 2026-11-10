#!/usr/bin/env python3
"""Laptop webcam -> MediaPipe Tasks Gesture Recognizer -> ROS gesture labels."""
import json
import math
from pathlib import Path
import time

import cv2
import mediapipe as mp
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from gesture_core import GESTURES, WaveDetector

TITLE = 'TurtleBot 4 - Hand Gesture Webcam'
CONNECTIONS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
               (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),
               (15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]


class GestureRecognitionNode(Node):
    def __init__(self):
        super().__init__('gesture_recognition_node')
        for name, default in [('camera_index', 0), ('model_path', ''), ('show_window', True),
                              ('output_dir', ''), ('confidence', 0.65)]:
            self.declare_parameter(name, default)
        self.publisher = self.create_publisher(String, '/detected_gesture', 1)
        self.status = 'WAITING FOR ROBOT SENSORS'
        self.create_subscription(String, '/gesture_behavior/status', self.on_status, 1)
        self.wave = WaveDetector()
        self.show = self.get_parameter('show_window').value
        self.threshold = float(self.get_parameter('confidence').value)
        self.capture = None
        self.recognizer = None
        self.video = None
        self.log_file = None
        self.closed = False
        self.timestamp_ms = -1
        output = self.get_parameter('output_dir').value
        try:
            if output:
                Path(output).mkdir(parents=True, exist_ok=True)
                self.log_file = (Path(output) / 'gestures.jsonl').open('a', buffering=1)
            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=self.get_parameter('model_path').value),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.6)
            self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
            self.capture = cv2.VideoCapture(self.get_parameter('camera_index').value, cv2.CAP_V4L2)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture.set(cv2.CAP_PROP_FPS, 20)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.capture.isOpened():
                raise RuntimeError('Cannot open laptop webcam; check /dev/video* and camera_index.')
            if self.show:
                cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(TITLE, 800, 680)
            self.output = output
            self.create_timer(0.05, self.frame)
        except Exception:
            self.close()
            raise

    def on_status(self, message):
        self.status = message.data

    def frame(self):
        try:
            ok, frame = self.capture.read()
            if not ok:
                raise RuntimeError('Webcam frame unavailable')
            frame = cv2.flip(frame, 1)
            now = time.monotonic()
            self.timestamp_ms = max(self.timestamp_ms+1, int(now*1000))
            rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = self.recognizer.recognize_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self.timestamp_ms)
            label, score = 'No_Hand', 0.0
            hands = result.hand_landmarks
            if len(hands) == 1 and result.gestures and result.gestures[0]:
                best = result.gestures[0][0]
                score = float(best.score)
                label = best.category_name if score >= self.threshold else 'Unknown'
                if label not in GESTURES:
                    label = 'Unknown'
                points = hands[0]
                width = math.hypot(points[5].x-points[17].x, points[5].y-points[17].y)
                center = sum(points[i].x for i in (0,5,9,13,17))/5
                label = self.wave.update(now, label, center, width)
            else:
                # Multiple hands are ambiguous; never let one person's thumb
                # confirm another person's selected command. Palm/fist still stop.
                label = 'Multiple_Hands' if hands else 'No_Hand'
                for categories in result.gestures:
                    if categories and categories[0].score >= self.threshold:
                        if categories[0].category_name in ('Open_Palm', 'Closed_Fist'):
                            label = categories[0].category_name
                            score = float(categories[0].score)
                            break
                self.wave.update(now, 'Unknown')
            self.publisher.publish(String(data=label))
            if self.log_file:
                self.log_file.write(json.dumps({'wall_time': time.time(), 'gesture': label,
                                               'confidence': score, 'hands': len(hands)}) + '\n')
            h, w = frame.shape[:2]
            for hand in hands:
                coords = [(int(p.x*w), int(p.y*h)) for p in hand]
                for a, b in CONNECTIONS:
                    cv2.line(frame, coords[a], coords[b], (0,220,0), 2)
                for point in coords:
                    cv2.circle(frame, point, 3, (0,220,255), -1)
            panel = np.zeros((190, w, 3), dtype=np.uint8)
            lines = [f'Gesture: {label}   Confidence: {score:.2f}', self.status,
                     'Wave: greet | 1 finger: forward/back x4 | 2: circle',
                     'Thumb Up: start once; you may lower your hand',
                     'Open Palm: STOP | Closed Fist: cancel']
            for i, line in enumerate(lines):
                cv2.putText(panel, line, (10, 27+i*34), cv2.FONT_HERSHEY_SIMPLEX,
                            0.48, (255,255,255), 1, cv2.LINE_AA)
            annotated = np.vstack([frame, panel])
            if self.output and self.video is None:
                self.video = cv2.VideoWriter(str(Path(self.output)/'webcam_gestures.mp4'),
                    cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h+190))
                if not self.video.isOpened():
                    raise RuntimeError('Cannot create webcam recording')
            if self.video:
                self.video.write(annotated)
            if self.show:
                cv2.imshow(TITLE, annotated)
                cv2.waitKey(1)  # GUI event processing only; no keyboard motion commands.
                if cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    raise RuntimeError('Webcam window closed')
        except Exception as error:
            self.publisher.publish(String(data='Camera_Error'))
            self.get_logger().error(str(error))
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if rclpy.ok():
            self.publisher.publish(String(data='Shutdown'))
        if self.capture:
            self.capture.release()
        if self.recognizer:
            self.recognizer.close()
        if self.video:
            self.video.release()
        if self.log_file:
            self.log_file.close()
        if self.show:
            cv2.destroyAllWindows()


def main():
    rclpy.init()
    node = None
    try:
        node = GestureRecognitionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
