"""检查Redis中的大盘数据"""
from gs2026.utils import redis_util
from datetime import datetime

date_str = datetime.now().strftime('%Y%m%d')
print(f'当前日期: {date_str}')

# 初始化Redis
redis_util.init_redis()
redis_client = redis_util.con

# 检查Redis中的键
patterns = [
    f'monitor_gp_apqd_{date_str}',
    f'monitor_zq_apqd_{date_str}',
]

for pattern in patterns:
    try:
        # 检查key是否存在
        exists = redis_client.exists(pattern)
        print(f'\nKey: {pattern}')
        print(f'  Exists: {exists}')

        if exists:
            # 获取数据类型
            data_type = redis_client.type(pattern)
            print(f'  Type: {data_type}')

            # 获取数据长度
            if data_type == 'string':
                length = redis_client.strlen(pattern)
                print(f'  Length: {length} bytes')
            elif data_type == 'list':
                length = redis_client.llen(pattern)
                print(f'  Length: {length} items')

            # 尝试获取DataFrame
            df = redis_util.load_dataframe_by_key(pattern, use_compression=False)
            if df is not None and not df.empty:
                print(f'  DataFrame shape: {df.shape}')
                print(f'  Columns: {list(df.columns)}')
                print(f'  Last row time: {df.iloc[-1].get("time", "N/A")}')
            else:
                print(f'  DataFrame: None or empty')
    except Exception as e:
        print(f'  Error: {e}')
