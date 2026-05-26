#!/usr/bin/env python
"""测试 MySQL 连接"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
        row = result.fetchone()
        print(f'Threads_connected: {row[1]}')

        result = conn.execute(text('SHOW PROCESSLIST'))
        rows = result.fetchall()
        print(f'Total connections: {len(rows)}')
        print('OK - MySQL is accessible')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
