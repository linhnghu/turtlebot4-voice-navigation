"""15 deterministic synthetic cue trials; does not validate a camera or a person."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .core import EngagementEngine
from .trials import append_trial

SCENARIOS = [
    ('look_only', False), ('look_with_one_hand_spike', False), ('look_with_unknown_speech', False),
    ('head_hand', True), ('head_hand_noisy', True), ('head_hand_delayed_head', True),
    ('head_speech_hello', True), ('head_speech_excuse', True), ('head_speech_vietnamese', True),
    ('passerby', False), ('passerby_brief_glance', False), ('speech_without_facing', False),
    ('head_hand_speech', True), ('head_speech_before_head', True), ('head_hand_no_repeat', True),
]


def run_scenario(name):
    engine = EngagementEngine()
    states = []
    for frame in range(81):
        now = frame * .05
        face, head, hand = True, True, False
        if name.startswith('passerby'):
            face = .4 <= now <= 1.5
            head = name == 'passerby_brief_glance' and .7 <= now <= .85
        if name == 'speech_without_facing':
            head = False
        if 'hand' in name and name != 'look_with_one_hand_spike':
            hand = .8 <= now <= 2.
        if name == 'look_with_one_hand_spike':
            hand = frame == 20
        if name == 'head_hand_noisy' and frame in (20, 25):
            hand = False
        if name in ('head_hand_delayed_head', 'head_speech_before_head'):
            head = now >= 1.2
        engine.observe(now, healthy=True, face_present=face, facing=head, hand_raised=hand)
        if frame == 16:
            text = {'head_speech_hello': 'Hello robot', 'head_speech_excuse': 'Excuse me',
                    'head_speech_vietnamese': 'Xin chào robot', 'speech_without_facing': 'Hello robot',
                    'head_hand_speech': 'Hello robot', 'head_speech_before_head': 'Hello robot',
                    'look_with_unknown_speech': 'not hello robot'}.get(name)
            if text:
                engine.speech(now, text)
        states.append(engine.update(now))
    return states


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/hri_engagement/synthetic_trials.csv')
    options = parser.parse_args(args)
    path = Path(options.output)
    if path.exists():
        parser.error('output already exists; choose a new path to preserve previous results')
    failed = []
    summary = None
    for name, expected in SCENARIOS:
        states = run_scenario(name)
        observed = any(s['state'] == 'ENGAGED' for s in states)
        greetings = states[-1]['greeting_count']
        if observed != expected or greetings != int(expected):
            failed.append(name)
        summary = append_trial(path, dict(
            timestamp=datetime.now(timezone.utc).isoformat(timespec='seconds'), source='synthetic',
            scenario=name, expected_engaged=int(expected), observed_engaged=int(observed),
            greetings=greetings, camera_valid=1, duration_s=4., video='',
            notes='Generated cue booleans, NOT webcam/person validation'))
    print(json.dumps(dict(source='synthetic', trials=15, failed=failed, **summary), indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
