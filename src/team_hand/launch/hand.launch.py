"""
ros2 launch team_hand hand.launch.py
    [calibration:=~/.config/gomoku/marker_calibration.json]   비전 노드와 같은 보정 파일 (gomoku.launch.py 와 같은 기본값)
    [params:=/경로/hand_params.yaml] [debug_image:=true]
"""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default_params = os.path.join(get_package_share_directory('team_hand'), 'config', 'hand_params.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('params', default_value=default_params),
        DeclareLaunchArgument('calibration', default_value=str(Path.home() / '.config/gomoku/marker_calibration.json')),
        DeclareLaunchArgument('debug_image', default_value='false'),
        Node(
            package='team_hand',
            executable='hand_node',
            name='team_hand',
            output='screen',
            parameters=[LaunchConfiguration('params'),
                        {'calibration': LaunchConfiguration('calibration'),
                         'debug_image': ParameterValue(LaunchConfiguration('debug_image'), value_type=bool)}],
        ),
    ])
