"""One launch: existing TurtleBot4 simulation + semantic map + Nav2 + speech."""
import os
from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    from turtlebot4_voice_nav.segmentation import segment
    package = Path(get_package_share_directory('turtlebot4_voice_nav'))
    output = Path(value('output_dir')).expanduser().resolve()
    segment(value('map'), value('seeds'), output, float(value('clearance')))
    common = {'use_sim_time': value('use_sim_time') == 'true',
              'regions_file': str(output / 'regions.yaml')}
    actions = []
    if value('simulation') == 'true':
        lab = Path(get_package_share_directory('turtlebot4_lab'))
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(lab / 'launch/lab.launch.py')),
            launch_arguments=dict(mode='navigation', world='maze', model='lite', rviz='false',
                                  gazebo_gui=value('gazebo_gui'), map=value('map'),
                                  localization_delay='25.0', navigation_delay='35.0').items()))
    actions.append(Node(package='turtlebot4_voice_nav', executable='navigator', output='screen',
                        parameters=[common, {'map_file': value('map'),
                                             'journal': str(output / 'events.jsonl'),
                                             'goal_timeout': float(value('goal_timeout'))}]))
    if value('rviz') == 'true':
        actions.append(Node(package='rviz2', executable='rviz2', output='screen',
                            arguments=['-d', str(package / 'config/semantic.rviz')],
                            parameters=[{'use_sim_time': common['use_sim_time']}]))
    if value('dashboard') == 'true':
        actions.append(Node(package='turtlebot4_voice_nav', executable='dashboard',
                            output='screen', parameters=[common],
                            additional_env={'QT_QPA_PLATFORM_PLUGIN_PATH': '/usr/lib/x86_64-linux-gnu/qt5/plugins'}))
    if value('voice') == 'true':
        python = Path(value('speech_python')).expanduser()
        model_present = (Path(value('whisper_path'), 'model.bin').is_file() if value('backend') == 'whisper'
                         else Path(value('model_path'), 'am').is_dir())
        if not python.is_file() or not model_present:
            raise RuntimeError('Run ./setup_voice_nav.bash or select voice:=false')
        speech = Path(get_package_prefix('turtlebot4_voice_nav')) / 'lib/turtlebot4_voice_nav/speech'
        actions.append(ExecuteProcess(cmd=[str(python), str(speech), '--ros-args',
                            '-p', 'model_path:=' + value('model_path'),
                            '-p', 'backend:=' + value('backend'),
                            '-p', 'whisper_path:=' + value('whisper_path'),
                            '-p', 'regions_file:=' + str(output / 'regions.yaml'),
                            '-p', 'energy_threshold:=' + value('energy_threshold'),
                            '-p', 'device:=' + value('device')], output='screen'))
    return actions


def generate_launch_description():
    ws = Path(os.environ.get('TURTLEBOT4_WORKSPACE', str(Path.home() / 'ros2_ws')))
    package = Path(get_package_share_directory('turtlebot4_voice_nav'))
    defaults = dict(map=str(ws / 'maps/map.yaml'), seeds=str(package / 'config/seeds.yaml'),
                    output_dir=str(ws / 'artifacts/voice_nav'), clearance='0.30', goal_timeout='240.0',
                    speech_python=str(ws / '.venv-voice-nav/bin/python'),
                    model_path=str(ws / '.models/hri/vosk-model-small-vn-0.4'), device='-1')
    defaults.update(backend='whisper', whisper_path=str(ws / '.models/faster-whisper-small'),
                    energy_threshold='300.0')
    booleans = dict(simulation='true', gazebo_gui='true', rviz='true', dashboard='true',
                    voice='true', use_sim_time='true')
    return LaunchDescription([
        *[DeclareLaunchArgument(k, default_value=v) for k, v in defaults.items()],
        *[DeclareLaunchArgument(k, default_value=v, choices=['true', 'false']) for k, v in booleans.items()],
        OpaqueFunction(function=setup),
    ])
