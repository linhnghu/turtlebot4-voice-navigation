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
    camera = Node(package='hri_object_reference', executable='camera_node', output='screen',
                  prefix=[LaunchConfiguration('camera_python')], parameters=[{
                      'camera_index': ParameterValue(LaunchConfiguration('camera_index'), value_type=int),
                      'scene_source': LaunchConfiguration('scene_source'),
                      'output_dir': LaunchConfiguration('log_dir'),
                  }])
    voice = Node(package='hri_object_reference', executable='voice_node', output='screen',
                 prefix=[LaunchConfiguration('voice_python')], parameters=[{
                     'model_path': LaunchConfiguration('voice_model'),
                     'device': ParameterValue(LaunchConfiguration('mic_index'), value_type=int),
                 }])
    gui = Node(package='hri_object_reference', executable='dashboard', output='screen',
               condition=IfCondition(LaunchConfiguration('gui')), parameters=[{
                   'live': True, 'scene_source': LaunchConfiguration('scene_source'),
                   'record_dir': LaunchConfiguration('record_dir'),
               }])
    actions = [
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('scene_source', default_value='simulation'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('mic_index', default_value='-1'),
        DeclareLaunchArgument('camera_python', default_value='/usr/bin/python3'),
        DeclareLaunchArgument('voice_python', default_value='/usr/bin/python3'),
        DeclareLaunchArgument('voice_model', default_value=''),
        DeclareLaunchArgument('record_dir', default_value=''),
        DeclareLaunchArgument('log_dir', default_value=''),
        DeclareLaunchArgument('config', default_value=config),
        Node(package='hri_object_reference', executable='reference_node', output='screen',
             parameters=[LaunchConfiguration('config'), {'camera_required': True, 'mic_required': True,
                                                         'log_dir': LaunchConfiguration('log_dir')}]),
        camera, voice, gui,
    ]
    for process, label in ((camera, 'Camera'), (voice, 'Microphone'), (gui, 'Dashboard')):
        actions.append(RegisterEventHandler(OnProcessExit(target_action=process,
            on_exit=[EmitEvent(event=Shutdown(reason=f'{label} stopped'))])))
    return LaunchDescription(actions)
