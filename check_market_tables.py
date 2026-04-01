"""检查大盘数据表"""
from gs2026.utils.mysql_util import get_mysql_tool
from datetime import datetime
import pandas as pd

date_str = datetime.now().strftime('%Y%m%d')
print(f'当前日期: {date_str}')

mysql = get_mysql_tool()
tables = [
    f'monitor_gp_sssj_{date_str}',
    f'monitor_zq_sssj_{date_str}',
    f'monitor_dp_signal_{date_str}',
    f'monitor_gp_apqd_{date_str}',
    f'monitor_zq_apqd_{date_str}',
]

for table in tables:
    try:
        exists = mysql.check_table_exists(table)
        if exists:
            # 使用 engine 查询记录数
            with mysql.engine.connect() as conn:
                result = pd.read_sql(f'SELECT COUNT(*) as cnt FROM {table}', conn)
                cnt = result['cnt'].iloc[0] if not result.empty else 0
            print(f'[OK] {table}: {cnt} 条记录')
        else:
            print(f'[MISSING] {table}: 不存在')
    except Exception as e:
        print(f'[ERROR] {table}: {e}')
