from glob import glob

from setuptools import setup

package_name = 'team_algorithm'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/alphazero', glob('alphazero/*')),   # AlphaZero_Gomoku (MIT) 필요한 파일만
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='team_algorithm',
    maintainer_email='team@example.com',
    description='오목 AI 노드 (AlphaZero_Gomoku)',
    license='MIT',
    entry_points={'console_scripts': ['algorithm_node = team_algorithm.algorithm_node:main']},
)
