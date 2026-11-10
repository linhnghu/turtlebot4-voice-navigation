from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    gui = Node(package='hri_multimodal', executable='dashboard', output='screen',
               condition=IfCondition(LaunchConfiguration('gui')),
               parameters=[{'demo': LaunchConfiguration('demo'),
                            'record_dir': LaunchConfiguration('record_dir')}])
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('demo', default_value='false'),
        DeclareLaunchArgument('record_dir', default_value=''),
        DeclareLaunchArgument('input_ttl', default_value='3.0'),
        Node(package='hri_multimodal', executable='fusion_node', output='screen',
             parameters=[{'input_ttl': LaunchConfiguration('input_ttl')}]),
        Node(package='hri_multimodal', executable='simulator', output='screen'),
        gui,
        RegisterEventHandler(OnProcessExit(target_action=gui,
                             on_exit=[EmitEvent(event=Shutdown(reason='Dashboard closed'))])),
    ])
