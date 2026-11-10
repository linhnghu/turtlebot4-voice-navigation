#!/usr/bin/env python3
"""Render the actual ROS dashboard offscreen, including live localized pose."""
from pathlib import Path
from PyQt5 import QtCore, QtWidgets
import rclpy
from rclpy.node import Node
from turtlebot4_voice_nav.dashboard import Dashboard

rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true', '-p',
                 'regions_file:=' + str(Path('artifacts/voice_nav/regions.yaml').resolve())])
node = Node('capture_semantic_dashboard')
app = QtWidgets.QApplication([])
window = Dashboard(node)
window.show()


def save():
    window.grab().save('artifacts/voice_nav/dashboard.png')
    print(window.xy.text(), flush=True)
    window.close()


QtCore.QTimer.singleShot(7000, save)
app.exec_()
node.destroy_node()
rclpy.shutdown()
