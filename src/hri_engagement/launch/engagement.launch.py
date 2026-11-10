from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    config = str(Path(get_package_share_directory('hri_engagement')) / 'config/engagement.yaml')
    camera = Node(
        package='hri_engagement', executable='camera_node', output='screen',
        condition=IfCondition(LaunchConfiguration('camera')),
        prefix=[LaunchConfiguration('camera_python')],
        parameters=[{
            'camera_index': ParameterValue(LaunchConfiguration('camera_index'), value_type=int),
            'show_window': ParameterValue(LaunchConfiguration('show_window'), value_type=bool),
            'output_dir': LaunchConfiguration('output_dir'),
            'yaw_limit': ParameterValue(LaunchConfiguration('yaw_limit'), value_type=float),
            'pitch_limit': ParameterValue(LaunchConfiguration('pitch_limit'), value_type=float),
        }])
    return LaunchDescription([
        DeclareLaunchArgument('camera', default_value='true'),
        DeclareLaunchArgument('camera_python', default_value='/usr/bin/python3'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('show_window', default_value='true'),
        DeclareLaunchArgument('output_dir', default_value=''),
        DeclareLaunchArgument('yaw_limit', default_value='22.0'),
        DeclareLaunchArgument('pitch_limit', default_value='22.0'),
        DeclareLaunchArgument('config', default_value=config),
        Node(package='hri_engagement', executable='engagement_node', output='screen',
             parameters=[LaunchConfiguration('config')]),
        camera,
        RegisterEventHandler(OnProcessExit(target_action=camera,
                             on_exit=[EmitEvent(event=Shutdown(reason='Engagement camera stopped'))])),
    ])
