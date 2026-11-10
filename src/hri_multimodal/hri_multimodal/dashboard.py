"""Qt dashboard, simulated gesture labels, scripted demo and video capture."""
import json
import math
from pathlib import Path
import signal
import subprocess
import time

from PyQt5 import QtCore, QtGui, QtWidgets
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point, Pose2D
from std_msgs.msg import String
from std_srvs.srv import Trigger


class Arena(QtWidgets.QWidget):
    target_changed = QtCore.pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(620, 460)
        self.pose = (1.2, 1.2, 0.0)
        self.target = (2., 4.)
        self.trail = []
        self.state = {}

    def transform(self, x, y):
        return QtCore.QPointF(35 + x * self.scale, self.height() - 35 - y * self.scale)

    @property
    def scale(self):
        return min((self.width() - 70) / 8, (self.height() - 70) / 6)

    def mousePressEvent(self, event):
        x = (event.x() - 35) / self.scale
        y = (self.height() - 35 - event.y()) / self.scale
        if .4 <= x <= 7.6 and .4 <= y <= 5.6:
            self.target = (x, y)
            self.target_changed.emit(x, y)
            self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor('#101f30'))
        p.setPen(QtGui.QPen(QtGui.QColor('#27394c'), 1))
        for x in range(9):
            p.drawLine(self.transform(x, 0), self.transform(x, 6))
        for y in range(7):
            p.drawLine(self.transform(0, y), self.transform(8, y))
        p.setPen(QtGui.QColor('#718a9f'))
        p.drawText(35, 23, 'LAB 8 × 6 m   •   Bấm trong bản đồ để đặt người gọi')
        p.setPen(QtGui.QPen(QtGui.QColor('#438e9c'), 2))
        for a, b in zip(self.trail, self.trail[1:]):
            p.drawLine(self.transform(*a), self.transform(*b))
        center = self.transform(*self.target)
        p.setBrush(QtGui.QColor('#f8bd61'))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(center, 12, 12)
        p.setPen(QtGui.QColor('#f8bd61'))
        p.drawText(center + QtCore.QPointF(18, 5), 'NGƯỜI GỌI')
        x, y, heading = self.pose
        robot = self.transform(x, y)
        color = '#fa7878' if self.state.get('latched') else '#54ddbd'
        p.setBrush(QtGui.QColor(color))
        p.setPen(QtGui.QPen(QtGui.QColor('#e8ffff'), 2))
        radius = .22 * self.scale
        p.drawEllipse(robot, radius, radius)
        p.setPen(QtGui.QPen(QtGui.QColor('#102539'), 3))
        p.drawLine(robot, robot + QtCore.QPointF(math.cos(heading) * radius,
                                                -math.sin(heading) * radius))
        p.setPen(QtGui.QColor('#d0e0ed'))
        p.drawText(35, self.height() - 10,
                   f'x = {x:.2f} m    y = {y:.2f} m    θ = {math.degrees(heading):.0f}°')


class Dashboard(QtWidgets.QWidget):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setWindowTitle('HRI • Voice + Gesture • ROS 2')
        self.setFixedSize(1120, 780)
        self.setStyleSheet('''
            QWidget { background: #f3f6fa; color: #142d43; font: 14px "DejaVu Sans"; }
            QLabel#heading { font-size: 27px; font-weight: bold; }
            QLabel#action { font-size: 24px; font-weight: bold; color: #078679; }
            QPushButton { background: #dceaeF; padding: 10px; border: none; border-radius: 6px; }
            QPushButton:hover { background: #bcdcdF; }
            QPushButton#send { background: #0b9287; color: white; font-weight: bold; }
            QPushButton#stop { background: #c43d48; color: white; font-weight: bold; }
            QLineEdit, QComboBox, QDoubleSpinBox { background: white; padding: 8px; border: 1px solid #d4dfe8; }
            QTextEdit { background: white; border: 1px solid #d4dfe8; font-size: 12px; }
        ''')
        self.input_pub = node.create_publisher(String, '/hri/input', 10)
        self.voice_pub = node.create_publisher(String, '/hri/voice', 10)
        self.external_camera = bool(node.declare_parameter('external_camera', False).value)
        self.backend = str(node.declare_parameter('backend', 'Mô phỏng động học 2D').value)
        self.target_pub = node.create_publisher(Point, '/hri/target', 10)
        self.reset_client = node.create_client(Trigger, '/hri/reset_stop')
        node.create_subscription(Pose2D, '/hri/pose', self.on_pose, 10)
        node.create_subscription(String, '/hri/decision', self.on_state, 10)
        self.state = {}
        self.last_log = None
        self.demo_started = None
        self.demo_index = 0
        self.video = None
        self.evidence = None
        self.frames = 0
        self.record_dir = str(node.declare_parameter('record_dir', '').value)
        self.demo = bool(node.declare_parameter('demo', False).value)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        heading = QtWidgets.QLabel('Robot nhận lệnh bằng giọng nói và cử chỉ')
        heading.setObjectName('heading')
        root.addWidget(heading)
        root.addWidget(QtWidgets.QLabel('BÀI 01  /  ROS 2 HUMBLE     •     STOP được ưu tiên ở cả hai kênh'))
        body = QtWidgets.QHBoxLayout()
        root.addLayout(body, 1)
        self.arena = Arena()
        self.arena.target_changed.connect(self.send_target)
        body.addWidget(self.arena, 3)
        controls = QtWidgets.QVBoxLayout()
        body.addLayout(controls, 2)
        controls.addWidget(QtWidgets.QLabel('VERBAL  /  Câu nói hoặc văn bản'))
        self.voice = QtWidgets.QComboBox()
        self.voice.setEditable(True)
        self.voice.addItems(['Move forward', 'Come here', 'Stop', ''])
        controls.addWidget(self.voice)
        controls.addWidget(QtWidgets.QLabel('GESTURE  /  Webcam thật' if self.external_camera
                                           else 'GESTURE  /  Nhãn cử chỉ mô phỏng'))
        self.gesture = QtWidgets.QComboBox()
        self.gesture.addItems(['Thumb Up', 'Wave', 'Open Palm', 'None'])
        if self.external_camera:
            self.gesture.setCurrentText('None')
            self.gesture.setEnabled(False)
        controls.addWidget(self.gesture)
        confidence = QtWidgets.QHBoxLayout()
        self.conf_voice, self.conf_hand = QtWidgets.QDoubleSpinBox(), QtWidgets.QDoubleSpinBox()
        for label, spin in [('Tin cậy lời nói', self.conf_voice), ('Tin cậy cử chỉ', self.conf_hand)]:
            col = QtWidgets.QVBoxLayout()
            col.addWidget(QtWidgets.QLabel(label))
            spin.setRange(0., 1.)
            spin.setSingleStep(.05)
            spin.setValue(.95)
            col.addWidget(spin)
            confidence.addLayout(col)
        controls.addLayout(confidence)
        send = QtWidgets.QPushButton('GỬI HAI KÊNH')
        self.send_button = send
        if self.external_camera:
            send.setText('GỬI LỆNH NÓI  •  Cử chỉ lấy từ camera')
            self.conf_hand.setEnabled(False)
        send.setObjectName('send')
        send.clicked.connect(self.send)
        controls.addWidget(send)
        hint = QtWidgets.QLabel('Lệnh có hiệu lực 3 giây. Gửi lại để tiếp tục.\nWave → lại đây  •  Thumb Up → tiến\nOpen Palm → dừng và giữ STOP')
        hint.setWordWrap(True)
        if self.external_camera:
            hint.setText('Thumb Up → tiến  •  Wave → lại đây\nXòe tay đứng yên 0.4 giây → STOP\nHạ tay rồi RESET STOP để mở chốt.')
        controls.addWidget(hint)
        stop = QtWidgets.QPushButton('■  DỪNG KHẨN  /  STOP')
        stop.setObjectName('stop')
        stop.clicked.connect(lambda: self.publish('Stop', 'Open Palm'))
        controls.addWidget(stop)
        reset = QtWidgets.QPushButton('RESET STOP  •  Sau đó gửi lệnh mới')
        reset.clicked.connect(self.reset)
        controls.addWidget(reset)
        self.action = QtWidgets.QLabel('Đang chờ ROS 2…')
        self.action.setObjectName('action')
        controls.addWidget(self.action)
        self.details = QtWidgets.QLabel('')
        self.details.setWordWrap(True)
        controls.addWidget(self.details)
        controls.addStretch()
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(128)
        root.addWidget(self.log)
        self.footer = QtWidgets.QLabel('Mô phỏng động học 2D  •  Cử chỉ mô phỏng  •  Microphone: voice_node tùy chọn')
        if self.external_camera:
            self.footer.setText(self.backend + '  •  Webcam MediaPipe  •  Mất camera: dừng và giữ STOP')
        elif self.backend != 'Mô phỏng động học 2D':
            self.footer.setText(self.backend + '  •  Cử chỉ mô phỏng  •  Microphone tùy chọn')
        root.addWidget(self.footer)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(20)
        self.capture_timer = QtCore.QTimer(self)
        self.capture_timer.timeout.connect(self.capture)
        if self.demo:
            send.setEnabled(False)
            self.arena.setEnabled(False)
            self.footer.setText('DEMO TỰ ĐỘNG 48 GIÂY  •  Lệnh và cử chỉ được mô phỏng để kiểm tra fusion')
            QtCore.QTimer.singleShot(1800, self.start_demo)

    def send_target(self, x, y):
        self.target_pub.publish(Point(x=x, y=y))

    def on_pose(self, msg):
        self.arena.pose = (msg.x, msg.y, msg.theta)
        p = (msg.x, msg.y)
        if not self.arena.trail or math.dist(self.arena.trail[-1], p) > .03:
            self.arena.trail.append(p)
            self.arena.trail = self.arena.trail[-2000:]
        self.arena.update()

    def on_state(self, msg):
        self.state = json.loads(msg.data)
        self.arena.state = self.state
        self.action.setText(self.state['behavior'].upper())
        self.details.setText(f"Lý do: {self.state['reason']}\n"
                             f"STOP latch: {'ĐANG GIỮ' if self.state['latched'] else 'sẵn sàng'}\n"
                             f"v = {self.state['linear']:.2f} m/s    ω = {self.state['angular']:.2f} rad/s\n"
                             f"Lời: {self.state['voice'] or '—'}\nCử chỉ: {self.state['gesture'] or '—'}"
                             + (f"\nCamera: {self.state.get('camera', 'waiting')}" if self.external_camera else ''))
        key = (self.state['action'], self.state['reason'], self.state['behavior'])
        if key != self.last_log:
            self.log.append(f"{time.strftime('%H:%M:%S')}   {key[0].upper()}   /   {key[1]}   /   {key[2]}")
            self.last_log = key
            if self.record_dir and self.demo and self.state['behavior'] == 'arrived':
                self.grab().save(str(Path(self.record_dir).expanduser() / 'arrived.png'))
        if self.evidence:
            self.evidence.write(json.dumps(dict(t=round(time.monotonic()-self.demo_started, 3),
                                                pose=self.arena.pose, **self.state)) + '\n')

    def publish(self, voice='', gesture='None', cv=.95, cg=.95):
        self.voice.setCurrentText(voice)
        self.gesture.setCurrentText(gesture)
        self.conf_voice.setValue(cv)
        self.conf_hand.setValue(cg)
        payload = dict(voice=dict(text=voice, confidence=cv) if voice else None,
                       gesture=dict(text=gesture, confidence=cg) if gesture != 'None' else None)
        self.input_pub.publish(String(data=json.dumps(payload)))

    def send(self):
        if self.external_camera:
            self.voice_pub.publish(String(data=json.dumps(dict(
                text=self.voice.currentText(), confidence=self.conf_voice.value()))))
            return
        self.publish(self.voice.currentText(), self.gesture.currentText(),
                     self.conf_voice.value(), self.conf_hand.value())

    def reset(self):
        if not self.reset_client.service_is_ready():
            self.log.append('Reset service chưa sẵn sàng.')
            return
        future = self.reset_client.call_async(Trigger.Request())
        future.add_done_callback(lambda f: self.log.append(f.result().message))

    def start_demo(self):
        if not self.state:
            self.log.append('Chưa có dữ liệu ROS; chờ simulator…')
            QtCore.QTimer.singleShot(500, self.start_demo)
            return
        self.demo_started = time.monotonic()
        self.reset()
        self.events = [
            (1, 'Trùng khớp: tiến', 'Move forward', 'Thumb Up', .95, .95),
            (4, 'Open Palm thắng lệnh tiến', 'Move forward', 'Open Palm', .95, .2),
            (6, 'Lệnh tiến không tự mở STOP', 'Move forward', 'Thumb Up', .95, .95),
            (7, 'reset'),
            (8, 'Trùng khớp: lại đây', 'Come here', 'Wave', .95, .95),
            (10, 'Tiếp tục lại đây', 'Come here', 'Wave', .95, .95),
            (12, 'Tiếp tục lại đây', 'Come here', 'Wave', .95, .95),
            (14, 'Đến gần người gọi', 'Come here', 'Wave', .95, .95),
            (18, 'Chỉ có lời nói', 'Move forward', 'None', .95, 0.),
            (24, 'Chỉ có cử chỉ', '', 'Thumb Up', 0., .95),
            (27, 'Độ tin cậy thấp: đứng yên', 'Move forward', 'Thumb Up', .2, .2),
            (30, 'Xung đột: dừng', 'Move forward', 'Wave', .95, .95),
            (33, 'reset'),
            (34, 'Tiến sau reset', 'Move forward', 'Thumb Up', .95, .95),
            (36, 'Stop bằng lời thắng cử chỉ', 'Stop', 'Thumb Up', .3, .95),
            (39, 'reset'),
            (40, 'Không hiểu lệnh: đứng yên', 'dance', 'None', .95, 0.),
            (43, 'Tiến', 'Move forward', 'Thumb Up', .95, .95),
            (46, 'Kết thúc bằng STOP', '', 'Open Palm', 0., 1.),
        ]
        if self.record_dir:
            output = Path(self.record_dir).expanduser().resolve()
            output.mkdir(parents=True, exist_ok=True)
            self.evidence = (output / 'states.jsonl').open('w')
            try:
                self.video = subprocess.Popen([
                    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1120x780',
                    '-framerate', '10', '-i', '-', '-an', '-c:v', 'libx264',
                    '-threads', '2', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                    str(output / 'demo_48s.mp4')], stdin=subprocess.PIPE)
                self.capture_timer.start(100)
            except OSError as exc:
                self.log.append(f'Không ghi được video: {exc}')

    def poll(self):
        if not rclpy.ok():
            self.close()
            return
        for _ in range(8):
            rclpy.spin_once(self.node, timeout_sec=0)
        if self.demo_started and self.demo_index < len(self.events):
            elapsed = time.monotonic() - self.demo_started
            event = self.events[self.demo_index]
            if elapsed >= event[0]:
                self.demo_index += 1
                if event[1] == 'reset':
                    self.reset()
                else:
                    self.log.append(f'DEMO {event[0]:02d}s  •  {event[1]}')
                    self.publish(*event[2:])
        if self.demo_started and time.monotonic() - self.demo_started >= 48 and self.demo:
            self.demo = False
            self.send_button.setEnabled(True)
            self.arena.setEnabled(True)
            self.footer.setText('DEMO HOÀN TẤT  •  48 giây  •  Robot đang giữ STOP')
            self.finish_recording()

    def capture(self):
        if self.video is None:
            return
        frame = self.grab().toImage().convertToFormat(QtGui.QImage.Format_RGB888)
        # 1120 * 3 is divisible by four: no per-line Qt padding.
        data = frame.bits()
        data.setsize(frame.byteCount())
        try:
            self.video.stdin.write(bytes(data))
            self.frames += 1
        except (BrokenPipeError, OSError):
            self.log.append('ffmpeg đã dừng; kiểm tra ffmpeg trong terminal.')
            self.capture_timer.stop()

    def finish_recording(self):
        self.capture_timer.stop()
        if self.video:
            self.video.stdin.close()
            try:
                self.video.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.video.terminate()
                self.video.wait(timeout=3)
            self.video = None
        if self.evidence:
            self.evidence.close()
            self.evidence = None
        if self.record_dir:
            self.grab().save(str(Path(self.record_dir).expanduser() / 'dashboard.png'))

    def closeEvent(self, event):
        if rclpy.ok():
            self.publish('Stop', 'Open Palm')
            rclpy.spin_once(self.node, timeout_sec=0)
        self.finish_recording()
        event.accept()


def main(args=None):
    rclpy.init(args=args)
    app = QtWidgets.QApplication([])
    node = Node('hri_dashboard')
    window = Dashboard(node)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    window.show()
    try:
        app.exec_()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        window.close()
        window.finish_recording()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
