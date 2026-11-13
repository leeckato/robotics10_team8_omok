from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    sim=LaunchConfiguration('simulation');gui=LaunchConfiguration('gui');mock=LaunchConfiguration('mock_peers');hand=LaunchConfiguration('use_hand');cal=LaunchConfiguration('calibration')
    params={'simulation':ParameterValue(sim,value_type=bool)}
    return LaunchDescription([
        DeclareLaunchArgument('simulation',default_value='true'),
        DeclareLaunchArgument('gui',default_value='true'),
        DeclareLaunchArgument('mock_peers',default_value='false'),
        DeclareLaunchArgument('use_hand',default_value='false'),
        DeclareLaunchArgument('calibration',default_value=str(Path.home()/'.config/gomoku/marker_calibration.json')),
        Node(package='gomoku_system',executable='vision_node',parameters=[params,{'calibration':cal}],output='screen'),
        Node(package='gomoku_system',executable='game_controller',parameters=[params,{'use_hand':ParameterValue(hand,value_type=bool)}],output='screen'),
        Node(package='gomoku_system',executable='gui_node',parameters=[params],condition=IfCondition(gui),output='screen'),
        Node(package='gomoku_system',executable='mock_peers',parameters=[params],condition=IfCondition(mock),output='screen')])
