#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动 LLM 指挥官节点"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='llm_nav_robot',
            executable='llm_commander',
            name='llm_commander',
            output='screen',
            parameters=[{'use_sim_time': False}],
        ),
    ])
