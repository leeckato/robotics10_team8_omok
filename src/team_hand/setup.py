from glob import glob

from setuptools import setup

package_name = 'team_hand'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/models', glob('team_hand/models/*')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='team_hand',
    maintainer_email='team@example.com',
    description='오목 로봇 손 감지 노드',
    license='MIT',
    entry_points={
        'console_scripts': [
            'hand_node = team_hand.hand_node:main',
        ],
    },
)
