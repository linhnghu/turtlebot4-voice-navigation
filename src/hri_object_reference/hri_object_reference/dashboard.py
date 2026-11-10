"""Interactive image scene, mouse pointing ray, text commands and demo recording."""
import json
import math
from pathlib import Path
import signal
import time

import cv2
from PyQt5 import QtCore, QtGui, QtWidgets
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import CompressedImage

from .perception import detect_objects, make_table

COLOR_HEX = {'red': '#e14141', 'blue': '#2d7ddc', 'yellow': '#e6b12e'}


class Table(QtWidgets.QWidget):
    pointed = QtCore.pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(590, 590)
        self.setMouseTracking(True)
        self.seed = 0
        self.ray = None
        self.ray_at = -math.inf
        self.dragging = False
        self.anchor = None
        self.state = {}
        self.live = False
        self.camera_scene = False
        self.regenerate()

    def regenerate(self):
        self.image = make_table(self.seed)
        self.objects = detect_objects(self.image)
        rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        self.background = QtGui.QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0],
                                       QtGui.QImage.Format_RGB888).copy()
        self.ray, self.state = None, {}
        self.update()

    def image_rect(self):
        size = min(self.width(), self.height())
        return QtCore.QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

    def coord(self, x, y):
        box = self.image_rect()
        return QtCore.QPointF(box.left() + x * box.width(), box.top() + y * box.height())

    def normalized(self, position):
        box = self.image_rect()
        x, y = (position.x() - box.left()) / box.width(), (position.y() - box.top()) / box.height()
        return min(1., max(0., x)), min(1., max(0., y))

    def set_ray(self, ray, emit=True):
        self.ray, self.ray_at = ray, time.monotonic()
        if emit:
            self.pointed.emit(ray)
        self.update()

    def mousePressEvent(self, event):
        if not self.live and event.button() == QtCore.Qt.LeftButton and self.image_rect().contains(event.pos()):
            self.anchor, self.dragging = self.normalized(event.pos()), True

    def mouseMoveEvent(self, event):
        if self.dragging:
            end = self.normalized(event.pos())
            self.ray = dict(origin=list(self.anchor), direction=[end[0] - self.anchor[0], end[1] - self.anchor[1]])
            self.ray_at = time.monotonic()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            end = self.normalized(event.pos())
            direction = [end[0] - self.anchor[0], end[1] - self.anchor[1]]
            if math.hypot(*direction) >= .04:
                self.set_ray(dict(origin=list(self.anchor), direction=direction))
            else:
                self.ray = None
                self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.drawImage(self.image_rect(), self.background)
        painter.setPen(QtGui.QColor('#574672'))
        painter.setFont(QtGui.QFont('DejaVu Sans', 12, QtGui.QFont.Bold))
        painter.drawText(self.coord(.05, .065), 'WEBCAM / VẬT THẬT' if self.camera_scene else 'MẶT BÀN / VẬT ẢO')
        candidates = self.state.get('candidates', []) if self.state.get('state') == 'CLARIFY' else []
        for obj in self.objects:
            center = self.coord(obj['x'], obj['y'])
            painter.setPen(QtGui.QColor('#263343'))
            painter.setFont(QtGui.QFont('DejaVu Sans', 10, QtGui.QFont.Bold))
            painter.drawText(center + QtCore.QPointF(-29, 65), obj['color'].upper())
            painter.setBrush(QtGui.QColor('#263343'))
            painter.drawEllipse(center, 3., 3.)
            radius = (obj['radius'] + .016) * self.image_rect().width()
            if obj['id'] == self.state.get('target') or obj['id'] in candidates:
                selected = obj['id'] == self.state.get('target')
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor('#12966b' if selected else '#9658c5'), 4))
                painter.drawRoundedRect(QtCore.QRectF(center.x() - radius, center.y() - radius,
                                                      radius * 2, radius * 2), 9, 9)
        if self.ray:
            origin, direction = self.ray['origin'], self.ray['direction']
            length = math.hypot(*direction)
            if length > 1e-6:
                dx, dy = direction[0] / length, direction[1] / length
                start = self.coord(*origin)
                painter.save()
                painter.setClipRect(self.image_rect())
                angle = math.radians(self.state.get('cone_degrees', 12.))
                sides = [(dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a))
                         for a in (-angle, angle)]
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(125, 72, 170, 23))
                painter.drawPolygon(QtGui.QPolygonF([start] + [self.coord(origin[0] + x * 3, origin[1] + y * 3)
                                                             for x, y in sides]))
                pen = QtGui.QPen(QtGui.QColor('#7d48aa'), 3)
                if time.monotonic() - self.ray_at > self.state.get('cue_ttl', 3.):
                    pen.setStyle(QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(start, self.coord(origin[0] + dx * 3, origin[1] + dy * 3))
                arrow = self.coord(origin[0] + dx * .23, origin[1] + dy * .23)
                painter.drawLine(arrow, arrow + QtCore.QPointF((-dx - dy) * 11, (-dy + dx) * 11))
                painter.drawLine(arrow, arrow + QtCore.QPointF((-dx + dy) * 11, (-dy - dx) * 11))
                painter.setBrush(QtGui.QColor('#ffcf91'))
                painter.drawEllipse(start, 9., 9.)
                painter.restore()
        painter.setFont(QtGui.QFont('DejaVu Sans', 10))
        painter.setPen(QtGui.QColor('#6c6580'))
        painter.drawText(self.coord(.055, .955), 'Duỗi ngón trỏ, gập các ngón còn lại, giữ hướng rồi nói.' if self.live
                         else 'Kéo chuột: điểm đầu → hướng vật. Nét đứt: tia đã hết hạn.')


class Dashboard(QtWidgets.QWidget):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.live = bool(node.declare_parameter('live', False).value)
        self.scene_source = str(node.declare_parameter('scene_source', 'simulation').value)
        self.camera_scene = self.live and self.scene_source == 'camera'
        self.setWindowTitle('Bài 03 · Lời nói + Chỉ tay · ROS 2')
        self.setFixedSize(1140, 850)
        self.setStyleSheet('''
            QWidget { background: #f6f4f9; color: #263343; font: 14px "DejaVu Sans"; }
            QLabel#title { font-size: 27px; font-weight: bold; }
            QLabel#state { font-size: 24px; font-weight: bold; color: #7d48aa; }
            QLabel#message { background: #ede5f5; padding: 13px; border-radius: 8px; }
            QComboBox { background: white; padding: 10px; border: 1px solid #d5cce0; }
            QPushButton { background: #e8e0f0; border: none; padding: 10px; border-radius: 6px; }
            QPushButton:hover { background: #d8c7e9; }
            QPushButton:disabled { color: #a49bad; background: #eeebf1; }
            QPushButton#send { background: #7d48aa; color: white; font-weight: bold; }
            QTextEdit { background: white; border: 1px solid #ddd5e5; font-size: 12px; }
        ''')
        self.scene_pub = node.create_publisher(String, '/reference/scene', 1)
        self.point_pub = node.create_publisher(String, '/reference/pointing', 1)
        self.request_pub = node.create_publisher(String, '/reference/request', 10)
        self.confirm_pub = node.create_publisher(String, '/reference/confirm', 10)
        node.create_subscription(String, '/reference/state', self.on_state, 10)
        node.create_subscription(String, '/reference/events', self.on_event, 20)
        node.create_subscription(String, '/reference/transcript', self.on_transcript, 10)
        node.create_subscription(String, '/reference/camera_status', self.on_camera_status, 1)
        node.create_subscription(String, '/reference/mic_status', self.on_mic_status, 1)
        node.create_subscription(CompressedImage, '/reference/image/compressed', self.on_image, 1)
        self.state = {}
        self.last_scene = 0.
        self.demo = bool(node.declare_parameter('demo', False).value)
        self.auto_close = bool(node.declare_parameter('auto_close', False).value)
        directory = str(node.declare_parameter('record_dir', '').value)
        self.output = None
        self.writer = self.log_file = None
        if directory:
            self.output = Path(directory).expanduser() / f'{time.strftime("%Y%m%d_%H%M%S")}_{time.time_ns() % 1000000:06d}'
            self.output.mkdir(parents=True, exist_ok=False)
            self.log_file = (self.output / 'dashboard.jsonl').open('w', buffering=1)
        self.demo_start = None
        self.demo_index = 0
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 19, 24, 16)
        title = QtWidgets.QLabel('“Pick up this object” · Lời nói + Chỉ tay')
        title.setObjectName('title')
        root.addWidget(title)
        root.addWidget(QtWidgets.QLabel('BÀI 03 / 07    •    Nhận màu từ ảnh, kết hợp tia chỉ và hỏi lại khi chưa rõ'))
        body = QtWidgets.QHBoxLayout()
        root.addLayout(body, 1)
        self.table = Table()
        self.table.live = self.live
        self.table.camera_scene = self.camera_scene
        if self.camera_scene:
            self.table.objects = []
            self.table.background.fill(QtGui.QColor('#292c34'))
        self.table.pointed.connect(self.point)
        body.addWidget(self.table, 3)
        controls = QtWidgets.QVBoxLayout()
        controls.setSpacing(12)
        body.addLayout(controls, 2)
        controls.addWidget(QtWidgets.QLabel('GIỌNG NÓI / MICROPHONE' if self.live else 'LỜI NÓI / TEXT'))
        self.text = QtWidgets.QComboBox()
        self.text.setEditable(True)
        self.text.addItems(['Pick up this object', 'Pick up the red object', 'Pick up the blue object',
                            'Pick up the yellow object', 'Gắp vật này', 'Chọn vật màu đỏ'])
        self.text.lineEdit().returnPressed.connect(self.send)
        controls.addWidget(self.text)
        send = QtWidgets.QPushButton('GỬI LỜI NÓI + TIA ĐANG CHỈ')
        send.setObjectName('send')
        send.clicked.connect(self.send)
        send.setEnabled(not self.live)
        self.text.setEnabled(not self.live)
        send.setVisible(not self.live)
        self.text.setVisible(not self.live)
        controls.addWidget(send)
        self.status_label = QtWidgets.QLabel('WAITING')
        self.status_label.setObjectName('state')
        controls.addWidget(self.status_label)
        self.message = QtWidgets.QLabel('Kéo từ phía dưới bàn lên vật rồi gửi câu nói.')
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(100)
        self.message.setObjectName('message')
        controls.addWidget(self.message)
        self.ray_label = QtWidgets.QLabel('Chưa có tia chỉ.')
        controls.addWidget(self.ray_label)
        self.transcription = QtWidgets.QLabel('MIC: đang chờ…' if self.live else '')
        self.transcription.setWordWrap(True)
        self.mic_label = QtWidgets.QLabel('')
        self.camera_label = QtWidgets.QLabel('')
        self.camera_label.setWordWrap(True)
        controls.addWidget(self.transcription)
        controls.addWidget(self.mic_label)
        controls.addWidget(self.camera_label)
        self.camera_thumbnail = QtWidgets.QLabel()
        self.camera_thumbnail.setAlignment(QtCore.Qt.AlignCenter)
        self.camera_thumbnail.setFixedHeight(140)
        self.camera_thumbnail.setVisible(self.live and not self.camera_scene)
        controls.addWidget(self.camera_thumbnail)
        controls.addWidget(QtWidgets.QLabel('HỎI LẠI: NÓI “MÀU ĐỎ / XANH DƯƠNG / VÀNG”' if self.live
                                           else 'XÁC NHẬN KHI ROBOT HỎI LẠI'))
        choices = QtWidgets.QHBoxLayout()
        self.confirm_buttons = {}
        for color in ('red', 'blue', 'yellow'):
            button = QtWidgets.QPushButton(color.upper())
            button.clicked.connect(lambda checked=False, c=color: self.confirm(c))
            button.setEnabled(False)
            choices.addWidget(button)
            self.confirm_buttons[color] = button
        controls.addLayout(choices)
        if not self.live:
            controls.addWidget(QtWidgets.QLabel('3 TÌNH HUỐNG KIỂM THỬ'))
        for label, case in [('1 · Chỉ đúng BLUE', 'correct'), ('2 · Chỉ giữa hai vật', 'ambiguous'),
                            ('3 · Nói RED nhưng chỉ BLUE', 'conflict')]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda checked=False, c=case: self.scenario(c))
            button.setEnabled(not self.live)
            button.setVisible(not self.live)
            controls.addWidget(button)
        regenerate = QtWidgets.QPushButton('ĐỔI VỊ TRÍ CÁC VẬT')
        regenerate.clicked.connect(self.regenerate)
        regenerate.setEnabled(not self.live)
        regenerate.setVisible(not self.live)
        controls.addWidget(regenerate)
        controls.addStretch()
        self.log_widget = QtWidgets.QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setFixedHeight(108)
        root.addWidget(self.log_widget)
        self.footer = QtWidgets.QLabel('Ảnh mô phỏng 2D • Chuột thay chỉ tay • Text thay STT • Kết quả là lựa chọn vật')
        root.addWidget(self.footer)
        if self.demo:
            self.footer.setText('DEMO TỰ ĐỘNG • Chỉ đúng → mơ hồ → mâu thuẫn → xác nhận BLUE')
        if self.live:
            self.footer.setText(('VẬT THẬT' if self.camera_scene else 'VẬT ẢO') +
                ' • CAMERA + MIC TIẾNG VIỆT • Giữ ngón trỏ rồi nói “Lấy vật này” • Hỏi lại: nói tên màu')
            self.message.setText('Đặt 3 vật đỏ, xanh dương, vàng trên bàn, trong tầm nhìn camera.' if self.camera_scene
                else 'Ba vật ảo đã sẵn sàng. Nhìn ảnh webcam nhỏ, điều chỉnh tia ngón trỏ trên bàn rồi nói “Lấy vật này”.')
        if self.output:
            cv2.imwrite(str(self.output / 'tabletop.png'), self.table.image)
            (self.output / 'detected_objects.json').write_text(json.dumps(self.table.objects, indent=2) + '\n')
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(20)
        self.record_timer = QtCore.QTimer(self)
        self.record_timer.timeout.connect(self.capture)
        if self.output:
            self.record_timer.start(100)

    def record(self, kind, **data):
        if self.log_file:
            self.log_file.write(json.dumps(dict(kind=kind, wall_time=time.time(), **data), ensure_ascii=False) + '\n')

    def publish_scene(self):
        if self.camera_scene:
            return
        # Re-run extraction on pixels, not the rendering coordinates.
        self.table.objects = detect_objects(self.table.image)
        self.scene_pub.publish(String(data=json.dumps(dict(objects=self.table.objects))))
        self.last_scene = time.monotonic()

    def regenerate(self):
        self.table.seed += 1
        self.table.regenerate()
        self.publish_scene()
        self.record('scene', objects=self.table.objects)

    def point(self, ray):
        self.point_pub.publish(String(data=json.dumps(ray)))
        self.record('pointing', ray=ray)

    def send(self):
        ray = self.table.ray if time.monotonic() - self.table.ray_at <= self.state.get('cue_ttl', 3.) else None
        data = dict(text=self.text.currentText(), ray=ray)
        self.request_pub.publish(String(data=json.dumps(data, ensure_ascii=False)))
        self.record('request', **data)

    def confirm(self, color):
        obj = next((o for o in self.state.get('objects', []) if o['color'] == color
                    and o['id'] in self.state.get('candidates', [])), None)
        if self.state.get('state') == 'CLARIFY' and obj:
            data = dict(request_id=self.state['request_id'], object_id=obj['id'])
            self.confirm_pub.publish(String(data=json.dumps(data)))
            self.record('confirmation', **data)

    def scenario(self, case):
        by_color = {o['color']: o for o in self.table.objects}
        if len(by_color) < 3:
            return
        blue, red = by_color['blue'], by_color['red']
        origin = [.5, .90]
        endpoint = [blue['x'], blue['y']]
        text = 'Pick up this object'
        if case == 'ambiguous':
            # Average unit bearings gives the angular bisector even after shuffling.
            ordered = sorted(self.table.objects, key=lambda o: math.atan2(o['y'] - origin[1], o['x'] - origin[0]))
            # Use neighboring bearings so a third object cannot lie between the pair.
            pairs = list(zip(ordered, ordered[1:]))
            pair = min(pairs, key=lambda p: abs(math.atan2(p[0]['y'] - origin[1], p[0]['x'] - origin[0])
                                              - math.atan2(p[1]['y'] - origin[1], p[1]['x'] - origin[0])))
            vectors = [(o['x'] - origin[0], o['y'] - origin[1]) for o in pair]
            direction = [sum(v[i] / math.hypot(*v) for v in vectors) for i in range(2)]
        else:
            direction = [endpoint[i] - origin[i] for i in range(2)]
        if case == 'conflict':
            text = 'Pick up the red object'
        self.table.set_ray(dict(origin=origin, direction=direction), emit=False)
        self.text.setCurrentText(text)
        self.send()

    def on_state(self, message):
        try:
            state = json.loads(message.data)
        except ValueError:
            return
        self.state, self.table.state = state, state
        self.status_label.setText(state['state'])
        self.message.setText(state['message'])
        for color, button in self.confirm_buttons.items():
            button.setEnabled(state['state'] == 'CLARIFY' and any(o['color'] == color
                and o['id'] in state['candidates'] for o in state['objects']))
        self.table.update()

    def on_image(self, message):
        image = QtGui.QImage.fromData(bytes(message.data), 'JPG')
        if not image.isNull():
            if self.camera_scene:
                self.table.background = image
                self.table.update()
            elif self.live:
                self.camera_thumbnail.setPixmap(QtGui.QPixmap.fromImage(image).scaled(140, 140, QtCore.Qt.KeepAspectRatio))

    def on_camera_status(self, message):
        if not self.live:
            return
        data = json.loads(message.data)
        if self.camera_scene:
            self.table.objects = data.get('objects', [])
        scene_label = (f"vật thật: {len(data.get('objects', []))}" if self.camera_scene
                       else f"vật ảo: {len(self.table.objects)}")
        self.camera_label.setText(f"CAM: {'OK' if data['healthy'] else 'LỖI'} • {scene_label}"
                                 f" • {'đang chỉ' if data.get('pointing') else 'chờ ngón trỏ'}")
        if data.get('ray') and data.get('pointing'):
            self.table.set_ray(data['ray'], emit=False)
        if not data.get('healthy'):
            self.table.ray = None

    def on_transcript(self, message):
        data = json.loads(message.data)
        self.transcription.setText(f"{'Đang nghe' if data.get('partial') else 'Đã nghe'}: {data.get('text', '')}")
        self.record('transcript', **data)

    def on_mic_status(self, message):
        data = json.loads(message.data)
        level = ('mức thu quá lớn' if data.get('clip_fraction', 0) > .03 else
                 'âm thanh nhỏ' if data.get('rms', 0) < 100 else 'đang nghe')
        self.mic_label.setText(f"MIC: {'OK' if data['healthy'] else 'LỖI'} • {level}")

    def on_event(self, message):
        try:
            data = json.loads(message.data)
        except ValueError:
            return
        self.log_widget.append(f"{time.strftime('%H:%M:%S')}  [{data['state']}] {data['message']}")
        self.record('decision', **data)

    def poll(self):
        if not rclpy.ok():
            self.close()
            return
        for _ in range(4):
            rclpy.spin_once(self.node, timeout_sec=0)
        now = time.monotonic()
        if now - self.last_scene >= .2:
            self.publish_scene()
        remaining = max(0., self.state.get('cue_ttl', 3.) - (now - self.table.ray_at))
        self.ray_label.setText(f'Tia chỉ còn hiệu lực: {remaining:.1f}s' if remaining else 'Kéo chuột để tạo tia chỉ mới.')
        self.table.update()
        if self.demo:
            if self.demo_start is None and self.request_pub.get_subscription_count() and self.state.get('objects'):
                self.demo_start = now
            if self.demo_start is not None:
                self.advance_demo(now - self.demo_start)

    def advance_demo(self, elapsed):
        steps = [(1., 'correct'), (4., '01_selected'), (5., 'ambiguous'), (8., '02_ambiguous'),
                 (9., 'conflict'), (12., '03_conflict'), (13., 'confirm'), (16., '04_confirmed')]
        if self.demo_index < len(steps) and elapsed >= steps[self.demo_index][0]:
            action = steps[self.demo_index][1]
            self.demo_index += 1
            if action in ('correct', 'ambiguous', 'conflict'):
                self.scenario(action)
            elif action == 'confirm':
                self.confirm('blue')
            elif self.output:
                self.grab().save(str(self.output / f'{action}.png'))
        if self.auto_close and elapsed >= 18.:
            self.close()

    def capture(self):
        if not self.output or not self.isVisible():
            return
        image = self.grab().toImage().convertToFormat(QtGui.QImage.Format_RGBA8888)
        pointer = image.bits()
        pointer.setsize(image.byteCount())
        import numpy as np
        rgba = np.frombuffer(pointer, dtype=np.uint8).reshape(image.height(), image.width(), 4)
        bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        if self.writer is None:
            self.writer = cv2.VideoWriter(str(self.output / 'demo.avi'), cv2.VideoWriter_fourcc(*'MJPG'),
                                          10., (image.width(), image.height()))
            if not self.writer.isOpened():
                raise RuntimeError('Cannot create demo.avi')
        self.writer.write(bgr)

    def closeEvent(self, event):
        self.poll_timer.stop()
        self.record_timer.stop()
        if self.writer:
            self.writer.release()
            self.writer = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        event.accept()


def main(args=None):
    rclpy.init(args=args)
    node = Node('reference_dashboard')
    app = QtWidgets.QApplication([])
    window = None
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    try:
        window = Dashboard(node)
        window.show()
        app.exec_()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if window:
            window.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
