#!/usr/bin/env python3
"""DDS integration with an image-derived scene and synthetic pointing/text."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from hri_object_reference.perception import detect_objects, make_table


def main():
    output = Path('artifacts/hri_object_reference')
    output.mkdir(parents=True, exist_ok=True)
    log = (output / 'runtime_controller.log').open('w')
    process = subprocess.Popen(['ros2', 'launch', 'hri_object_reference', 'reference.launch.py', 'gui:=false',
                                'camera_required:=true', 'mic_required:=true'],
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    node = Node('reference_runtime_check')
    publishers = {name: node.create_publisher(String, f'/reference/{name}', 10)
                  for name in ('scene', 'request', 'pointing', 'speech', 'confirm', 'camera_status', 'mic_status')}
    states, targets, questions = [], [], []
    node.create_subscription(String, '/reference/state', lambda m: states.append(json.loads(m.data)), 100)
    node.create_subscription(String, '/reference/target', lambda m: targets.append(json.loads(m.data)), 20)
    node.create_subscription(String, '/reference/clarification', lambda m: questions.append(json.loads(m.data)), 20)
    client = node.create_client(Trigger, '/reference/reset')
    scene = dict(objects=detect_objects(make_table()))
    blue = dict(origin=[.5, .9], direction=[0., -1.])
    between = dict(origin=[.5, .9], direction=[-.24, -1.])
    results = []

    def publish(name, data):
        publishers[name].publish(String(data=data if isinstance(data, str) else json.dumps(data)))

    def spin(duration, with_scene=True, camera_healthy=True, mic_healthy=True):
        deadline = time.monotonic() + duration
        last_scene = 0.
        while time.monotonic() < deadline:
            if time.monotonic() - last_scene > .1:
                if with_scene:
                    publish('scene', scene)
                publish('camera_status', dict(healthy=camera_healthy, scene_ready=camera_healthy))
                publish('mic_status', dict(healthy=mic_healthy))
                last_scene = time.monotonic()
            rclpy.spin_once(node, timeout_sec=.01)

    def reset():
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.)
        assert future.done() and future.result().success
        spin(.15)
        states.clear()
        targets.clear()
        questions.clear()

    def check(name, reason, target_count):
        assert states and states[-1]['reason'] == reason, (name, states[-1:] or 'no state')
        assert len(targets) == target_count, (name, targets)
        results.append(dict(case=name, reason=reason, target_events=target_count, passed=True))

    try:
        assert client.wait_for_service(timeout_sec=12.), 'controller did not start'
        spin(.5)
        assert all(p.get_subscription_count() for p in publishers.values()), 'missing subscriptions'
        reset()
        publish('request', dict(text='Pick up this object', ray=blue))
        spin(.3)
        check('correct_blue', 'speech_and_pointing_agree', 1)
        assert targets[-1]['object']['color'] == 'blue'
        spin(.4)
        check('no_repeated_target', 'speech_and_pointing_agree', 1)
        reset()
        publish('request', dict(text='Pick up this object', ray=between))
        spin(.3)
        check('between_two', 'ambiguous_pointing', 0)
        assert len(questions) == 1 and len(questions[0]['candidates']) == 2
        reset()
        publish('request', dict(text='red', ray=blue))
        spin(.3)
        check('red_speech_blue_pointing', 'speech_pointing_conflict', 0)
        request_id = states[-1]['request_id']
        publish('confirm', dict(request_id=request_id - 1, object_id='blue_1'))
        spin(.2)
        check('reject_wrong_confirmation_id', 'speech_pointing_conflict', 0)
        publish('confirm', dict(request_id=request_id, object_id='blue_1'))
        spin(.3)
        check('explicit_confirmation', 'explicit_confirmation', 1)
        reset()
        publish('speech', 'Pick up this object')
        spin(.2)
        check('speech_waits_for_point', 'need_pointing', 0)
        publish('pointing', blue)
        spin(.3)
        check('speech_then_point', 'speech_and_pointing_agree', 1)
        reset()
        publish('pointing', blue)
        spin(.2)
        publish('request', dict(text='blue', ray=None))
        spin(.3)
        check('atomic_null_does_not_reuse_old_ray', 'need_pointing', 0)
        reset()
        publish('request', dict(text='red', ray=blue))
        spin(.2)
        old_request = states[-1]['request_id']
        scene = dict(objects=[dict(o, x=o['x'] + .01) for o in scene['objects']])
        spin(.3)
        publish('confirm', dict(request_id=old_request, object_id='blue_1'))
        spin(.2)
        check('scene_change_invalidates_confirmation', 'scene_changed', 0)
        publish('request', dict(text='blue', ray=dict(origin=[0, 0], direction=[0, 0])))
        spin(.2)
        check('zero_ray_rejected', 'invalid_input', 0)
        spin(1.2, with_scene=False)
        check('scene_timeout', 'scene_unavailable', 0)
        spin(.3)
        reset()
        publish('request', dict(text='Lấy vật màu đỏ', ray=blue))
        spin(.3)
        check('vietnamese_spoken_color_conflict', 'speech_pointing_conflict', 0)
        publish('speech', dict(text='màu xanh dương', confidence=.2, accepted=True))
        spin(.2)
        check('low_confidence_voice_not_confirmed', 'speech_pointing_conflict', 0)
        publish('speech', dict(text='xác nhận màu xanh dương', confidence=.95, accepted=True))
        spin(.3)
        check('vietnamese_voice_confirmation', 'explicit_confirmation', 1)
        reset()
        spin(.2, camera_healthy=False)
        publish('request', dict(text='blue', ray=blue))
        spin(.2, camera_healthy=False)
        check('camera_fault_blocks_target', 'camera_not_ready', 0)
        spin(.3)
        reset()
        spin(.2, mic_healthy=False)
        publish('request', dict(text='blue', ray=blue))
        spin(.2, mic_healthy=False)
        check('mic_fault_blocks_target', 'microphone_not_ready', 0)
        report = dict(source='image-derived objects, synthetic pointing and text over ROS',
                      results=results, passed=len(results))
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
        log.close()


if __name__ == '__main__':
    main()
