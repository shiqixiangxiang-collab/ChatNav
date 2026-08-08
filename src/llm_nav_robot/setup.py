import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'llm_nav_robot'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yax',
    maintainer_email='shiqixiangxiang@gmail.com',
    description='自然语言指挥雷达小车：LLM 意图解析 + Nav2 导航',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'llm_commander = llm_nav_robot.llm_commander:main',
            'llm_gui = llm_nav_robot.llm_gui:main',
        ],
    },
)
