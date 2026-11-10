"""Existing map + AMCL/Nav2 + physical scene objects + RGB YOLO + sequential goals."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    package = Path(get_package_share_directory('turtlebot4_vision_nav'))
    lab = Path(get_package_share_directory('turtlebot4_lab'))
    python = Path(value('yolo_python')).expanduser()
    weights = Path(value('weights')).expanduser()
    if not python.is_file() or not weights.is_file():
        raise RuntimeError('YOLO environment/weights missing. Run ./setup_vision.bash first.')
    output = Path(value('output_dir')).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    workspace = Path(os.environ.get('TURTLEBOT4_WORKSPACE', str(Path.home() / 'ros2_ws')))
    (workspace / 'artifacts/latest_vision_run.txt').write_text(str(output) + '\n')
    arguments = dict(mode='navigation', world='maze', model='lite', rviz='false',
                     map=value('map'), auto_initial_pose='true',
                     localization_delay='30.0', navigation_delay='45.0')
    actions = [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(lab / 'launch/lab.launch.py')),
        launch_arguments=arguments.items())]
    if value('scene_objects') == 'true':
        # Static models off the intended route; Nav2 still sees them through LiDAR.
        template = (package / 'models/person_standing/model.sdf').read_text()
        template = template.replace('<model name="person_standing">',
                                    '<model name="person_standing"><static>true</static>')
        template = template.replace('model://person_standing/',
                                    'file://' + str(package / 'models/person_standing') + '/')
        model_file = output / 'person_standing.sdf'
        model_file.write_text(template)
        placements = [('person_west', -5.5, -0.7, 0.0),
                      ('person_north', -4.7, 5.7, -1.57),
                      ('person_east', 2.0, 2.7, -1.57)]
        for name, x, y, yaw in placements:
            actions.append(TimerAction(period=14.0, actions=[Node(
                package='ros_gz_sim', executable='create', name='spawn_' + name,
                arguments=['-world', 'maze', '-file', str(model_file), '-name', name,
                           '-x', str(x), '-y', str(y), '-z', '0.0', '-Y', str(yaw)],
                output='screen')]))
    detector = Path(get_package_share_directory('turtlebot4_vision_nav')).parents[1] / 'lib/turtlebot4_vision_nav/yolo_detector.py'
    # Execute with the isolated Python while retaining system ROS packages.
    actions.append(TimerAction(period=18.0, actions=[ExecuteProcess(
        cmd=[str(python), str(detector), '--ros-args', '-p', 'use_sim_time:=true',
             '-p', f'weights:={weights}', '-p', f'output_dir:={output}',
             '-p', 'show_window:=' + value('show_window')],
        output='screen', additional_env={'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '1'})]))
    if value('rviz') == 'true':
        actions.append(Node(package='rviz2', executable='rviz2',
                            arguments=['-d', str(package / 'config/vision.rviz')],
                            parameters=[{'use_sim_time': True}], output='screen'))
    if value('autostart_mission') == 'true':
        actions.append(TimerAction(period=50.0, actions=[Node(
            package='turtlebot4_vision_nav', executable='mission.py', output='screen',
            parameters=[{'use_sim_time': True, 'goals_file': value('goals_file'),
                         'output_dir': str(output), 'goal_timeout': 240.0}])]))
    return actions


def generate_launch_description():
    workspace = Path(os.environ.get('TURTLEBOT4_WORKSPACE', str(Path.home() / 'ros2_ws')))
    package = Path(get_package_share_directory('turtlebot4_vision_nav'))
    return LaunchDescription([
        DeclareLaunchArgument('map', default_value=str(workspace / 'maps/map.yaml')),
        DeclareLaunchArgument('goals_file', default_value=str(package / 'config/goals.yaml')),
        DeclareLaunchArgument('yolo_python', default_value=str(workspace / '.venv-yolo/bin/python')),
        DeclareLaunchArgument('weights', default_value=str(workspace / '.models/yolo11n.pt')),
        DeclareLaunchArgument('output_dir', default_value=str(workspace / 'artifacts/vision_runs' /
            datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S'))),
        *[DeclareLaunchArgument(name, default_value='true', choices=['true', 'false'])
          for name in ('rviz', 'show_window', 'scene_objects', 'autostart_mission')],
        OpaqueFunction(function=setup),
    ])
