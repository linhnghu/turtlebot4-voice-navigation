from glob import glob
from setuptools import find_packages, setup

setup(
    name='hri_object_reference', version='0.1.0', packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/hri_object_reference']),
        ('share/hri_object_reference', ['package.xml', 'README.md', 'VALIDATION.md']),
        ('share/hri_object_reference/launch', glob('launch/*.launch.py')),
        ('share/hri_object_reference/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Linh', maintainer_email='linh@example.com', license='Apache-2.0',
    description='Speech and pointing fusion for object reference resolution',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'reference_node = hri_object_reference.controller:main',
        'dashboard = hri_object_reference.dashboard:main',
        'camera_node = hri_object_reference.camera:main',
        'voice_node = hri_object_reference.voice:main',
    ]},
)
