"""Record a labelled live ROS trial and summarize false greetings."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import time

FIELDS = ('timestamp', 'source', 'scenario', 'expected_engaged', 'observed_engaged',
          'greetings', 'camera_valid', 'duration_s', 'video', 'notes')


def summarize(rows):
    valid = [r for r in rows if str(r['camera_valid']) == '1']
    counts = dict(tp=0, fp=0, tn=0, fn=0, invalid=len(rows) - len(valid))
    for row in valid:
        expected = str(row['expected_engaged']) == '1'
        observed = str(row['observed_engaged']) == '1'
        counts['tp' if expected and observed else 'fn' if expected else 'fp' if observed else 'tn'] += 1
    negatives = counts['fp'] + counts['tn']
    total = len(valid)
    counts['false_greeting_rate'] = counts['fp'] / negatives if negatives else None
    counts['accuracy'] = (counts['tp'] + counts['tn']) / total if total else None
    return counts


def append_trial(path, row):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size:
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(FIELDS):
                raise ValueError(f'{path} has an incompatible CSV header; use a new output path')
            sources = {r['source'] for r in reader}
            if sources - {row['source']}:
                raise ValueError('Keep live and synthetic trials in separate CSV files')
    fresh = not path.exists() or path.stat().st_size == 0
    with path.open('a', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if fresh:
            writer.writeheader()
        writer.writerow(row)
    with path.open(newline='') as stream:
        return summarize(list(csv.DictReader(stream)))


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True, help='look_only / head_hand / head_speech / passerby')
    parser.add_argument('--expected', required=True, choices=('yes', 'no'))
    parser.add_argument('--duration', type=float, default=8.)
    parser.add_argument('--output', default='artifacts/hri_engagement/live_trials.csv')
    parser.add_argument('--video', default='', help='Path to the video for this trial')
    parser.add_argument('--notes', default='')
    parser.add_argument('--source', choices=('live', 'synthetic'), default='live',
                        help='Use synthetic when vision comes from a simulator')
    options, ros_args = parser.parse_known_args(args)
    if not .5 <= options.duration <= 600:
        parser.error('duration must be between .5 and 600 seconds')
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    rclpy.init(args=ros_args)
    node = Node('engagement_trial_recorder')
    samples, responses = [], []
    started = False
    camera_ready = False

    def state(message):
        nonlocal camera_ready
        try:
            data = json.loads(message.data)
            camera_ready = bool(data.get('camera_fresh'))
            if started:
                samples.append(data)
        except (ValueError, AttributeError):
            pass

    def response(message):
        if started:
            responses.append(message.data)

    node.create_subscription(String, '/engagement/state', state, 100)
    node.create_subscription(String, '/engagement/response', response, 10)
    client = node.create_client(Trigger, '/engagement/reset')
    try:
        if not client.wait_for_service(timeout_sec=5.):
            raise RuntimeError('Engagement controller is unavailable; check ROS_DOMAIN_ID')
        print('Chuẩn bị: hạ tay, quay đầu khỏi camera. Bắt đầu sau 3 giây.', flush=True)
        deadline = time.monotonic() + 3.
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.)
        if not future.done() or not future.result() or not future.result().success:
            raise RuntimeError('Could not reset the FSM before the trial')
        # Reset deliberately invalidates old visual evidence. Wait for a new
        # frame so that this startup transient does not invalidate every trial.
        camera_ready = False
        deadline = time.monotonic() + 3.
        while not camera_ready and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.02)
        if not camera_ready:
            print('Chưa có frame camera mới; lượt thử sẽ được đánh dấu invalid.', flush=True)
        started = True
        print(f'BẮT ĐẦU: {options.scenario}, {options.duration:g} giây', flush=True)
        start = time.monotonic()
        while time.monotonic() - start < options.duration:
            rclpy.spin_once(node, timeout_sec=.05)
        started = False
        healthy = [s for s in samples if s.get('camera_fresh')]
        valid = len(samples) >= 5 and len(healthy) == len(samples)
        engaged = any(s.get('state') == 'ENGAGED' for s in samples) or bool(responses)
        row = dict(timestamp=datetime.now().astimezone().isoformat(timespec='seconds'),
                   source=options.source, scenario=options.scenario,
                   expected_engaged=int(options.expected == 'yes'), observed_engaged=int(engaged),
                   greetings=len(responses), camera_valid=int(valid), duration_s=options.duration,
                   video=options.video, notes=options.notes)
        print(json.dumps(row, ensure_ascii=False, indent=2))
        print(json.dumps(append_trial(options.output, row), indent=2))
    except KeyboardInterrupt:
        print('Lượt thử đã hủy; không ghi vào bảng.')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
