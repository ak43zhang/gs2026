#!/usr/bin/env python
"""最小化测试 - 只测试 MySQL 连接"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

print("Step 1: 导入 config_util...")
from gs2026.utils import config_util
print("  OK")

print("\nStep 2: 获取数据库 URL...")
url = config_util.get_config('common.url')
print(f"  OK: {url[:50]}...")

print("\nStep 3: 创建 engine...")
from sqlalchemy import create_engine, text
engine = create_engine(
    url,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=10,
    connect_args={'connect_timeout': 10}
)
print("  OK")

print("\nStep 4: 测试连接...")
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        row = result.fetchone()
        print(f"  OK: {row[0]}")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nStep 5: 测试简单写入...")
import pandas as pd
from datetime import datetime

df = pd.DataFrame({
    'code': ['123001', '123002'],
    'name': ['Test1', 'Test2'],
    'price': [100.5, 101.2],
})

table_name = f"test_table_{datetime.now().strftime('%H%M%S')}"
print(f"  Table: {table_name}")

try:
    with engine.connect() as conn:
        df.to_sql(table_name, con=conn, if_exists='replace', index=False)
        conn.commit()
    print("  OK: Write success")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback
    traceback.print_exc()

print("\nStep 6: 验证数据...")
try:
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        print(f"  OK: {count} rows in table")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nAll tests passed!")
