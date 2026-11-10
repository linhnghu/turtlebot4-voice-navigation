#!/usr/bin/env python3
"""Record the real Qt demo and verify its target and clarification ROS events."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import cv2
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main():
    output = Path('artifacts/hri_object_reference') / f'demo_check_{time.strftime("%Y%m%d_%H%M%S")}'
    output.mkdir(parents=True, exist_ok=False)
    rclpy.init()
    node = Node('reference_demo_check')
    events, targets, questions = [], [], []
    node.create_subscription(String, '/reference/events', lambda m: events.append(json.loads(m.data)), 100)
    node.create_subscription(String, '/reference/target', lambda m: targets.append(json.loads(m.data)), 20)
    node.create_subscription(String, '/reference/clarification', lambda m: questions.append(json.loads(m.data)), 20)
    environment = dict(os.environ, REFERENCE_DOMAIN_ID=os.environ.get('ROS_DOMAIN_ID', '68'))
    log = (output / 'launch.log').open('w')
    process = subprocess.Popen(['./run_object_reference.bash', 'demo:=true', 'auto_close:=true',
                                f'record_dir:={output.resolve()}', f'log_dir:={output.resolve()}'],
                               env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 45.
        while process.poll() is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        assert process.poll() == 0, f'Demo did not exit cleanly: {output / "launch.log"}'
        reasons = [e['reason'] for e in events]
        for reason in ('speech_and_pointing_agree', 'ambiguous_pointing',
                       'speech_pointing_conflict', 'explicit_confirmation'):
            assert reason in reasons, (reason, reasons)
        assert len(targets) == 2 and all(t['object']['color'] == 'blue' for t in targets), targets
        assert [q['reason'] for q in questions] == ['ambiguous_pointing', 'speech_pointing_conflict'], questions
        recordings = list(output.glob('*/demo.avi'))
        assert len(recordings) == 1, recordings
        video = cv2.VideoCapture(str(recordings[0]))
        ok, _ = video.read()
        frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        video.release()
        assert ok and frames >= 100, (ok, frames)
        for name in ('01_selected.png', '02_ambiguous.png', '03_conflict.png', '04_confirmed.png'):
            assert cv2.imread(str(recordings[0].with_name(name))) is not None, name
        mp4 = None
        if shutil.which('ffmpeg'):
            mp4 = recordings[0].with_suffix('.mp4')
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(recordings[0]),
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)],
                           check=True, timeout=45.)
        report = dict(passed=True, source='automated mouse/text simulation rendered in Qt and resolved over ROS',
                      target_events=len(targets), clarification_events=len(questions), reasons=reasons,
                      video_frames=frames, video=str(mp4 or recordings[0]),
                      evidence_dir=str(recordings[0].parent))
        (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=8.)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5.)
        log.close()


if __name__ == '__main__':
    main()
