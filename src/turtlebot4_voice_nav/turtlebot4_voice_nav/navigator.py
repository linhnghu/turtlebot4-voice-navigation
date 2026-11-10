"""Asynchronous Nav2 sequencer. A route advances only on SUCCEEDED."""
import json
import math
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
from geometry_msgs.msg import Point
from irobot_create_msgs.action import Undock
from irobot_create_msgs.msg import DockStatus
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException
from visualization_msgs.msg import Marker, MarkerArray

from .commands import CommandParser, CommandError
from .segmentation import load_regions


def latched():
    return QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Navigator(Node):
    def __init__(self):
        super().__init__('voice_navigator')
        self.config, self.grid, self.labels = load_regions(
            self.declare_parameter('regions_file', '').value,
            self.declare_parameter('map_file', '').value or None)
        self.regions = {r['id']: r for r in self.config['regions']}
        self.parser = CommandParser(self.config['regions'])
        self.goal_timeout = float(self.declare_parameter('goal_timeout', 240.0).value)
        self.minimum_confidence = float(self.declare_parameter('minimum_confidence', .65).value)
        self.max_speech_age = float(self.declare_parameter('max_speech_age', 15.0).value)
        self.journal = Path(self.declare_parameter('journal', 'artifacts/voice_nav/events.jsonl').value)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.status_pub = self.create_publisher(String, '/voice_nav/status', latched())
        self.markers = self.create_publisher(MarkerArray, '/voice_nav/regions', latched())
        self.create_subscription(String, '/voice_nav/command', self.on_text, 10)
        self.create_subscription(String, '/voice_nav/transcript', self.on_speech, 10)
        self.create_subscription(OccupancyGrid, '/map', self.on_map, latched())
        self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.nav = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.undock = ActionClient(self, Undock, '/undock')
        self.lifecycle = self.create_client(GetState, '/bt_navigator/get_state')
        self.nav_active = False
        self.lifecycle_received = 0.
        self.lifecycle_pending = False
        self.lifecycle_future = None
        self.lifecycle_started = 0.
        self.next_lifecycle_check = 0.
        self.map_valid = False
        self.dock = None
        self.dock_received = 0.
        self.busy = False
        self.route = []
        self.completed = []
        self.goal_handle = None
        self.cancel_requested = False
        self.cancel_sent = False
        self.stage = ''
        self.last_feedback = 0.
        self.ready_before = None
        # Wall-clock watchdog still runs if simulation is paused.
        self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(.25, self.tick, clock=self.wall_clock)
        self.publish_markers()
        self.emit('WAITING', 'Đang chờ bản đồ, định vị và Nav2.')

    def emit(self, state, message, **fields):
        data = dict(state=state, message=message, busy=self.busy,
                    route=list(self.route), completed=list(self.completed),
                    wall_time=time.time(), **fields)
        encoded = json.dumps(data, ensure_ascii=False)
        self.status_pub.publish(String(data=encoded))
        with self.journal.open('a') as stream:
            stream.write(encoded + '\n')
        self.get_logger().info(encoded)

    def on_dock(self, msg):
        self.dock, self.dock_received = msg, time.monotonic()

    def on_map(self, msg):
        g, info = self.grid, msg.info
        q = info.origin.orientation
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1-2*(q.y*q.y + q.z*q.z))
        valid = (msg.header.frame_id == 'map' and info.width == g.width and
                 info.height == g.height and abs(info.resolution-g.resolution) < 1e-6 and
                 abs(info.origin.position.x-g.origin[0]) < 1e-5 and
                 abs(info.origin.position.y-g.origin[1]) < 1e-5 and
                 abs(math.atan2(math.sin(yaw-g.origin[2]), math.cos(yaw-g.origin[2]))) < 1e-5)
        if valid:
            data = np.flipud(np.asarray(msg.data).reshape(g.height, g.width))
            valid = np.array_equal(data == 0, g.free) and np.array_equal(data == 100, g.occupied)
        self.map_valid = bool(valid)
        if not valid:
            self.emit('MAP_MISMATCH', 'Bản đồ Nav2 khác bản đồ đã phân vùng.')
            if self.busy:
                self.cancel('Bản đồ thay đổi khi đang điều hướng.')

    def pose(self):
        try:
            transform = self.tf.lookup_transform('map', 'base_link', rclpy.time.Time())
            stamp = rclpy.time.Time.from_msg(transform.header.stamp)
            age = (self.get_clock().now() - stamp).nanoseconds / 1e9
            if not -.5 <= age <= 2.:
                return None
            p = transform.transform.translation
            return [p.x, p.y]
        except TransformException:
            return None

    def ready(self):
        return (self.map_valid and self.nav_active and time.monotonic()-self.lifecycle_received < 5.
                and self.nav.server_is_ready() and self.pose() is not None and
                self.dock is not None and time.monotonic()-self.dock_received < 5.)

    def on_text(self, msg):
        self.command(msg.data, 'text')

    def on_speech(self, msg):
        try:
            data = json.loads(msg.data)
            text = data['text']
            if not isinstance(text, str):
                raise ValueError('text must be a string')
            # A recognized STOP can cancel even when confidence is low.
            try:
                is_stop = self.parser.parse(text).kind == 'stop'
            except CommandError:
                is_stop = False
            confidence = float(data['confidence'])
            age = time.time() - float(data['captured_at'])
            if not math.isfinite(age) or not -.5 <= age <= self.max_speech_age:
                self.emit('STALE_SPEECH', 'Bỏ qua câu nói đã quá hạn.')
                return
            if not is_stop and (not math.isfinite(confidence) or not 0 <= confidence <= 1
                                or confidence < self.minimum_confidence):
                self.emit('LOW_CONFIDENCE', 'Nghe chưa rõ, hãy nói lại.', text=text)
                return
            self.command(text, 'speech')
        except (ValueError, KeyError, TypeError) as exc:
            self.emit('INVALID_SPEECH', str(exc))

    def command(self, text, source):
        try:
            command = self.parser.parse(text)
        except CommandError as exc:
            self.emit(exc.code, str(exc), text=text, source=source)
            return
        if command.kind == 'stop':
            self.cancel('Đã nhận lệnh dừng.')
            return
        if self.busy:
            self.emit('BUSY', 'Robot đang thực hiện hành trình. Dừng trước khi gửi lệnh mới.', text=text)
            return
        if not self.ready():
            self.emit('NOT_READY', 'Chưa có bản đồ khớp, TF mới, dock status hoặc Nav2.', text=text)
            return
        self.busy = True
        self.cancel_requested = self.cancel_sent = False
        self.route = list(command.route)
        self.completed = []
        self.emit('ACCEPTED', 'Đã nhận hành trình: ' + ' → '.join(self.route), text=text, source=source)
        if self.dock.is_docked:
            if not self.undock.server_is_ready():
                self.finish('FAILED', 'Không có action undock.')
                return
            self.stage = 'undock'
            self.send(self.undock, Undock.Goal())
        else:
            self.next_goal()

    def next_goal(self):
        if not self.route:
            self.finish('SUCCEEDED', 'Đã đến đúng các khu vực yêu cầu.')
            return
        if not self.ready():
            self.finish('FAILED', 'Mất bản đồ hoặc định vị trước chặng tiếp theo.')
            return
        self.stage = 'navigate'
        region = self.regions[self.route[0]]
        target = region['goal']
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(target['x'])
        goal.pose.pose.position.y = float(target['y'])
        goal.pose.pose.orientation.z = math.sin(target['yaw']/2)
        goal.pose.pose.orientation.w = math.cos(target['yaw']/2)
        self.emit('SENDING', f"Đang đi đến {region['id']}", target=target)
        self.send(self.nav, goal)

    def send(self, client, goal):
        self.started = time.monotonic()
        self.goal_handle = None
        client.send_goal_async(goal, feedback_callback=self.feedback).add_done_callback(self.accepted)

    def accepted(self, future):
        try:
            handle = future.result()
        except Exception as exc:
            # Transport failure has an ambiguous server outcome. Keep busy until
            # the operator resolves it; never send another potentially competing goal.
            self.emit('ACTION_ERROR', f'Lỗi gửi action: {exc}; kiểm tra Nav2 rồi khởi động lại.')
            self.cancel_requested = True
            return
        if not handle.accepted:
            self.finish('CANCELED' if self.cancel_requested else 'REJECTED', 'Action không được chấp nhận.')
            return
        self.goal_handle = handle
        handle.get_result_async().add_done_callback(self.result)
        if self.cancel_requested:
            self.request_cancel()
        else:
            self.emit('UNDOCKING' if self.stage == 'undock' else 'NAVIGATING', 'Action đang chạy.')

    def feedback(self, msg):
        if (self.busy and self.goal_handle and self.stage == 'navigate' and
                not self.cancel_requested and time.monotonic()-self.last_feedback > 1):
            self.last_feedback = time.monotonic()
            self.emit('NAVIGATING', 'Đang di chuyển theo Nav2.',
                      distance_remaining=round(msg.feedback.distance_remaining, 2), xy=self.pose())

    def result(self, future):
        try:
            result = future.result()
        except Exception as exc:
            self.emit('ACTION_ERROR', f'Lỗi nhận kết quả: {exc}; kiểm tra Nav2 rồi khởi động lại.')
            self.cancel_requested = True
            return
        self.goal_handle = None
        if self.cancel_requested:
            self.finish('CANCELED', 'Đã kết thúc action; hành trình bị hủy.', action_status=result.status)
        elif result.status != 4:
            self.finish('FAILED', 'Nav2/undock không thành công; dừng hành trình.', action_status=result.status)
        elif self.stage == 'undock':
            if result.result.is_docked:
                self.finish('FAILED', 'Robot vẫn đang ở dock.')
            else:
                # Undock result is authoritative; dock topic can lag a callback.
                self.dock.is_docked = False
                self.next_goal()
        else:
            reached = self.route.pop(0)
            self.completed.append(reached)
            self.emit('WAYPOINT_SUCCEEDED', f'Đã đến khu vực {reached}.', action_status=result.status, xy=self.pose())
            self.next_goal()

    def cancel(self, reason):
        if not self.busy:
            self.emit('STOPPED', 'Robot không có hành trình đang chạy.')
            return
        self.cancel_requested = True
        self.emit('CANCELING', reason)
        # Includes the interval before send_goal_async returns its handle.
        if self.goal_handle and not self.cancel_sent:
            self.request_cancel()

    def request_cancel(self):
        self.cancel_sent = True
        self.goal_handle.cancel_goal_async().add_done_callback(self.cancel_ack)

    def cancel_ack(self, future):
        try:
            response = future.result()
            if not response.goals_canceling and self.busy:
                self.emit('CANCEL_REJECTED', 'Server chưa xác nhận hủy; đang chờ kết quả action.')
                self.cancel_sent = False
        except Exception as exc:
            self.emit('CANCEL_ERROR', str(exc))
            self.cancel_sent = False

    def finish(self, state, message, **fields):
        self.busy = False
        self.route = []
        self.goal_handle = None
        self.emit(state, message, **fields)
        self.ready_before = self.ready()

    def tick(self):
        now = time.monotonic()
        if self.lifecycle_pending and now-self.lifecycle_started > 3.:
            previous = self.lifecycle_future
            self.lifecycle_future = None
            self.lifecycle_pending = False
            self.nav_active = False
            self.lifecycle.remove_pending_request(previous)
            previous.cancel()
        if now >= self.next_lifecycle_check and not self.lifecycle_pending:
            self.next_lifecycle_check = now + 2.
            if self.lifecycle.service_is_ready():
                self.lifecycle_pending = True
                self.lifecycle_started = now
                self.lifecycle_future = self.lifecycle.call_async(GetState.Request())
                self.lifecycle_future.add_done_callback(self.lifecycle_state)
            else:
                self.nav_active = False
        if self.busy:
            timeout = 75 if self.stage == 'undock' else self.goal_timeout
            if time.monotonic()-self.started > timeout and not self.cancel_requested:
                self.cancel('Quá thời gian cho phép; hủy hành trình.')
            elif not self.cancel_requested and (not self.map_valid or self.pose() is None):
                self.cancel('Mất bản đồ hoặc TF định vị.')
        else:
            ready = self.ready()
            if ready != self.ready_before:
                self.ready_before = ready
                self.emit('READY' if ready else 'WAITING',
                          'Sẵn sàng nhận lệnh.' if ready else 'Đang chờ bản đồ, TF và Nav2.')

    def lifecycle_state(self, future):
        if future is not self.lifecycle_future:
            return
        self.lifecycle_future = None
        self.lifecycle_pending = False
        try:
            self.nav_active = future.result().current_state.id == 3
            self.lifecycle_received = time.monotonic()
        except Exception:
            self.nav_active = False

    def publish_markers(self):
        markers = MarkerArray()
        for r in self.regions.values():
            for text in (False, True):
                m = Marker()
                m.header.frame_id = 'map'
                m.ns = 'semantic_regions'
                m.id = r['label']*2 + int(text)
                m.type = Marker.TEXT_VIEW_FACING if text else Marker.CUBE_LIST
                m.action = Marker.ADD
                m.pose.orientation.w = 1.
                m.color.r, m.color.g, m.color.b = (c/255 for c in r['color'])
                m.color.a = 1. if text else .40
                if text:
                    m.pose.position.x = r['goal']['x']
                    m.pose.position.y = r['goal']['y']
                    m.pose.position.z = .65
                    m.scale.z = .40
                    m.text = r['id']
                else:
                    m.scale.x = m.scale.y = self.grid.resolution * 2
                    m.scale.z = .015
                    # Sample every other cell to limit RViz message size.
                    for v, u in np.argwhere(self.labels[::2, ::2] == r['label']):
                        x, y = self.grid.pixel_to_world(int(u)*2, int(v)*2)
                        m.points.append(Point(x=float(x), y=float(y), z=.025))
                markers.markers.append(m)
        self.markers.publish(markers)


def main(args=None):
    rclpy.init(args=args)
    node = Navigator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.busy and node.goal_handle and rclpy.ok():
            node.cancel('Đóng node; hủy action đang chạy.')
            deadline = time.monotonic()+3
            while node.busy and time.monotonic() < deadline and rclpy.ok():
                rclpy.spin_once(node, timeout_sec=.1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
