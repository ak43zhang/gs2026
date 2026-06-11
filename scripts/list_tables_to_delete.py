"""列出 20260515 及之前的所有 monitor_* 表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import text
from gs2026.utils.mysql_util import get_mysql_tool

mysql_tool = get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    sql = text("""
        SELECT TABLE_NAME, 
               ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS size_mb
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'gs' 
          AND TABLE_NAME LIKE 'monitor_%'
        ORDER BY TABLE_NAME
    """)
    rows = conn.execute(sql).fetchall()
    
    to_delete = []
    to_keep = []
    
    for r in rows:
        name = r[0]
        size = float(r[1])
        # 提取日期部分（最后8位）
        date_part = name[-8:]
        try:
            int(date_part)
            if date_part <= '20260515':
                to_delete.append((name, size))
            else:
                to_keep.append((name, size))
        except ValueError:
            to_keep.append((name, size))
    
    print(f"=== 待删除表（日期 <= 20260515）===")
    print(f"{'表名':<45} {'大小(MB)':>10}")
    print('-' * 57)
    total_del = 0
    for name, size in to_delete:
        print(f"{name:<45} {size:>10}")
        total_del += size
    print('-' * 57)
    print(f"{'合计':<45} {total_del:>10.2f}")
    print(f"共 {len(to_delete)} 张表")
    
    print(f"\n=== 保留表（日期 > 20260515）===")
    total_keep = 0
    for name, size in to_keep:
        total_keep += size
    print(f"共 {len(to_keep)} 张表，合计 {total_keep:.2f} MB")
