import sys
sys.path.insert(0, 'src')
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()
client = redis_util._get_redis_client()

date = '20260403'

# 模拟债券数据
bonds = [
    {'code': '123054', 'name': '思特转债', 'count': 156},
    {'code': '113601', 'name': 'Z泰1转', 'count': 141},
]

# 获取最新时间
sssj_table = f'monitor_zq_sssj_{date}'
ts_key = f'{sssj_table}:timestamps'
latest_ts = client.lindex(ts_key, 0)
if latest_ts:
    query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
    print(f'查询时间: {query_time}')
else:
    print('无时间戳数据')
    sys.exit(1)

# 获取债券代码
bond_codes = [str(bond.get('code', '')) for bond in bonds]
print(f'债券代码: {bond_codes}')

# 直接查询Redis
redis_key = f'{sssj_table}:{query_time}'
print(f'Redis key: {redis_key}')

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
if df is not None and not df.empty:
    print(f'数据行数: {len(df)}')
    print(f'数据列: {df.columns.tolist()}')
    
    # 转换代码为字符串
    df['bond_code'] = df['bond_code'].astype(str).str.replace('.0', '', regex=False)
    
    # 构建字典
    result = df.set_index('bond_code')['change_pct'].to_dict()
    print(f'字典大小: {len(result)}')
    
    # 查询特定代码
    for code in bond_codes:
        change_pct = result.get(code, 'NOT_FOUND')
        print(f'代码 {code}: {change_pct}')
else:
    print('数据为空')
