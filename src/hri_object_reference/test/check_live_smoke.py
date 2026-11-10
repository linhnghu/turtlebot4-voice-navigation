#!/usr/bin/env python3
"""Observe a running live launch; verify actual camera and microphone streams."""
import json
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String


def main():
    rclpy.init()
    node = Node('reference_live_hardware_probe')
    camera, mic, states, utterances, images = [], [], [], [], []
    for topic, bucket in (('camera_status', camera), ('mic_status', mic), ('state', states), ('transcript', utterances)):
        node.create_subscription(String, '/reference/' + topic,
                                 lambda message, target=bucket: target.append(json.loads(message.data)), 100)
    node.create_subscription(CompressedImage, '/reference/image/compressed', lambda m: images.append(len(m.data)), 1)
    try:
        deadline = time.monotonic() + 12.
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        report = dict(source='physical webcam and physical default microphone',
            healthy_camera=sum(c.get('healthy') is True for c in camera), image_messages=len(images),
            healthy_microphone=sum(m.get('healthy') is True for m in mic),
            audio_blocks=max((m.get('blocks', 0) for m in mic), default=0),
            audio_rms_max=max((m.get('rms', 0) for m in mic), default=0),
            clipping_max=max((m.get('clip_fraction', 0) for m in mic), default=0),
            model=mic[-1].get('model') if mic else None,
            scene_ready=any(c.get('scene_ready') for c in camera),
            scene_source=camera[-1].get('source') if camera else None,
            object_count=max((len(s.get('objects', [])) for s in states), default=0),
            fusion_ready=any(s.get('camera_ready') and s.get('microphone_ready') for s in states),
            frames_with_pointing=sum(c.get('pointing', False) for c in camera),
            observed_states=sorted({s['state'] for s in states}),
            accepted_utterances=sum(u.get('accepted') is True for u in utterances),
            audio_overruns=sum(u.get('reason') == 'audio_overrun' for u in utterances),
            note='Hardware smoke only. Does not measure recognition accuracy or validate a labelled human selection.')
        output = Path('artifacts/hri_object_reference/live/hardware_smoke.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        assert report['healthy_camera'] > 10 and report['healthy_microphone'] > 10 and len(images) > 5
        if report['scene_source'] == 'simulation':
            assert report['object_count'] == 3 and report['fusion_ready'], report
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
