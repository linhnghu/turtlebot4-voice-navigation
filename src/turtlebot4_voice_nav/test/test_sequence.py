from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from rclpy.task import Future

from turtlebot4_voice_nav.navigator import Navigator


class Harness:
    command = Navigator.command
    accepted = Navigator.accepted
    result = Navigator.result
    cancel = Navigator.cancel
    request_cancel = Navigator.request_cancel
    cancel_ack = Navigator.cancel_ack
    finish = Navigator.finish

    def __init__(self):
        self.busy = True
        self.cancel_requested = False
        self.cancel_sent = False
        self.goal_handle = None
        self.completed = []
        self.route = ['A', 'B']
        self.stage = 'navigate'
        self.emit = Mock()
        self.next_goal = Mock()
        self.ready = Mock(return_value=True)
        self.pose = Mock(return_value=[-3., 0.])


def future(value):
    f = Future()
    f.set_result(value)
    return f


def test_successful_a_advances_to_b():
    h = Harness()
    h.result(future(NS(status=4)))
    assert h.completed == ['A']
    assert h.route == ['B']
    h.next_goal.assert_called_once()


@pytest.mark.parametrize('status', [5, 6, 0])
def test_failure_never_advances_to_second_area(status):
    h = Harness()
    h.result(future(NS(status=status)))
    h.next_goal.assert_not_called()
    assert h.route == [] and not h.busy
    assert h.emit.call_args.args[0] == 'FAILED'


def test_stop_before_handle_acceptance_cancels_when_handle_arrives():
    h = Harness()
    h.cancel('stop during acceptance')
    assert h.busy and h.cancel_requested
    result_future, cancel_future = Future(), Future()
    handle = NS(accepted=True, get_result_async=Mock(return_value=result_future),
                cancel_goal_async=Mock(return_value=cancel_future))
    h.accepted(future(handle))
    handle.cancel_goal_async.assert_called_once()
    assert h.busy
    h.result(future(NS(status=5)))
    assert not h.busy and h.route == []
    h.next_goal.assert_not_called()


def test_stop_at_success_boundary_suppresses_remaining_route():
    h = Harness()
    h.cancel_requested = True
    h.result(future(NS(status=4)))
    assert not h.busy and not h.route
    assert h.emit.call_args.args[0] == 'CANCELED'
    h.next_goal.assert_not_called()


def test_rejected_goal_finishes_route():
    h = Harness()
    h.accepted(future(NS(accepted=False)))
    assert not h.busy and h.route == []
    h.next_goal.assert_not_called()


def test_rejected_cancel_does_not_unlock_busy_state():
    h = Harness()
    h.cancel_requested = True
    h.cancel_ack(future(NS(goals_canceling=[])))
    assert h.busy and h.cancel_requested
    h.next_goal.assert_not_called()


def test_transport_failure_does_not_send_new_goal():
    h = Harness()
    f = Future()
    f.set_exception(RuntimeError('connection lost'))
    h.accepted(f)
    assert h.busy and h.cancel_requested
    h.next_goal.assert_not_called()
