"""Open arena, undocked TurtleBot 4, webcam AI, and one velocity controller."""
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from ament_index_python.packages import get_package_share_directory, get_package_prefix
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler,
                            SetEnvironmentVariable)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def include(package, filename, **arguments):
    return IncludeLaunchDescription(PythonLaunchDescriptionSource(str(
        Path(get_package_share_directory(package)) / 'launch' / filename)),
        launch_arguments=arguments.items())


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    share = Path(get_package_share_directory('turtlebot4_gesture'))
    scripts = Path(get_package_prefix('turtlebot4_gesture')) / 'lib/turtlebot4_gesture'
    output = Path(value('output_dir')).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    workspace = Path(os.environ.get('TURTLEBOT4_WORKSPACE', str(Path.home() / 'ros2_ws')))
    (workspace / 'artifacts').mkdir(exist_ok=True)
    (workspace / 'artifacts/latest_gesture_run.txt').write_text(str(output)+'\n')
    python = Path(value('gesture_python')).expanduser()
    model = Path(value('model_path')).expanduser()
    if not python.is_file() or not model.is_file():
        raise RuntimeError('Run ./setup_gesture.bash before launching gestures.')
    # Run server and GUI as separate processes. Fortress' combined Ruby launcher
    # can deadlock in fork() when desktop graphics libraries already have threads.
    bringup = Path(get_package_share_directory('turtlebot4_ignition_bringup'))
    resource = ':'.join(str(Path(get_package_share_directory(p)).parent)
        for p in ('turtlebot4_description', 'irobot_create_description'))
    gui_plugins = ':'.join(str(Path(get_package_share_directory(p))/'lib')
        for p in ('turtlebot4_ignition_gui_plugins', 'irobot_create_ignition_plugins'))
    server = ExecuteProcess(cmd=['ign','gazebo','-s','-r','-v','3',
                                  str(share/'worlds/gesture_arena.sdf')], output='screen')
    actions = [SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', resource),
               SetEnvironmentVariable('IGN_GUI_PLUGIN_PATH', gui_plugins),
               SetEnvironmentVariable('IGN_GAZEBO_SYSTEM_PLUGIN_PATH', ':'.join(filter(None, [
                   os.environ.get('IGN_GAZEBO_SYSTEM_PLUGIN_PATH', ''),
                   os.environ.get('LD_LIBRARY_PATH', ''),
                   str(Path(get_package_prefix('ign_ros2_control'))/'lib')]))), server,
               Node(package='ros_gz_bridge', executable='parameter_bridge', name='gesture_clock',
                    arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock']),
               include('turtlebot4_description', 'robot_description.launch.py',
                       model='lite', use_sim_time='true', namespace=''),
               include('irobot_create_common_bringup', 'dock_description.launch.py', gazebo='ignition')]
    if value('gui') == 'true':
        actions.append(ExecuteProcess(cmd=['ign','gazebo','-g','-v','2','--gui-config',
            str(bringup/'gui/lite/gui.config')], output='screen'))
    actions.append(RegisterEventHandler(OnProcessExit(target_action=server,
        on_exit=[EmitEvent(event=Shutdown(reason='Gazebo server exited'))])))
    # Spawn separately so the robot starts free of its dock. The dock remains
    # far away, allowing upstream dock sensors/pose republisher to function.
    for name, topic, x, y in [('turtlebot4', 'robot_description', '0', '0'),
                               ('standard_dock', 'standard_dock_description', '8', '8')]:
        actions.append(Node(package='ros_gz_sim', executable='create',
            arguments=['-name', name, '-topic', topic, '-x', x, '-y', y, '-z', '0.02'],
            output='screen'))
    actions += [include('turtlebot4_ignition_bringup', 'ros_ign_bridge.launch.py',
                        model='lite', robot_name='turtlebot4', dock_name='standard_dock',
                        world='gesture_arena'),
                include('turtlebot4_ignition_bringup', 'turtlebot4_nodes.launch.py', model='lite'),
                include('irobot_create_common_bringup', 'create3_nodes.launch.py',
                        gazebo='ignition', namespace=''),
                include('irobot_create_ignition_bringup', 'create3_ignition_nodes.launch.py',
                        robot_name='turtlebot4', dock_name='standard_dock'),
                Node(package='tf2_ros', executable='static_transform_publisher',
                     name='gesture_lidar_tf', arguments=['0','0','0','0','0','0',
                         'rplidar_link','turtlebot4/rplidar_link/rplidar'])]
    behavior = Node(package='turtlebot4_gesture', executable='robot_behavior_node.py',
                    output='screen', parameters=[{'output_dir': str(output)}])
    webcam = ExecuteProcess(cmd=[str(python), str(scripts/'gesture_recognition_node.py'),
        '--ros-args', '-p', 'model_path:='+str(model), '-p', 'output_dir:='+str(output),
        '-p', 'camera_index:='+value('camera_index'), '-p', 'show_window:='+value('show_window')],
        additional_env={'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '1'}, output='screen')
    # A failed perception/controller process terminates this whole demo.
    for process in (webcam, behavior):
        actions.append(RegisterEventHandler(OnProcessExit(target_action=process,
            on_exit=[EmitEvent(event=Shutdown(reason='Gesture node exited'))])))
    actions.append(behavior)
    if value('start_camera') == 'true':
        actions.append(webcam)
    return actions


def generate_launch_description():
    workspace = Path(os.environ.get('TURTLEBOT4_WORKSPACE', str(Path.home()/'ros2_ws')))
    return LaunchDescription([
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('gui', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('show_window', default_value='true', choices=['true','false']),
        DeclareLaunchArgument('start_camera', default_value='true', choices=['true','false'],
                              description='Disable only for scripted controller integration tests'),
        DeclareLaunchArgument('gesture_python', default_value=str(workspace/'.venv-gesture/bin/python')),
        DeclareLaunchArgument('model_path', default_value=str(workspace/'.models/gesture_recognizer.task')),
        DeclareLaunchArgument('output_dir', default_value=str(workspace/'artifacts/gesture_runs'/
            datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S'))),
        OpaqueFunction(function=setup)])
