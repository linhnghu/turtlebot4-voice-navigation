from glob import glob
from setuptools import find_packages, setup

setup(
    name='hri_multimodal', version='0.1.0', packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/hri_multimodal']),
        ('share/hri_multimodal', ['package.xml', 'README.md', 'VALIDATION.md']),
        ('share/hri_multimodal/launch', glob('launch/*.launch.py')),
        ('share/hri_multimodal/worlds', glob('worlds/*.sdf')),
        ('share/hri_multimodal/config', glob('config/*')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Linh', maintainer_email='linh@example.com', license='Apache-2.0',
    description='ROS 2 multimodal HRI practical', tests_require=['pytest'],
    entry_points={'console_scripts': [
        'fusion_node = hri_multimodal.controller:main',
        'simulator = hri_multimodal.simulator:main',
        'dashboard = hri_multimodal.dashboard:main',
        'voice_node = hri_multimodal.voice:main',
        'camera_node = hri_multimodal.camera:main',
        'gazebo_adapter = hri_multimodal.gazebo:main',
    ]},
)
