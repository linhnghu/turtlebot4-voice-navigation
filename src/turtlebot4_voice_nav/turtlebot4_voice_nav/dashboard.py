"""Qt view of semantic map, localized robot, transcripts and Nav2 status."""
import json
import math
from pathlib import Path
import sys

from PyQt5 import QtCore, QtGui, QtWidgets
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException

from .navigator import latched
from .segmentation import load_regions


class Dashboard(QtWidgets.QWidget):
    def __init__(self, node):
        super().__init__()
        self.node = node
        path = Path(node.declare_parameter('regions_file', '').value)
        self.config, self.grid, _ = load_regions(path)
        self.map_pixmap = QtGui.QPixmap(str(path.parent / self.config['overlay']))
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, node)
        self.pub = node.create_publisher(String, '/voice_nav/command', 10)
        self.setWindowTitle('Bài 7 · Phân vùng bản đồ và điều hướng giọng nói')
        self.resize(1120, 780)
        self.setStyleSheet('QWidget {background:#142130;color:#edf2f7;font-size:16px;} '
                           'QLineEdit,QComboBox {background:#24364b;padding:10px;} '
                           'QPushButton {background:#2864a0;padding:12px;border-radius:5px;}')
        root = QtWidgets.QHBoxLayout(self)
        self.map_view = QtWidgets.QLabel()
        self.map_view.setMinimumSize(600, 600)
        self.map_view.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.map_view, 2)
        panel = QtWidgets.QVBoxLayout()
        root.addLayout(panel, 1)
        title = QtWidgets.QLabel('BÀI THỰC HÀNH 7\nĐiều hướng bằng giọng nói')
        title.setStyleSheet('font-size:23px;font-weight:bold;')
        panel.addWidget(title)
        for r in self.config['regions']:
            label = QtWidgets.QLabel(r['id'])
            label.setStyleSheet('padding:10px;border-left:6px solid rgb(%s);' % ','.join(map(str, r['color'])))
            panel.addWidget(label)
        self.status = QtWidgets.QLabel('Đang chờ Nav2...')
        self.status.setWordWrap(True)
        panel.addWidget(self.status)
        self.speech_status = QtWidgets.QLabel('Microphone: chưa kết nối / voice:=false')
        self.speech_status.setWordWrap(True)
        panel.addWidget(self.speech_status)
        self.heard = QtWidgets.QLabel('Câu nói: —')
        self.heard.setWordWrap(True)
        panel.addWidget(self.heard)
        self.input = QtWidgets.QComboBox()
        self.input.setEditable(True)
        self.input.addItems(['Đi đến khu vực A', 'Di chuyển từ khu vực A đến khu vực B',
                             'Đi đến khu vực B', 'Đi đến khu vực C', 'Đi đến khu vực Z'])
        panel.addWidget(self.input)
        send = QtWidgets.QPushButton('GỬI CÂU LỆNH VĂN BẢN')
        send.clicked.connect(lambda: self.pub.publish(String(data=self.input.currentText())))
        panel.addWidget(send)
        self.input.lineEdit().returnPressed.connect(send.click)
        stop = QtWidgets.QPushButton('DỪNG / HỦY HÀNH TRÌNH')
        stop.setStyleSheet('background:#b83240;font-weight:bold;padding:16px;')
        stop.clicked.connect(lambda: self.pub.publish(String(data='dừng lại')))
        panel.addWidget(stop)
        self.xy = QtWidgets.QLabel('Vị trí robot: chờ TF map → base_link')
        self.xy.setWordWrap(True)
        panel.addWidget(self.xy)
        panel.addStretch()
        node.create_subscription(String, '/voice_nav/status', self.on_status, latched())
        node.create_subscription(String, '/voice_nav/speech_status', self.on_speech_status, latched())
        node.create_subscription(String, '/voice_nav/transcript', self.on_transcript, 10)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(80)

    def on_status(self, msg):
        d = json.loads(msg.data)
        distance = d.get('distance_remaining')
        tail = f'\nCòn {distance:.2f} m' if distance is not None else ''
        self.status.setText(f"{d['state']}\n{d['message']}" + tail)

    def on_speech_status(self, msg):
        self.speech_status.setText('Microphone: ' + json.loads(msg.data)['message'])

    def on_transcript(self, msg):
        d = json.loads(msg.data)
        self.heard.setText(f"Nghe: {d['text']}\nĐộ tin cậy: {d['confidence']:.2f}")

    def tick(self):
        if not rclpy.ok():
            self.close()
            return
        rclpy.spin_once(self.node, timeout_sec=0)
        pix = self.map_pixmap.scaled(self.map_view.size(), QtCore.Qt.KeepAspectRatio,
                                     QtCore.Qt.FastTransformation)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        sx, sy = pix.width()/self.grid.width, pix.height()/self.grid.height
        painter.setFont(QtGui.QFont('DejaVu Sans', 14, QtGui.QFont.Bold))
        for r in self.config['regions']:
            u, v = self.grid.world_to_pixel(r['goal']['x'], r['goal']['y'])
            p = QtCore.QPointF((u+.5)*sx, (v+.5)*sy)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 2))
            painter.setBrush(QtGui.QColor('#142130'))
            painter.drawEllipse(p, 14, 14)
            painter.drawText(QtCore.QRectF(p.x()-12, p.y()-14, 24, 28), QtCore.Qt.AlignCenter, r['id'])
        try:
            t = self.tf.lookup_transform('map', 'base_link', rclpy.time.Time())
            age = (self.node.get_clock().now()-rclpy.time.Time.from_msg(t.header.stamp)).nanoseconds/1e9
            if not -.5 <= age <= 2:
                raise ValueError('TF quá hạn')
            x, y = t.transform.translation.x, t.transform.translation.y
            u, v = self.grid.world_to_pixel(x, y)
            p = QtCore.QPointF((u+.5)*sx, (v+.5)*sy)
            painter.setBrush(QtGui.QColor('#e53e3e'))
            painter.drawEllipse(p, 9, 9)
            self.xy.setText(f'Robot (AMCL): x={x:.2f}, y={y:.2f} m')
        except (TransformException, ValueError):
            self.xy.setText('Vị trí robot: chưa có TF định vị mới.')
        painter.end()
        self.map_view.setPixmap(pix)


def main(args=None):
    rclpy.init(args=args)
    node = Node('semantic_navigation_dashboard')
    app = QtWidgets.QApplication(sys.argv[:1])
    window = Dashboard(node)
    window.show()
    try:
        app.exec_()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
