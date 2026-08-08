#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API 配置：从环境变量或桌面 API合集.md 读取 DeepSeek Key
真相来源：~/桌面/API合集.md（与 OpenClaw 约定一致）
"""

import os
import re


def get_deepseek_api_key() -> str:
    """优先环境变量 DEEPSEEK_API_KEY，其次解析桌面 API合集.md"""
    key = os.environ.get('DEEPSEEK_API_KEY')
    if key:
        return key.strip()

    path = os.path.expanduser('~/桌面/API合集.md')
    if not os.path.exists(path):
        raise RuntimeError('未找到 API 配置文件，请检查 ~/桌面/API合集.md')

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    m = re.search(r'deepseek\s*[:：]\s*(sk-[A-Za-z0-9_\-]+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    raise RuntimeError('API合集.md 中未找到 DeepSeek Key（格式应为 deepseek: sk-xxx）')


if __name__ == '__main__':
    print('DeepSeek Key 读取成功:', get_deepseek_api_key()[:6] + '***')
