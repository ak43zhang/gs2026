import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
from gs2026.utils import config_util

url = config_util.get_config('common.url')
mysql_tool = mysql_util.MysqlTool(url)

# 查询2026年4月的交易日
sql = "SELECT trade_date FROM data_jyrl WHERE trade_status = 1 AND trade_date BETWEEN '2026-04-01' AND '2026-04-30' ORDER BY trade_date"
df = mysql_tool.query_data(sql)
print('2026年4月交易日:')
print(df)
print(f'\n共 {len(df)} 个交易日')