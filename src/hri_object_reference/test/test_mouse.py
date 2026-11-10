import os
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5 import QtCore, QtTest, QtWidgets

from hri_object_reference.dashboard import Table


class MouseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_drag_emits_a_pointing_ray(self):
        table = Table()
        table.resize(640, 640)
        table.show()
        self.app.processEvents()
        rays = []
        table.pointed.connect(rays.append)
        QtTest.QTest.mousePress(table, QtCore.Qt.LeftButton, pos=QtCore.QPoint(320, 576))
        QtTest.QTest.mouseRelease(table, QtCore.Qt.LeftButton, pos=QtCore.QPoint(320, 224))
        self.assertEqual(len(rays), 1)
        self.assertAlmostEqual(rays[0]['origin'][0], .5)
        self.assertLess(rays[0]['direction'][1], 0.)
        self.assertAlmostEqual(rays[0]['direction'][0], 0.)
        table.close()

    def test_tiny_drag_does_not_create_ray(self):
        table = Table()
        table.resize(640, 640)
        rays = []
        table.pointed.connect(rays.append)
        QtTest.QTest.mousePress(table, QtCore.Qt.LeftButton, pos=QtCore.QPoint(320, 500))
        QtTest.QTest.mouseRelease(table, QtCore.Qt.LeftButton, pos=QtCore.QPoint(322, 501))
        self.assertFalse(rays)
        self.assertIsNone(table.ray)
        table.close()


if __name__ == '__main__':
    unittest.main()
