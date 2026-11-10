#!/usr/bin/env python3
"""Actual WAV -> speech ROS node -> parser -> Nav2 -> arrived, three commands."""
import json
from pathlib import Path
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from turtlebot4_voice_nav.navigator import latched


def main():
    root = Path(__file__).resolve().parents[3]
    output = root / 'artifacts/voice_nav'
    rclpy.init()
    node = Node('check_voice_pipeline')
    events, transcripts, checks = [], [], []
    node.create_subscription(String, '/voice_nav/status', lambda m: events.append(json.loads(m.data)), latched())
    node.create_subscription(String, '/voice_nav/transcript', lambda m: transcripts.append(json.loads(m.data)), 10)
    pub = node.create_publisher(String, '/voice_nav/command', 10)

    def wait(predicate, timeout):
        end = time.monotonic()+timeout
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.1)
            if predicate():
                return
        raise RuntimeError('Timeout in audio/Nav2 pipeline: ' + str(events[-3:]))

    report = dict(passed=False, input='google_tts_wav_not_human_microphone', checks=checks)
    child = None
    try:
        wait(lambda: events and not events[-1]['busy'], 20)
        speech = root / 'install/turtlebot4_voice_nav/lib/turtlebot4_voice_nav/speech'
        for index, region in enumerate(['A', 'B', 'C'], 1):
            start, spoken_start = len(events), len(transcripts)
            with (output / f'voice_pipeline_{index}.log').open('w') as log:
                child = subprocess.Popen([
                    str(root / '.venv-voice-nav/bin/python'), str(speech), '--ros-args',
                    '-p', 'backend:=whisper',
                    '-p', 'whisper_path:=' + str(root / '.models/faster-whisper-small'),
                    '-p', 'regions_file:=' + str(output / 'regions.yaml'),
                    '-p', 'wav_file:=' + str(output / f'speech/command_{index}.wav')],
                    stdout=log, stderr=subprocess.STDOUT)
                wait(lambda: len(transcripts) > spoken_start, 45)
                wait(lambda: any(e['state'] in ('SUCCEEDED', 'FAILED', 'REJECTED', 'LOW_CONFIDENCE',
                                               'UNKNOWN_REGION', 'UNKNOWN_COMMAND', 'NOT_READY', 'CANCELED')
                                 for e in events[start:]), 240)
                result = events[-1]
                observed = [e for e in events[start:] if e['state'] == 'WAYPOINT_SUCCEEDED']
                assert result['state'] == 'SUCCEEDED', result
                assert result['completed'] == [region], result
                check = dict(region=region, transcript=transcripts[-1],
                             result=result, waypoint=observed[-1] if observed else None)
                checks.append(check)
                print(json.dumps(check, ensure_ascii=False), flush=True)
                assert child.wait(timeout=15) == 0
                child = None
        report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
        pub.publish(String(data='dừng lại'))
        raise
    finally:
        if child and child.poll() is None:
            child.terminate()
            child.wait(timeout=15)
        (output / 'voice_pipeline_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
