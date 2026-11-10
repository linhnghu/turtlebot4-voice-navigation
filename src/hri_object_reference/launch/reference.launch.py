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
    config = str(Path(get_package_share_directory('hri_object_reference')) / 'config/reference.yaml')
    gui = Node(package='hri_object_reference', executable='dashboard', output='screen',
               condition=IfCondition(LaunchConfiguration('gui')),
               parameters=[{
                   'demo': ParameterValue(LaunchConfiguration('demo'), value_type=bool),
                   'auto_close': ParameterValue(LaunchConfiguration('auto_close'), value_type=bool),
                   'record_dir': LaunchConfiguration('record_dir'),
               }])
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('demo', default_value='false'),
        DeclareLaunchArgument('auto_close', default_value='false'),
        DeclareLaunchArgument('record_dir', default_value=''),
        DeclareLaunchArgument('log_dir', default_value=''),
        DeclareLaunchArgument('camera_required', default_value='false'),
        DeclareLaunchArgument('mic_required', default_value='false'),
        DeclareLaunchArgument('config', default_value=config),
        Node(package='hri_object_reference', executable='reference_node', output='screen',
             parameters=[LaunchConfiguration('config'), {'log_dir': LaunchConfiguration('log_dir'),
                 'camera_required': ParameterValue(LaunchConfiguration('camera_required'), value_type=bool),
                 'mic_required': ParameterValue(LaunchConfiguration('mic_required'), value_type=bool)}]),
        gui,
        RegisterEventHandler(OnProcessExit(target_action=gui,
                             on_exit=[EmitEvent(event=Shutdown(reason='Object reference dashboard closed'))])),
    ])
