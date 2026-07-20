"""用正确的债券代码从MySQL读取真实数据写入Redis"""
import json
import time
import redis
from sqlalchemy import create_engine, text

# 连接
r = redis.Redis(host='localhost', port=6379, decode_responses=False)
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8')

date_str = "20260717"
bonds = [
    ("123273", "三江转债"),
    ("123270", "盛德转债"),
]

for bond_code, bond_name in bonds:
    print(f"\n{'='*50}")
    print(f"处理 {bond_name}({bond_code})...")
    
    # 从MySQL读取真实数据
    start = time.time()
    with engine.connect() as conn:
        result = conn.execute(text(
            f"SELECT `time`, `price`, `change_pct`, `amount`, `volume`, "
            f"`high`, `low`, `open`, `pre_close` "
            f"FROM monitor_zq_sssj_{date_str} "
            f"WHERE bond_code = :code ORDER BY `time`"
        ), {'code': bond_code})
        rows = result.fetchall()
    mysql_time = (time.time() - start) * 1000
    print(f"  MySQL查询: {len(rows)}条, {mysql_time:.0f}ms")
    
    if not rows:
        print(f"  ❌ 无数据")
        continue
    
    # 构造Redis数据
    columns = ['time', 'price', 'change_pct', 'amount', 'volume', 'high', 'low', 'open', 'pre_close']
    mapping = {}
    for row in rows:
        tick = dict(zip(columns, row))
        # 处理time字段
        t = tick['time']
        if hasattr(t, 'total_seconds'):
            total_secs = int(t.total_seconds())
            time_str = f"{total_secs // 3600:02d}:{(total_secs % 3600) // 60:02d}:{total_secs % 60:02d}"
        else:
            time_str = str(t)
        tick['time'] = time_str
        # 数值转float
        for k in columns[1:]:
            if tick[k] is not None:
                tick[k] = float(tick[k])
        mapping[time_str] = json.dumps(tick, ensure_ascii=False)
    
    # 写入Redis
    start = time.time()
    key = f"bond:tick:{bond_code}:{date_str}"
    index_key = f"bond:tick:index:{date_str}"
    
    pipe = r.pipeline()
    pipe.hset(key, mapping=mapping)
    pipe.sadd(index_key, bond_code)
    pipe.expire(key, 16 * 3600)
    pipe.expire(index_key, 16 * 3600)
    pipe.execute()
    redis_time = (time.time() - start) * 1000
    
    print(f"  Redis写入: {len(mapping)}条, {redis_time:.0f}ms")
    
    # 验证
    count = r.hlen(key)
    print(f"  验证: Redis中{count}条 ✅")
    
    # 显示首尾数据
    first = json.loads(r.hget(key, list(mapping.keys())[0]))
    last = json.loads(r.hget(key, list(mapping.keys())[-1]))
    print(f"  首条: {first['time']} 涨跌幅={first['change_pct']}%")
    print(f"  末条: {last['time']} 涨跌幅={last['change_pct']}%")

# 清理旧的错误数据
print(f"\n{'='*50}")
print("清理旧错误数据...")
for old_code in ['111060', '113064']:
    key = f"bond:tick:{old_code}:{date_str}"
    if r.exists(key):
        r.delete(key)
        print(f"  删除 {old_code} ✅")

print(f"\n{'='*50}")
print("✅ 完成！正确的测试数据已写入Redis")
print(f"  三江转债(123273): bond:tick:123273:{date_str}")
print(f"  盛德转债(123270): bond:tick:123270:{date_str}")
