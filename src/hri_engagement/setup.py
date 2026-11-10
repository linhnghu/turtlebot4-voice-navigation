from glob import glob
from setuptools import find_packages, setup

setup(
    name='hri_engagement', version='0.1.0', packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/hri_engagement']),
        ('share/hri_engagement', ['package.xml', 'README.md', 'VALIDATION.md']),
        ('share/hri_engagement/launch', glob('launch/*.launch.py')),
        ('share/hri_engagement/config', glob('config/*.yaml')),
        ('share/hri_engagement/data', glob('data/*.csv')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Linh', maintainer_email='linh@example.com', license='Apache-2.0',
    description='Multimodal interaction intent recognition for ROS 2 Humble',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'engagement_node = hri_engagement.controller:main',
        'camera_node = hri_engagement.camera:main',
        'text_input = hri_engagement.text_input:main',
        'trial_recorder = hri_engagement.trials:main',
        'replay_trials = hri_engagement.replay:main',
    ]},
)
