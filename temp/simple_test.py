#!/usr/bin/env python3
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

print("开始测试...")

import pandas as pd
from sqlalchemy import create_engine, text

print("导入成功")

engine = create_engine("mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8")
print("引擎创建成功")

# 测试查询
with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_zq_sssj_20260709 WHERE time BETWEEN '093000' AND '093100'"))
    count = result.fetchone()[0]
    print(f"前1分钟数据量: {count}")

print("测试完成")
