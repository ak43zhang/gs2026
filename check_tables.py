import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util, mysql_util
url = config_util.get_config('common.url')
mysql_tool = mysql_util.MysqlTool(url)
from sqlalchemy import text

with mysql_tool.engine.connect() as conn:
    # 查找监控相关的表
    result = conn.execute(text("SHOW TABLES LIKE 'monitor%'"))
    tables = [row[0] for row in result]
    print('监控相关表:')
    for t in tables[:50]:
        print(t)
        # 获取表结构
        cols = conn.execute(text(f"DESCRIBE {t}"))
        for col in cols:
            print(f"  - {col[0]}: {col[1]}")
        print()
