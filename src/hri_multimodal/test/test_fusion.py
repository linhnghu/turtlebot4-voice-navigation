import pytest

from hri_multimodal.fusion import FusionEngine, fusion_decision


@pytest.mark.parametrize('voice,hand,cv,cg,action,reason', [
    ('Move forward', 'Thumb Up', .95, .95, 'forward', 'agreement'),
    ('Come here', 'Wave', .95, .95, 'come', 'agreement'),
    ('Move forward', 'Open Palm', .99, .01, 'stop', 'stop_priority'),
    ('Stop', 'Thumb Up', .01, .99, 'stop', 'stop_priority'),
    ('Stop', 'Open Palm', 1., 1., 'stop', 'stop_priority'),
    ('Move forward', None, .95, 0., 'forward', 'voice_only'),
    (None, 'Thumb Up', 0., .95, 'forward', 'gesture_only'),
    (None, 'Wave', 0., .95, 'come', 'gesture_only'),
    ('Move forward', 'Wave', .95, .95, 'stop', 'conflict'),
    ('Come here', 'Thumb Up', .95, .95, 'stop', 'conflict'),
    ('Move forward', 'Thumb Up', .2, .3, 'idle', 'no_reliable_input'),
    (None, None, 0., 0., 'idle', 'no_reliable_input'),
    ('dance', 'Fist', 1., 1., 'idle', 'no_reliable_input'),
    ('do not move forward', None, 1., 0., 'idle', 'no_reliable_input'),
    ('ĐI THẲNG!', 'Thumb_Up', .65, .65, 'forward', 'agreement'),
    ('Lại đây', 'Wave', 1., 1., 'come', 'agreement'),
    ('Dừng lại', 'Wave', .1, 1., 'stop', 'stop_priority'),
    ('Move forward', 'Open Palm', 1., 0., 'forward', 'voice_only'),
    ('Move forward', 'Wave', .2, .9, 'come', 'gesture_only'),
])
def test_fusion_table(voice, hand, cv, cg, action, reason):
    result = fusion_decision(voice, hand, cv, cg)
    assert (result.action, result.reason) == (action, reason)


@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -1., 1.1, True, '1', None])
def test_invalid_confidence_stops(confidence):
    assert fusion_decision('Move forward', None, confidence, 0.).action == 'stop'


def test_stop_latch_and_reset_clear_old_motion():
    engine = FusionEngine()
    engine.ingest('voice', dict(text='Move forward'))
    assert engine.decision().action == 'forward'
    engine.ingest('gesture', dict(text='Open Palm', confidence=.01))
    engine.snapshot(dict(voice=dict(text='Move forward'), gesture=dict(text='Thumb Up')))
    assert engine.decision().action == 'stop'
    engine.reset()
    assert engine.decision().action == 'idle'
    engine.ingest('gesture', dict(text='Wave'))
    assert engine.decision().action == 'come'


def test_timeout_and_one_channel_expiry():
    now = [0.]
    engine = FusionEngine(ttl=3., clock=lambda: now[0])
    engine.ingest('voice', dict(text='Move forward'))
    now[0] = 2.
    engine.ingest('gesture', dict(text='Thumb Up'))
    now[0] = 3.
    assert engine.decision().reason == 'gesture_only'
    now[0] = 5.
    assert engine.decision().action == 'idle'


def test_snapshot_is_atomic():
    engine = FusionEngine()
    engine.ingest('voice', dict(text='Move forward'))
    # Updating gesture first against old voice would falsely latch a conflict.
    engine.snapshot(dict(voice=dict(text='Come here'), gesture=dict(text='Wave')))
    assert engine.decision().action == 'come'
    assert not engine.latched


@pytest.mark.parametrize('payload', [[], 'hello', {'voice': []}, {'voice': {'text': 1}},
                                      {'voice': {'text': 'Stop', 'confidence': 'x'}},
                                      {'unexpected': 1}])
def test_malformed_snapshot_fails_closed(payload):
    engine = FusionEngine()
    engine.snapshot(payload)
    assert engine.decision().action == 'stop'
    assert engine.latched
