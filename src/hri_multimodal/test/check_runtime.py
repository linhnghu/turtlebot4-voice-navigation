#!/usr/bin/env python3
"""Exercise installed controller + simulator through actual DDS topics/services.

Run in a dedicated ROS domain; writes auditable JSON evidence. No GUI required.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import rclpy
from geometry_msgs.msg import Pose2D, Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/hri_multimodal/runtime_validation.json')
    args = parser.parse_args()
    # This script owns its two child nodes; isolate them from other demos.
    os.environ['ROS_DOMAIN_ID'] = '67'
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    processes, checks = [], []
    completed = False
    rclpy.init()
    node = rclpy.create_node('hri_runtime_probe')
    state, pose, velocity = {}, [None], [None]
    node.create_subscription(String, '/hri/decision', lambda m: state.update(json.loads(m.data)), 10)
    node.create_subscription(Pose2D, '/hri/pose', lambda m: pose.__setitem__(0, (m.x, m.y, m.theta)), 10)
    node.create_subscription(Twist, '/hri/cmd_vel', lambda m: velocity.__setitem__(0, m.linear.x), 10)
    publisher = node.create_publisher(String, '/hri/input', 10)
    reset = node.create_client(Trigger, '/hri/reset_stop')

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)

    def wait(predicate, seconds=5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            rclpy.spin_once(node, timeout_sec=.02)
        raise AssertionError(f'Timeout: state={state}, pose={pose[0]}')

    def record(name, condition):
        checks.append(dict(name=name, passed=bool(condition), state=dict(state), pose=pose[0]))
        print(f'{"PASS" if condition else "FAIL"}  {name}', flush=True)
        assert condition, name

    def send(voice='', hand='None', cv=.95, cg=.95):
        publisher.publish(String(data=json.dumps(dict(
            voice=dict(text=voice, confidence=cv) if voice else None,
            gesture=dict(text=hand, confidence=cg) if hand != 'None' else None))))
        pump(.2)

    def clear():
        future = reset.call_async(Trigger.Request())
        wait(future.done)
        assert future.result().success
        pump(.15)

    log = output.with_suffix('.log').open('w')
    try:
        for module in ('simulator', 'controller'):
            processes.append(subprocess.Popen(
                [sys.executable, '-c', f'from hri_multimodal.{module} import main; main()'],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        wait(lambda: bool(state) and pose[0] is not None and velocity[0] is not None
             and reset.service_is_ready(), 12)
        record('startup_idle', state['action'] == 'idle' and velocity[0] == 0.)
        before = pose[0]
        send('Move forward', 'Thumb Up')
        pump(.7)
        record('agreement_moves_robot', state['reason'] == 'agreement'
               and pose[0][0] - before[0] > .3)
        start = time.monotonic()
        send('Move forward', 'Open Palm', .99, .01)
        wait(lambda: state.get('latched') and velocity[0] == 0.)
        record('open_palm_priority_low_confidence', time.monotonic() - start < .5)
        stopped = pose[0]
        send('Move forward', 'Thumb Up')
        pump(.4)
        record('stop_latch_blocks_motion', state['latched'] and math.dist(stopped[:2], pose[0][:2]) < .02)
        clear()
        record('reset_discards_old_command', state['action'] == 'idle' and not state['latched'])
        send('Move forward')
        record('voice_only', state['reason'] == 'voice_only' and velocity[0] > 0.)
        send('', 'Thumb Up')
        record('gesture_only', state['reason'] == 'gesture_only' and velocity[0] > 0.)
        pump(3.15)
        record('input_timeout', state['action'] == 'idle' and velocity[0] == 0.)
        send('Move forward', 'Wave')
        record('conflict_latches_stop', state['reason'] == 'conflict' and state['latched'])
        clear()
        send('Come here', 'Wave')
        record('come_agreement', state['action'] == 'come')
        deadline = time.monotonic() + 18
        while state.get('behavior') != 'arrived' and time.monotonic() < deadline:
            send('Come here', 'Wave')
            pump(.6)
        record('come_arrives_at_person', state['behavior'] == 'arrived'
               and math.hypot(pose[0][0] - 2, pose[0][1] - 4) < .42)
        send('Stop', 'Thumb Up', .1, .99)
        record('voice_stop_priority', state['latched'] and velocity[0] == 0.)
        clear()
        send('Move forward', 'Thumb Up', .2, .2)
        record('low_confidence_idle', state['action'] == 'idle' and velocity[0] == 0.)
        send('do not move forward')
        record('unknown_sentence_idle', state['action'] == 'idle')
        publisher.publish(String(data='not json'))
        pump(.3)
        record('malformed_input_latches_stop', state['reason'] == 'invalid_json' and state['latched'])
        clear()
        send('Move forward', 'Thumb Up')
        # Kill the publisher process abruptly to test the simulator's own watchdog.
        os.killpg(processes[1].pid, signal.SIGKILL)
        processes[1].wait(timeout=4)
        pump(.6)
        stopped = pose[0]
        pump(.5)
        record('controller_loss_simulator_watchdog', math.dist(stopped[:2], pose[0][:2]) < .005)
        completed = True
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
        output.write_text(json.dumps(dict(domain=67, completed=completed, checks=checks,
                                         passed=completed and bool(checks)
                                         and all(c['passed'] for c in checks)), indent=2))
        log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
