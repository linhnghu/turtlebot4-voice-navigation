from glob import glob
from setuptools import find_packages, setup

setup(
    name='turtlebot4_voice_nav', version='0.1.0', packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/turtlebot4_voice_nav']),
        ('share/turtlebot4_voice_nav', ['package.xml']),
        ('share/turtlebot4_voice_nav/launch', glob('launch/*.launch.py')),
        ('share/turtlebot4_voice_nav/config', glob('config/*')),
    ],
    install_requires=['setuptools'], tests_require=['pytest'], zip_safe=True,
    maintainer='Linh', maintainer_email='linh@example.com', license='Apache-2.0',
    description='Semantic map segmentation and Vietnamese voice navigation',
    entry_points={'console_scripts': [
        'segment_map = turtlebot4_voice_nav.segmentation:main',
        'navigator = turtlebot4_voice_nav.navigator:main',
        'speech = turtlebot4_voice_nav.speech:main',
        'dashboard = turtlebot4_voice_nav.dashboard:main',
    ]},
)
