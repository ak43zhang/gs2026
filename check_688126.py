import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.utils import mysql_util
from sqlalchemy import text

tool = mysql_util.get_mysql_tool()

with tool.engine.connect() as conn:
    # 检查688126的数据
    result = conn.execute(text("SELECT COUNT(*) as cnt FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126'"))
    cnt = result.fetchone()[0]
    print(f'688126记录数: {cnt}')
    
    if cnt > 0:
        # 获取最新的一条
        result = conn.execute(text("SELECT time_str, cumulative_main_net FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY time_str DESC LIMIT 1"))
        row = result.fetchone()
        print(f'最新记录: time={row[0]}, cumulative={row[1]}')
