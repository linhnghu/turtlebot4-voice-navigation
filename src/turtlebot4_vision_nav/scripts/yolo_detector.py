#!/usr/bin/env python3
"""Real RGB camera -> cv_bridge -> YOLO -> annotated ROS image and detection JSON."""
from pathlib import Path
import json
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String
from cv_bridge import CvBridge
import torch
from ultralytics import YOLO


class Detector(Node):
    def __init__(self):
        super().__init__('camera_yolo_detector')
        self.topic = self.declare_parameter('image_topic', '/oakd/rgb/preview/image_raw').value
        weights = Path(self.declare_parameter('weights', '').value).expanduser()
        if not weights.is_file():
            raise FileNotFoundError(f'YOLO weights missing: {weights}. Run ./setup_vision.bash first.')
        self.confidence = float(self.declare_parameter('confidence', 0.35).value)
        self.image_size = int(self.declare_parameter('image_size', 640).value)
        self.rate = float(self.declare_parameter('inference_rate', 2.0).value)
        self.show = bool(self.declare_parameter('show_window', True).value)
        self.output = Path(self.declare_parameter('output_dir', 'artifacts/vision_demo').value)
        self.output.mkdir(parents=True, exist_ok=True)
        torch.set_num_threads(2)
        cv2.setNumThreads(1)
        self.model = YOLO(str(weights))
        self.model.predict(np.zeros((240, 320, 3), dtype=np.uint8), imgsz=self.image_size,
                           conf=self.confidence, device='cpu', verbose=False)
        self.bridge = CvBridge()
        self.latest = None
        self.sequence = self.processed = 0
        self.arrived = self.last_log = self.last_warn = 0.0
        self.mission_state = {'state': 'WAITING_FOR_MISSION'}
        self.stats = dict(model=weights.name, camera_topic=self.topic, processed_frames=0,
                          frames_with_detections=0, class_counts={}, max_confidence={})
        self.events = (self.output / 'detections.jsonl').open('w', buffering=1)
        self.video = None
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                              reliability=ReliabilityPolicy.RELIABLE)
        sensor_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.image_pub = self.create_publisher(Image, '/yolo/image_annotated', 1)
        self.detections_pub = self.create_publisher(String, '/yolo/detections', 1)
        self.ready_pub = self.create_publisher(Bool, '/yolo/ready', latched)
        self.create_subscription(Image, self.topic, self.image, sensor_qos)
        self.create_subscription(String, '/mission/state', self.state, latched)
        self.create_timer(1.0 / self.rate, self.infer)
        self.ready_pub.publish(Bool(data=False))
        if self.show:
            cv2.namedWindow('TurtleBot 4 - YOLO RGB Camera', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('TurtleBot 4 - YOLO RGB Camera', 800, 680)
        self.get_logger().info(f'YOLO loaded: {weights.name}; waiting for camera {self.topic}')

    def image(self, msg):
        self.latest = msg
        self.arrived = time.monotonic()
        self.sequence += 1

    def state(self, msg):
        self.mission_state = json.loads(msg.data)

    def save_stats(self):
        target = self.output / 'yolo_summary.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.stats, indent=2))
        temporary.replace(target)

    def infer(self):
        if self.latest is None or time.monotonic() - self.arrived > 5:
            self.ready_pub.publish(Bool(data=False))
            if time.monotonic() - self.last_warn > 8:
                self.last_warn = time.monotonic()
                self.get_logger().warning(f'No fresh RGB image on {self.topic}; check Gazebo is playing.')
            return
        if self.sequence == self.processed:
            if self.show:
                cv2.waitKey(1)
            return
        msg, self.processed = self.latest, self.sequence
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            start = time.monotonic()
            result = self.model.predict(frame, imgsz=self.image_size, conf=self.confidence,
                                        device='cpu', verbose=False)[0]
            elapsed = time.monotonic() - start
            objects = []
            for box in result.boxes:
                name = result.names[int(box.cls.item())]
                confidence = float(box.conf.item())
                objects.append(dict(class_name=name, confidence=round(confidence, 4),
                                    xyxy=[round(float(v), 1) for v in box.xyxy[0].tolist()]))
                counts, scores = self.stats['class_counts'], self.stats['max_confidence']
                counts[name] = counts.get(name, 0) + 1
                scores[name] = max(scores.get(name, 0), confidence)
            self.stats['processed_frames'] += 1
            self.stats['frames_with_detections'] += int(bool(objects))
            self.stats['last_inference_seconds'] = round(elapsed, 3)
            event = dict(stamp=dict(sec=msg.header.stamp.sec, nanosec=msg.header.stamp.nanosec),
                         frame=self.stats['processed_frames'], objects=objects,
                         mission=self.mission_state)
            self.events.write(json.dumps(event) + '\n')
            self.detections_pub.publish(String(data=json.dumps(event)))
            annotated = result.plot()
            out = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            out.header = msg.header
            self.image_pub.publish(out)
            self.ready_pub.publish(Bool(data=True))
            # The video/dashboard contain camera pixels and model outputs only.
            canvas = cv2.resize(annotated, (800, 600))
            canvas = cv2.copyMakeBorder(canvas, 0, 96, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
            state = self.mission_state
            title = f"{state.get('state', '')}  Goal {state.get('goal', '-')}/{state.get('total', 3)}"
            cv2.putText(canvas, title, (12, 628), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 160), 2)
            names = ', '.join(f"{o['class_name']} {o['confidence']:.2f}" for o in objects) or 'No detections'
            cv2.putText(canvas, names[:92], (12, 654), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
            cv2.putText(canvas, f"{self.stats['model']} CPU | {elapsed * 1000:.0f} ms | RGB frame {event['frame']}",
                        (12, 680), cv2.FONT_HERSHEY_SIMPLEX, .55, (200, 200, 200), 1)
            if self.video is None:
                self.video = cv2.VideoWriter(str(self.output / 'camera_yolo.mp4'),
                                             cv2.VideoWriter_fourcc(*'mp4v'), self.rate, (800, 696))
            self.video.write(canvas)
            if objects and not (self.output / 'detection_example.png').exists():
                cv2.imwrite(str(self.output / 'detection_example.png'), canvas)
                cv2.imwrite(str(self.output / 'rgb_example.png'), frame)
            if any(o['class_name'] == 'person' and o['confidence'] >= 0.6 for o in objects):
                if not (self.output / 'person_example.png').exists():
                    cv2.imwrite(str(self.output / 'person_example.png'), canvas)
                    cv2.imwrite(str(self.output / 'person_rgb.png'), frame)
            if self.show:
                cv2.imshow('TurtleBot 4 - YOLO RGB Camera', canvas)
                cv2.waitKey(1)
            if time.monotonic() - self.last_log > 2:
                self.last_log = time.monotonic()
                self.get_logger().info(f"frame={event['frame']} detections={names} inference={elapsed:.3f}s")
                self.save_stats()
        except Exception as error:
            self.ready_pub.publish(Bool(data=False))
            self.get_logger().error(f'Camera/inference failed: {error}')

    def close(self):
        self.save_stats()
        self.events.close()
        if self.video:
            self.video.release()
        if self.show:
            cv2.destroyAllWindows()


def main():
    rclpy.init()
    node = None
    try:
        node = Detector()
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
