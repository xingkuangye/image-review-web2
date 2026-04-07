# -*- coding: utf-8 -*-
"""
修复代码审查问题
1. 删除辅助脚本
2. 修复SQL参数
3. 修复fetch错误处理
"""

import os

# 删除辅助脚本
scripts_to_delete = [
    'fix_params.py',
    'fix_fetch.py',
]

for script in scripts_to_delete:
    if os.path.exists(script):
        os.remove(script)
        print(f"Deleted: {script}")

print("Cleanup done!")
