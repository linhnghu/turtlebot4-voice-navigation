#!/usr/bin/env python3
"""Real Gazebo physics with injected gesture/health messages, isolated domain 72.

This checks the controller/bridge/physics path, not webcam classification.
Ground-truth model poses are compared against wheel odometry.
"""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from geometry_msgs.msg import Point, Pose2D
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_msgs.msg import TFMessage


def main():
    workspace = Path(__file__).resolve().parents[3]
    output = workspace/'artifacts/hri_multimodal/gazebo_validation'
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(ROS_DOMAIN_ID='72', ROS_LOCALHOST_ONLY='1', HRI_DOMAIN_ID='72')
    log = (output/'runtime.log').open('w')
    process = subprocess.Popen([str(workspace/'run_hri_gazebo.bash'), 'camera:=false',
        'require_camera:=true', 'gazebo_gui:=false', 'dashboard:=false', 'output_dir:='+str(output)],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    node = rclpy.create_node('hri_gazebo_probe')
    state, world, pose, checks = {}, {}, [None], []
    completed = False
    health = dict(healthy=True, motion_inhibit=False, label='No hand')
    enabled = [True]
    camera = node.create_publisher(String,'/hri/camera_status',1)
    inputs = node.create_publisher(String,'/hri/input',1)
    target = node.create_publisher(Point,'/hri/target',1)
    reset = node.create_client(Trigger,'/hri/reset_stop')
    node.create_subscription(String,'/hri/decision',lambda m: state.update(json.loads(m.data)),1)
    node.create_subscription(Pose2D,'/hri/pose',lambda m: pose.__setitem__(0,(m.x,m.y)),1)

    def on_world(msg):
        for t in msg.transforms:
            if t.child_frame_id in ('hri_robot','caller'):
                p=t.transform.translation
                world[t.child_frame_id]=(p.x,p.y)
    node.create_subscription(TFMessage,'/hri/gazebo/world_poses',on_world,1)
    node.create_timer(.05,lambda: camera.publish(String(data=json.dumps(health))) if enabled[0] else None)

    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)

    def wait(predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate(): return
            if process.poll() is not None:
                raise AssertionError('Gazebo launch exited; see runtime.log')
            rclpy.spin_once(node,timeout_sec=.02)
        raise AssertionError(f'Timeout state={state}, world={world}, pose={pose[0]}')

    def record(name,condition):
        entry=dict(name=name,passed=bool(condition),state=dict(state),world=dict(world),odom_pose=pose[0])
        checks.append(entry)
        print(f'{"PASS" if condition else "FAIL"} {name}',flush=True)
        assert condition,name

    def send(voice,gesture):
        inputs.publish(String(data=json.dumps(dict(
            voice=dict(text=voice,confidence=.95) if voice else None,
            gesture=dict(text=gesture,confidence=.95) if gesture else None))))
        pump(.2)

    def clear(expect=True):
        future=reset.call_async(Trigger.Request())
        wait(future.done)
        assert future.result().success == expect,future.result().message
        pump(.2)

    try:
        wait(lambda: 'hri_robot' in world and pose[0] and reset.service_is_ready()
             and state.get('behavior')=='idle',20)
        record('gazebo_spawn_matches_odometry',math.dist(world['hri_robot'],pose[0])<.03)
        before=world['hri_robot']
        send('Move forward','Thumb Up')
        pump(1.)
        record('agreement_moves_physical_model',world['hri_robot'][0]-before[0]>.2)
        record('odometry_matches_physics_after_motion',math.dist(world['hri_robot'],pose[0])<.08)
        health.update(motion_inhibit=True,label='Palm pending')
        pump(.35)
        before=world['hri_robot']
        pump(.4)
        record('palm_pending_inhibits_voice_motion',state['behavior']=='checking_gesture'
               and math.dist(before,world['hri_robot'])<.03)
        health.update(motion_inhibit=False,label='Open Palm')
        send('Move forward','Open Palm')
        pump(.3)
        before=world['hri_robot']
        pump(.3)
        record('open_palm_stops_physical_model',state['latched'] and math.dist(before,world['hri_robot'])<.03)
        clear(False)
        record('reset_rejected_while_palm_visible',state['latched'])
        health['label']='No hand'
        pump(.15)
        send('Move forward','Thumb Up')
        record('stop_remains_latched',state['latched'] and state['linear']==0.)
        clear()
        record('reset_clears_old_motion',state['action']=='idle')
        target.publish(Point(x=2.,y=4.))
        pump(.4)
        deadline=time.monotonic()+28
        send('Come here','Wave')
        while state.get('behavior')!='arrived' and time.monotonic()<deadline:
            send('Come here','Wave')
            pump(.6)
        record('come_here_arrives_in_gazebo',state['behavior']=='arrived'
               and math.dist(world['hri_robot'],(2.,4.))<.5)
        record('caller_marker_matches_target',math.dist(world['caller'],(2.,4.))<.01)
        send('Move forward','Wave')
        record('conflict_stops_in_gazebo',state['reason']=='conflict' and state['latched'])
        clear()
        send('Move forward','Thumb Up')
        enabled[0]=False
        pump(1.1)
        before=world['hri_robot']
        pump(.4)
        record('camera_timeout_stops_physical_model',state['reason']=='camera_lost'
               and math.dist(before,world['hri_robot'])<.03)
        clear(False)
        enabled[0]=True
        pump(.2)
        clear()
        record('camera_recovery_requires_reset_and_new_input',state['action']=='idle' and not state['latched'])
        completed=True
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGINT)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=3)
        (output/'runtime.json').write_text(json.dumps(dict(
            source='Gazebo Fortress physics; injected gesture labels and camera health',
            completed=completed,passed=completed and all(c['passed'] for c in checks),checks=checks),indent=2))
        log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__=='__main__':
    main()
