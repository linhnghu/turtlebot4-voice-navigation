#!/usr/bin/env python3
"""Integration test using synthetic ROS labels, NOT a webcam/AI demo.

Run only with ./run_gesture_demo.bash start_camera:=false and no teleop/Nav2.
Uses actual Gazebo odometry, lidar and hazards through robot_behavior_node.
"""
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


def main():
    rclpy.init()
    node = rclpy.create_node('gesture_controller_integration_test')
    pub = node.create_publisher(String, '/detected_gesture', 1)
    data = {'status': '', 'pose': None, 'v': 0.0, 'w': 0.0, 'motion': 0}
    def status(m):
        if m.data != data['status']:
            print(m.data, flush=True)
        data['status'] = m.data
    def velocity(m):
        data.update(v=m.linear.x,w=m.angular.z)
        if abs(m.linear.x)+abs(m.angular.z)>0.001:
            data['motion'] += 1
    def odom(m):
        p,q=m.pose.pose.position,m.pose.pose.orientation
        data['pose']=[p.x,p.y,math.atan2(2*q.w*q.z,1-2*q.z*q.z)]
    node.create_subscription(String,'/gesture_behavior/status',status,1)
    node.create_subscription(Twist,'/cmd_vel',velocity,qos_profile_sensor_data)
    node.create_subscription(Odometry,'/odom',odom,qos_profile_sensor_data)
    def hold(label, duration, until_complete=False):
        deadline=time.monotonic()+duration
        next_pub=0
        while time.monotonic()<deadline:
            now=time.monotonic()
            if label and now>=next_pub:
                pub.publish(String(data=label));next_pub=now+.05
            rclpy.spin_once(node,timeout_sec=.02)
            if until_complete and data['status'].startswith('COMPLETE'):
                return
        if until_complete:
            raise AssertionError(f'Behavior did not complete: {data}')
    report={'input':'synthetic ROS gesture labels; real Gazebo sensor feedback',
            'confirmation':'one Thumb_Up, then No_Hand frames until completion','checks':[]}
    try:
        ready_deadline=time.monotonic()+40
        while time.monotonic()<ready_deadline:
            hold('Closed_Fist',.5)
            if data['pose'] is not None and data['status']=='WAITING: cancelled':
                break
        assert data['pose'] is not None, 'Gazebo odometry missing'
        for gesture in ('Wave','Pointing_Up','Victory'):
            before=data['motion']
            hold(gesture,.7)
            assert data['status'].startswith('SELECTED'), data
            assert data['motion']==before, 'Motion before confirmation'
            start=data['pose'][:]
            hold('Thumb_Up',.7)
            hold('No_Hand',65,until_complete=True)
            assert data['motion']>before, 'No velocity commands'
            report['checks'].append({'gesture':gesture,'completed':True,
                                     'start':start,'end':data['pose'][:]})
            hold('Closed_Fist',.4)
        for stop_gesture in ('Open_Palm','Closed_Fist',None):
            hold('Victory',.6);hold('Thumb_Up',.7);hold('No_Hand',1.2)
            assert data['status'].startswith('RUNNING'), data
            assert data['motion']>0
            hold(stop_gesture,1.2)
            assert abs(data['v'])+abs(data['w'])==0, data
            report['checks'].append({'stop':stop_gesture or 'signal_timeout','stopped':True})
            hold('Closed_Fist',.4)
        report['passed']=True
    finally:
        hold('Closed_Fist',.3)
        workspace=Path(__file__).resolve().parents[3]
        pointer=workspace/'artifacts/latest_gesture_run.txt'
        output=Path(pointer.read_text().strip())/'controller_integration.json'
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(f'Report: {output}',flush=True)
        node.destroy_node();rclpy.shutdown()


if __name__=='__main__':
    main()
