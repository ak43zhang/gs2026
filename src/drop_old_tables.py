#!/usr/bin/env python
"""删除旧的监控表以释放磁盘空间"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

# 要删除的表列表
tables_to_drop = [
    'monitor_gp_sssj_20260323',
    'monitor_gp_sssj_20260324',
    'monitor_gp_sssj_20260325',
    'monitor_gp_sssj_20260326',
    'monitor_gp_sssj_20260327',
    'monitor_gp_sssj_20260330',
    'monitor_gp_sssj_20260331',
    'monitor_gp_sssj_20260401',
    'monitor_gp_sssj_20260402',
    'monitor_gp_sssj_20260403',
    'monitor_gp_sssj_20260407',
    'monitor_gp_sssj_20260408',
    'monitor_gp_sssj_20260409',
    'monitor_gp_sssj_20260410',
]

url = config_util.get_config('common.url')
engine = create_engine(
    url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=10,
    connect_args={'connect_timeout': 10}
)

print(f"准备删除 {len(tables_to_drop)} 个表...\n")

dropped = 0
failed = 0

with engine.connect() as conn:
    for table_name in tables_to_drop:
        try:
            # 检查表是否存在
            result = conn.execute(text(f"SHOW TABLES LIKE '{table_name}'"))
            if result.fetchone():
                # 删除表
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                conn.commit()
                print(f"[OK] 已删除: {table_name}")
                dropped += 1
            else:
                print(f"[SKIP] 表不存在: {table_name}")
        except Exception as e:
            print(f"[FAIL] 删除失败 {table_name}: {e}")
            failed += 1

print(f"\n完成: 删除 {dropped} 个, 失败 {failed} 个")
