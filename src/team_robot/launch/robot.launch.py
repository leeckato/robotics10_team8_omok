"""
ros2 launch team_robot robot.launch.py robot_mode:=dry|real [gripper_mode:=drl|topic|sim|none]
    [grid_json:=~/ros2_ws/board_control/grid_robot_coordinates.json] [params:=...]
두산 드라이버(bringup)는 로봇 담당이 검증한 명령으로 먼저 따로 실행합니다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    params = os.path.join(get_package_share_directory('team_robot'), 'config', 'robot_params.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('params', default_value=params),
        DeclareLaunchArgument('gripper_drl', default_value=os.path.join(get_package_share_directory('team_robot'), 'robot_assets', 'gripper_drl.py')),
        DeclareLaunchArgument('robot_mode', default_value='dry', description='dry: 로봇 안 움직임 / real: 실제 이동'),
        DeclareLaunchArgument('gripper_mode', default_value='drl'),
        DeclareLaunchArgument('grid_json', default_value=os.path.join(get_package_share_directory('team_robot'), 'robot_assets', 'grid_robot_coordinates.json')),
        Node(package='team_robot', executable='robot_node', name='team_robot', output='screen',
             parameters=[LaunchConfiguration('params'),
                         {'robot_mode': LaunchConfiguration('robot_mode'),
                          'gripper_mode': LaunchConfiguration('gripper_mode'),
                          'grid_json': LaunchConfiguration('grid_json'),
                          'gripper_drl': LaunchConfiguration('gripper_drl'),
                          'config_source': LaunchConfiguration('params')}]),
    ])
