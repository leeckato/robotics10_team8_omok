from setuptools import setup,find_packages
from glob import glob
setup(name='gomoku_system',version='0.1.0',packages=find_packages(),
 data_files=[('share/ament_index/resource_index/packages',['resource/gomoku_system']),
 ('share/gomoku_system',['package.xml']),('share/gomoku_system/launch',glob('launch/*.py')),
 ('share/gomoku_system/tools',glob('tools/*'))],
 install_requires=['setuptools'],zip_safe=True,maintainer='Gomoku Team',maintainer_email='team@example.com',description='Gomoku vision system',license='MIT',
 entry_points={'console_scripts':[
 'vision_node=gomoku_system.vision_node:main','game_controller=gomoku_system.controller:main',
 'gui_node=gomoku_system.gui:main','mock_peers=gomoku_system.mock_peers:main',
 'calibrate=gomoku_system.calibrate:main']})
