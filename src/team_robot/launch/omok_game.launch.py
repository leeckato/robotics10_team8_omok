"""
오목 전체 실행: 비전 + 게임 제어 + GUI (gomoku_system) + 손 감지 (team_hand) + AI (team_algorithm) + 로봇 (team_robot)

  # 두산 드라이버(bringup)와 그리퍼 노드는 먼저 따로 실행 (로봇 담당이 검증한 명령)
  ros2 launch team_robot omok_game.launch.py                       # 로봇 안 움직임 (dry)
  ros2 launch team_robot omok_game.launch.py robot_mode:=real      # 실제 로봇

인자
  robot_mode   dry | real          (기본 dry)
  gripper_mode drl | topic | sim | none  (기본 drl = omok_pick_place.py --gripper real 과 같은 gripper_drl.py)
  use_hand     true | false        (기본 true. false 면 GUI [판 검사 요청 · 3초 대기] 로 사용자 착수 확인)
  grid_json    로봇 격자 좌표 (기본 ~/ros2_ws/board_control/grid_robot_coordinates.json)
  calibration  비전/손 공용 마커 보정 파일
  n_playout    AI 탐색 횟수 (기본 400)
"""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def include(pkg, name, args, condition=None):
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare(pkg), 'launch', name])),
        launch_arguments=args.items(), condition=condition)


def generate_launch_description():
    L = LaunchConfiguration
    cal = L('calibration')
    return LaunchDescription([
        DeclareLaunchArgument('robot_params', default_value=PathJoinSubstitution([FindPackageShare('team_robot'), 'config', 'robot_params.yaml'])),
        DeclareLaunchArgument('gripper_drl', default_value=PathJoinSubstitution([FindPackageShare('team_robot'), 'robot_assets', 'gripper_drl.py'])),
        DeclareLaunchArgument('robot_mode', default_value='dry'),
        DeclareLaunchArgument('gripper_mode', default_value='drl'),
        DeclareLaunchArgument('grid_json', default_value=PathJoinSubstitution([FindPackageShare('team_robot'), 'robot_assets', 'grid_robot_coordinates.json'])),
        DeclareLaunchArgument('use_hand', default_value='true'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('calibration', default_value=str(Path.home() / '.config/gomoku/marker_calibration.json')),
        DeclareLaunchArgument('n_playout', default_value='400'),

        # 실제 카메라와 실물 게임 노드
        include('gomoku_system', 'gomoku.launch.py', {
            'simulation': 'false', 'use_hand': L('use_hand'),
            'gui': L('gui'), 'calibration': cal}),
        include('team_hand', 'hand.launch.py', {'calibration': cal}, condition=IfCondition(L('use_hand'))),
        Node(package='team_algorithm', executable='algorithm_node', name='team_algorithm', output='screen',
             parameters=[PathJoinSubstitution([FindPackageShare('team_algorithm'), 'config', 'algorithm_params.yaml']),
                         {'n_playout': ParameterValue(L('n_playout'), value_type=int)}]),
        include('team_robot', 'robot.launch.py', {'robot_mode': L('robot_mode'), 'gripper_mode': L('gripper_mode'),
                                                  'grid_json': L('grid_json'), 'params': L('robot_params'),
                                                  'gripper_drl': L('gripper_drl')}),
    ])
