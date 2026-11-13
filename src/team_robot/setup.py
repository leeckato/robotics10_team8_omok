from glob import glob

from setuptools import setup

package_name = 'team_robot'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='team_robot',
    maintainer_email='team@example.com',
    description='오목 로봇 노드 (두산 E0509)',
    license='MIT',
    entry_points={'console_scripts': ['robot_node = team_robot.robot_node:main']},
)
