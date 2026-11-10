#!/usr/bin/env python3
"""Isolated ROS transport integration using synthetic observations (no webcam)."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


def main():
    output = Path('artifacts/hri_engagement')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'runtime_controller.log').open('w') as log:
        process = subprocess.Popen(['ros2', 'launch', 'hri_engagement', 'engagement.launch.py',
                                    'camera:=false'], stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        rclpy.init()
        node = Node('engagement_runtime_check')
        vision = node.create_publisher(String, '/engagement/vision', 10)
        speech = node.create_publisher(String, '/engagement/speech', 10)
        states, responses = [], []
        node.create_subscription(String, '/engagement/state', lambda m: states.append(json.loads(m.data)), 100)
        node.create_subscription(String, '/engagement/response', lambda m: responses.append(m.data), 10)
        client = node.create_client(Trigger, '/engagement/reset')
        results = []

        def spin(duration):
            until = time.monotonic() + duration
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=.01)

        def reset():
            future = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(node, future, timeout_sec=3.)
            assert future.done() and future.result().success, 'reset failed'
            spin(.1)
            states.clear()
            responses.clear()

        def feed(duration, *, head=True, hand=False, face=True, text=None):
            start = time.monotonic()
            sent = False
            while time.monotonic() - start < duration:
                vision.publish(String(data=json.dumps(dict(healthy=True, face_present=face,
                                                           facing=head, hand_raised=hand))))
                if text and not sent and time.monotonic() - start > .65:
                    speech.publish(String(data=text))
                    sent = True
                spin(.05)
            spin(.05)

        def check(name, expected, count):
            assert states, f'{name}: no controller state received'
            assert states[-1]['state'] == expected, (name, states[-1])
            assert len(responses) == count, (name, responses)
            results.append(dict(case=name, state=expected, greetings=count, passed=True))

        try:
            assert client.wait_for_service(timeout_sec=12.), 'controller did not start'
            deadline = time.monotonic() + 5.
            while (not vision.get_subscription_count() or not speech.get_subscription_count()
                   or not node.count_publishers('/engagement/response')) and time.monotonic() < deadline:
                spin(.05)
            reset()
            feed(1.5)
            check('head_only', 'ATTENTION', 0)
            reset()
            feed(1.8, hand=True)
            check('head_hand', 'ENGAGED', 1)
            assert 'ATTENTION' in [s['state'] for s in states], 'ATTENTION transition missing'
            feed(1.2, hand=True)
            check('no_repeated_greeting', 'ENGAGED', 1)
            spin(.9)
            check('camera_timeout', 'IDLE', 1)
            reset()
            feed(1.5, text='Hello robot')
            check('head_speech', 'ENGAGED', 1)
            reset()
            feed(1.5, head=False, face=False)
            check('passerby_no_cues', 'IDLE', 0)
            reset()
            feed(1.5, head=False, text='Excuse me')
            check('speech_without_facing', 'ATTENTION', 0)
            reset()
            feed(1.5, text='do not say hello robot')
            check('unrelated_speech', 'ATTENTION', 0)
            vision.publish(String(data='{"healthy":"false"}'))
            spin(.2)
            check('invalid_vision', 'IDLE', 0)
            # Exercise the same recorder users run, with explicitly synthetic labels.
            reset()
            with tempfile.TemporaryDirectory(prefix='engagement_recorder_') as temporary:
                recorder = subprocess.Popen([
                    'ros2', 'run', 'hri_engagement', 'trial_recorder', '--scenario', 'head_only',
                    '--expected', 'no', '--duration', '1', '--source', 'synthetic',
                    '--output', str(Path(temporary) / 'trials.csv')],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                try:
                    deadline = time.monotonic() + 10.
                    while recorder.poll() is None and time.monotonic() < deadline:
                        feed(.1)
                    if recorder.poll() is None:
                        raise RuntimeError('trial recorder timed out')
                    stdout, _ = recorder.communicate(timeout=2.)
                    assert recorder.returncode == 0, stdout
                    import csv
                    with (Path(temporary) / 'trials.csv').open() as stream:
                        row = next(csv.DictReader(stream))
                    assert row['source'] == 'synthetic', row
                    assert row['camera_valid'] == '1', (row, stdout)
                    assert row['observed_engaged'] == '0', row
                    results.append(dict(case='labelled_trial_recorder', passed=True))
                finally:
                    if recorder.poll() is None:
                        recorder.terminate()
                        recorder.wait(timeout=5.)
            report = dict(source='synthetic ROS observations', results=results,
                          note='Validates DDS, launch, FSM and greeting events; not perception accuracy')
            (output / 'runtime_results.json').write_text(json.dumps(report, indent=2) + '\n')
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


if __name__ == '__main__':
    main()
