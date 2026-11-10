from types import SimpleNamespace
from unittest.mock import Mock, patch

from rclpy.task import Future

from turtlebot4_voice_nav.navigator import Navigator


def test_lost_lifecycle_response_can_be_retried():
    pending = Future()
    lifecycle = Mock()
    lifecycle.service_is_ready.return_value = False
    node = SimpleNamespace(
        lifecycle_pending=True, lifecycle_future=pending, lifecycle_started=0.,
        next_lifecycle_check=2., nav_active=True, lifecycle=lifecycle,
        busy=False, ready=Mock(return_value=False), ready_before=False,
        emit=Mock())
    with patch('turtlebot4_voice_nav.navigator.time.monotonic', return_value=4.):
        Navigator.tick(node)
    lifecycle.remove_pending_request.assert_called_once_with(pending)
    assert pending.cancelled()
    assert not node.lifecycle_pending
    assert node.lifecycle_future is None
    assert not node.nav_active


def test_expired_lifecycle_callback_cannot_replace_new_readiness():
    node = SimpleNamespace(lifecycle_future=Future(), lifecycle_pending=True,
                           nav_active=True, lifecycle_received=123.)
    Navigator.lifecycle_state(node, Future())
    assert node.nav_active
    assert node.lifecycle_pending
    assert node.lifecycle_received == 123.
