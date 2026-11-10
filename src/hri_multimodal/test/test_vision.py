import pytest
from hri_multimodal.vision import GestureFilter


def test_stationary_palm_inhibits_then_stops():
    f = GestureFilter()
    assert f.observe(0., 'Open_Palm', .9)[2]
    assert f.observe(.1, 'Open_Palm', .9)[0] == 'Palm pending'
    assert f.observe(.25, 'Open_Palm', .9)[2]
    assert f.observe(.45, 'Open_Palm', .9) == ('Open Palm', .9, False)


def test_wave_is_not_initially_latched_as_stop():
    f = GestureFilter()
    results=[]
    # Three strokes, including two direction changes; never hold still .4s.
    for i, x in enumerate([.4,.46,.54,.61,.53,.45,.38,.46,.54,.62]):
        results.append(f.observe(i*.08, 'Open_Palm', .95, x=x))
    assert 'Open Palm' not in [r[0] for r in results]
    assert results[-1][0] == 'Wave'


def test_wave_to_stationary_palm_stops():
    f = GestureFilter()
    for i, x in enumerate([.4,.5,.6,.5,.4,.5,.6]):
        f.observe(i*.08,'Open_Palm',.9,x=x)
    result=None
    for i in range(1,14):
        result=f.observe(.48+i*.05,'Open_Palm',.9,x=.6)
    assert result[0] == 'Open Palm'


def test_thumb_debounce_and_palm_resets_candidate():
    f = GestureFilter()
    assert f.observe(0.,'Thumb_Up',.9)[0] == 'Thumb pending'
    assert f.observe(.21,'Thumb_Up',.9)[0] == 'Thumb Up'
    f.observe(.25,'Open_Palm',.9)
    assert f.observe(.3,'Thumb_Up',.9)[0] == 'Thumb pending'


@pytest.mark.parametrize('label,score,hands', [('Thumb_Up',.2,1),('Thumb_Up',.9,2),
                                               ('None',0.,0),('Victory',.99,1)])
def test_uncertain_or_unmapped_hands_cannot_command_motion(label,score,hands):
    f = GestureFilter()
    f.observe(0.,label,score,hands)
    result=f.observe(.5,label,score,hands)
    assert result[0] not in ('Wave','Thumb Up')


def test_multiple_hands_open_palm_still_stops():
    assert GestureFilter().observe(0.,'Open_Palm',.8,2)[0] == 'Open Palm'


def test_multiple_hands_inhibit_motion():
    assert GestureFilter().observe(0.,'None',0.,2)[2]


def test_brief_tracking_dropout_preserves_wave_evidence_and_inhibits():
    f=GestureFilter()
    f.observe(0.,'Open_Palm',.9,x=.4)
    f.observe(.08,'Open_Palm',.9,x=.5)
    assert f.observe(.12,'None',0.,0)[2]
    for t,x in [(.16,.6),(.24,.5),(.32,.4),(.4,.5),(.48,.6)]:
        result=f.observe(t,'Open_Palm',.9,x=x)
    assert result[0]=='Wave'
    assert f.observe(.7,'None',0.,0)[0]=='No hand'
