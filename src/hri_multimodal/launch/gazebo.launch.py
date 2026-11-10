"""Gazebo Fortress physics, ROS bridge, fusion, webcam and dashboard."""
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    share = Path(get_package_share_directory('hri_multimodal'))
    workspace = Path(value('workspace')).expanduser().resolve()
    output = Path(value('output_dir')).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    camera_on = value('camera') == 'true'
    server = ExecuteProcess(cmd=['ign', 'gazebo', '-s', '-r', '-v', '3',
                                 str(share/'worlds/hri_lab.sdf')], output='screen')
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge',
                  name='hri_gazebo_bridge', output='screen', arguments=[
                      '/hri/gazebo/cmd_vel@geometry_msgs/msg/Twist]ignition.msgs.Twist',
                      '/hri/gazebo/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry',
                      '/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock',
                      '/world/hri_lab/pose/info@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V'],
                  remappings=[('/world/hri_lab/pose/info', '/hri/gazebo/world_poses')])
    fusion = Node(package='hri_multimodal', executable='fusion_node', output='screen',
                  parameters=[{'camera_required': value('require_camera') == 'true',
                               'input_ttl': float(value('input_ttl')),
                               'max_speed': .35, 'enforce_bounds': True}])
    adapter = Node(package='hri_multimodal', executable='gazebo_adapter', output='screen')
    actions = [server, bridge, fusion, adapter]
    critical = [server, bridge, fusion, adapter]
    if value('gazebo_gui') == 'true':
        gui = ExecuteProcess(cmd=['ign','gazebo','-g','-v','2','--gui-config',
                                  str(share/'config/gazebo_gui.config')], output='screen')
        actions.append(gui)
        critical.append(gui)
    if value('dashboard') == 'true':
        dashboard = Node(package='hri_multimodal', executable='dashboard', output='screen',
                         parameters=[{'external_camera': camera_on, 'backend': 'Gazebo Fortress'}])
        actions.append(dashboard)
        critical.append(dashboard)
    if camera_on:
        python, model = Path(value('camera_python')), Path(value('model_path'))
        if not python.is_file() or not model.is_file():
            raise RuntimeError('Run bash src/hri_multimodal/scripts/setup_camera.bash first')
        camera = ExecuteProcess(cmd=[str(python), '-c',
            'from hri_multimodal.camera import main; main()', '--ros-args',
            '-p', 'camera_index:='+value('camera_index'),
            '-p', 'model_path:='+str(model), '-p', 'show_window:='+value('camera_window'),
            '-p', 'output_dir:='+str(output)],
            additional_env={'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '1'}, output='screen')
        actions.append(camera)
        critical.append(camera)
    if value('voice') == 'true':
        python = workspace/'.venv-hri/bin/python'
        model = workspace/'.models/hri/vosk-model-small-en-us-0.15'
        if not python.is_file() or not model.is_dir():
            raise RuntimeError('Run bash src/hri_multimodal/scripts/setup_voice.bash first')
        voice = ExecuteProcess(cmd=[str(python), '-c',
            'from hri_multimodal.voice import main; main()', '--ros-args',
            '-p', 'model_path:='+str(model)], additional_env={
                'LD_LIBRARY_PATH': str(workspace/'.hri-runtime/usr/lib/x86_64-linux-gnu')
                                   + ':' + os.environ.get('LD_LIBRARY_PATH', '')}, output='screen')
        actions.append(voice)
        critical.append(voice)
    for process in critical:
        actions.append(RegisterEventHandler(OnProcessExit(target_action=process,
            on_exit=[EmitEvent(event=Shutdown(reason='An HRI simulation process exited'))])))
    return actions


def generate_launch_description():
    workspace = Path(os.environ.get('HRI_WORKSPACE', str(Path.home()/'ros2_ws')))
    return LaunchDescription([
        DeclareLaunchArgument('workspace', default_value=str(workspace)),
        DeclareLaunchArgument('camera', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('require_camera', default_value=LaunchConfiguration('camera'), choices=['true','false']),
        DeclareLaunchArgument('gazebo_gui', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('dashboard', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('camera_window', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('voice', default_value='false', choices=['true','false']),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('input_ttl', default_value='3.0'),
        DeclareLaunchArgument('camera_python', default_value=str(workspace/'.venv-gesture/bin/python')),
        DeclareLaunchArgument('model_path', default_value=str(workspace/'.models/gesture_recognizer.task')),
        DeclareLaunchArgument('output_dir', default_value=str(workspace/'artifacts/hri_gazebo_runs'/
            datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S'))),
        OpaqueFunction(function=setup),
    ])
