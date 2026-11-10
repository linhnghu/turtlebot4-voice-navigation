"""Reuse the official Humble simulator and navigation packages."""
from pathlib import Path
import tempfile

import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            OpaqueFunction, SetEnvironmentVariable, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def include(package, filename, **arguments):
    path = Path(get_package_share_directory(package)) / 'launch' / filename
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(path)), launch_arguments=arguments.items())


def setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    mode = value('mode')
    actions = []
    # Validate map before starting Gazebo, so mistakes do not leave a simulator running.
    if mode in ('localization', 'navigation'):
        map_path = Path(value('map')).expanduser().resolve()
        if not map_path.is_file():
            raise RuntimeError(f'Map does not exist: {map_path}. Save your SLAM map first.')

    # Include world and spawn directly to consistently pass model to both upstream launches.
    if value('gazebo_gui') == 'true':
        actions.append(include('turtlebot4_ignition_bringup', 'ignition.launch.py',
                               world=value('world'), model=value('model'), use_sim_time='true'))
    else:
        # Same installed worlds/models as the official launch, without a GUI.
        resource_paths = [
            str(Path(get_package_share_directory('turtlebot4_ignition_bringup')) / 'worlds'),
            str(Path(get_package_share_directory('irobot_create_ignition_bringup')) / 'worlds'),
            str(Path(get_package_share_directory('turtlebot4_description')).parent),
            str(Path(get_package_share_directory('irobot_create_description')).parent)]
        actions.extend([
            SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', ':'.join(resource_paths)),
            include('ros_gz_sim', 'gz_sim.launch.py',
                    gz_args='-s -r --headless-rendering ' + value('world') + '.sdf -v 3'),
            Node(package='ros_gz_bridge', executable='parameter_bridge', name='clock_bridge',
                 arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock'], output='screen')])
    actions.append(include('turtlebot4_ignition_bringup', 'turtlebot4_spawn.launch.py',
                           model=value('model'), rviz='false', use_sim_time='true',
                           slam='false', nav2='false', localization='false',
                           **{axis: value(axis) for axis in ('x', 'y', 'z', 'yaw')}))
    if mode == 'mapping':
        actions.append(TimerAction(period=8.0, actions=[
            include('turtlebot4_navigation', 'slam.launch.py',
                    use_sim_time='true', sync='true')]))
    if mode in ('localization', 'navigation'):
        # Keep the official TurtleBot 4 parameters and add a known simulation
        # initial pose. AMCL otherwise waits indefinitely for /initialpose.
        source = Path(get_package_share_directory('turtlebot4_navigation')) / 'config/localization.yaml'
        params = yaml.safe_load(source.read_text())
        amcl = params['amcl']['ros__parameters']
        amcl['set_initial_pose'] = value('auto_initial_pose') == 'true'
        amcl['initial_pose'] = {'x': float(value('initial_x')),
                                'y': float(value('initial_y')), 'z': 0.0,
                                'yaw': float(value('initial_yaw'))}
        with tempfile.NamedTemporaryFile(mode='w', prefix='tb4_localization_',
                                         suffix='.yaml', delete=False) as file:
            yaml.safe_dump(params, file)
            localization_params = file.name
        actions.append(TimerAction(period=float(value('localization_delay')), actions=[
            include('turtlebot4_navigation', 'localization.launch.py',
                    use_sim_time='true', map=str(map_path), params=localization_params)]))
    if mode == 'navigation':
        actions.append(TimerAction(period=float(value('navigation_delay')), actions=[
            include('turtlebot4_navigation', 'nav2.launch.py', use_sim_time='true')]))
    if value('rviz') == 'true':
        config = Path(get_package_share_directory('turtlebot4_lab')) / 'config' / 'lab.rviz'
        actions.append(Node(package='rviz2', executable='rviz2', output='screen',
                            arguments=['-d', str(config), '-f',
                                       'odom' if mode == 'simulation' else 'map'],
                            parameters=[{'use_sim_time': True}]))
    return actions


def generate_launch_description():
    arguments = [
        DeclareLaunchArgument('mode', default_value='mapping',
                              choices=['simulation', 'mapping', 'localization', 'navigation']),
        DeclareLaunchArgument('world', default_value='maze',
                              choices=['depot', 'maze', 'warehouse']),
        DeclareLaunchArgument('model', default_value='lite', choices=['standard', 'lite']),
        DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('gazebo_gui', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('map', default_value=str(Path.home() / 'ros2_ws/maps/map.yaml')),
        DeclareLaunchArgument('auto_initial_pose', default_value='true',
                              choices=['true', 'false'],
                              description='Initialize AMCL at a known pose on the simulation map'),
        DeclareLaunchArgument('initial_x', default_value='0.0', description='Initial x in map (m)'),
        DeclareLaunchArgument('initial_y', default_value='0.0', description='Initial y in map (m)'),
        DeclareLaunchArgument('initial_yaw', default_value='0.0', description='Initial yaw in map (rad)'),
        DeclareLaunchArgument('localization_delay', default_value='8.0'),
        DeclareLaunchArgument('navigation_delay', default_value='12.0'),
    ]
    arguments += [DeclareLaunchArgument(axis, default_value='0.0')
                  for axis in ('x', 'y', 'z', 'yaw')]
    return LaunchDescription(arguments + [OpaqueFunction(function=setup)])
