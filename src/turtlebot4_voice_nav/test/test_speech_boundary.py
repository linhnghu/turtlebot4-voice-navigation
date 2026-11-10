import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from turtlebot4_voice_nav.commands import CommandParser
from turtlebot4_voice_nav.navigator import Navigator


def harness():
    return SimpleNamespace(
        parser=CommandParser([dict(id='A', name='phòng học', aliases=['khu vực A'])]),
        max_speech_age=15., minimum_confidence=.65, emit=Mock(), command=Mock())


def deliver(h, **overrides):
    data = dict(text='Đi đến khu vực A', confidence=.9, captured_at=time.time())
    data.update(overrides)
    Navigator.on_speech(h, SimpleNamespace(data=json.dumps(data)))


def test_final_speech_reaches_command_parser():
    h = harness()
    deliver(h)
    h.command.assert_called_once_with('Đi đến khu vực A', 'speech')


@pytest.mark.parametrize('confidence', [.2, -1, 1.2, float('nan'), float('inf')])
def test_uncertain_or_invalid_movement_is_not_sent(confidence):
    h = harness()
    deliver(h, confidence=confidence)
    h.command.assert_not_called()
    assert h.emit.call_args.args[0] == 'LOW_CONFIDENCE'


def test_stop_can_cancel_even_with_low_recognition_confidence():
    h = harness()
    deliver(h, text='dừng lại', confidence=.05)
    h.command.assert_called_once_with('dừng lại', 'speech')


@pytest.mark.parametrize('stamp', [time.time()-60, time.time()+60, float('nan')])
def test_stale_future_or_invalid_timestamp_is_rejected(stamp):
    h = harness()
    deliver(h, captured_at=stamp)
    h.command.assert_not_called()
    assert h.emit.call_args.args[0] == 'STALE_SPEECH'


def test_non_string_transcript_is_rejected():
    h = harness()
    deliver(h, text=['Đi đến A'])
    h.command.assert_not_called()
    assert h.emit.call_args.args[0] == 'INVALID_SPEECH'
