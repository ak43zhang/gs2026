"""删除 20260515 及之前的所有 monitor_* 表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import text
from gs2026.utils.mysql_util import get_mysql_tool

mysql_tool = get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    # 获取待删除表
    sql = text("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'gs' 
          AND TABLE_NAME LIKE 'monitor_%'
        ORDER BY TABLE_NAME
    """)
    rows = conn.execute(sql).fetchall()
    
    to_delete = []
    for r in rows:
        name = r[0]
        date_part = name[-8:]
        try:
            int(date_part)
            if date_part <= '20260515':
                to_delete.append(name)
        except ValueError:
            pass
    
    print(f"待删除: {len(to_delete)} 张表")
    
    # 批量删除（每次10张，避免超时）
    deleted = 0
    failed = 0
    for i in range(0, len(to_delete), 10):
        batch = to_delete[i:i+10]
        drop_sql = "DROP TABLE IF EXISTS " + ", ".join(f"`{t}`" for t in batch)
        try:
            conn.execute(text(drop_sql))
            conn.commit()
            deleted += len(batch)
            print(f"[{deleted}/{len(to_delete)}] 已删除: {batch[0]} ~ {batch[-1]}")
        except Exception as e:
            failed += len(batch)
            print(f"[ERROR] 删除失败: {batch[0]} ~ {batch[-1]}: {e}")
    
    print(f"\n完成: 删除 {deleted} 张，失败 {failed} 张")
