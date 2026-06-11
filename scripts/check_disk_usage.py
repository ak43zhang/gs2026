"""查看可清理的历史表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import text
from gs2026.utils.mysql_util import get_mysql_tool

mysql_tool = get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    # 查看 monitor_ 开头的表及大小
    sql = text("""
        SELECT TABLE_NAME, 
               ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS size_mb
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'gs' 
          AND TABLE_NAME LIKE 'monitor_%'
        ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
        LIMIT 30
    """)
    rows = conn.execute(sql).fetchall()
    
    total = 0
    print(f"{'表名':<45} {'大小(MB)':>10}")
    print('-' * 57)
    for r in rows:
        print(f"{r[0]:<45} {r[1]:>10}")
        total += float(r[1])
    print('-' * 57)
    print(f"{'合计':<45} {total:>10.2f}")
