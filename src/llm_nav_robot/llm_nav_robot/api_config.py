#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek API Key 配置

获取顺序：
1. 环境变量 DEEPSEEK_API_KEY（推荐）
2. 用户级配置文件 ~/.chatnav/api_key.txt
3. 与本文件同目录的 api_key.txt（源码运行模式）

未配置时抛出错误，配置方式详见项目 README「配置 API Key」章节。
"""

import os

# 用户级配置：~/.chatnav/api_key.txt（跨安装/源码模式均稳定）
_USER_KEY_FILE = os.path.expanduser('~/.chatnav/api_key.txt')
# 源码级配置：与 api_config.py 同目录
_LOCAL_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.txt')


def get_deepseek_api_key() -> str:
    """获取 DeepSeek API Key：环境变量 → ~/.chatnav/api_key.txt → 同目录 api_key.txt"""
    key = os.environ.get('DEEPSEEK_API_KEY')
    if key and key.strip():
        return key.strip()

    for path in (_USER_KEY_FILE, _LOCAL_KEY_FILE):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                key = f.read().strip()
            if key:
                return key

    raise RuntimeError(
        '未找到 DeepSeek API Key：请设置环境变量 DEEPSEEK_API_KEY，'
        f'或在 {_USER_KEY_FILE} 中写入 Key（详见 README「配置 API Key」章节）'
    )


if __name__ == '__main__':
    print('DeepSeek Key 读取成功:', get_deepseek_api_key()[:6] + '***')
