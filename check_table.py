#!/usr/bin/env python3
"""检查数据库表结构"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, config_util

url = config_util.get_config('common.url')
mysql_tool = mysql_util.get_mysql_tool(url)

# 检查analysis_area2026表结构
print("检查 analysis_area2026 表结构...")
try:
    result = mysql_tool.query_data('DESCRIBE analysis_area2026')
    print('analysis_area2026表结构:')
    for row in result:
        print(f"  {row}")
except Exception as e:
    print(f"查询失败: {e}")

# 检查analysis_area2025表结构（参考）
print("\n检查 analysis_area2025 表结构...")
try:
    result = mysql_tool.query_data('DESCRIBE analysis_area2025')
    print('analysis_area2025表结构:')
    for row in result:
        print(f"  {row}")
except Exception as e:
    print(f"查询失败: {e}")
