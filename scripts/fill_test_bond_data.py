"""
填充测试数据到Redis - 20260717三江转债和盛德转债

用于测试债券上攻排行悬停分时图效果
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import random
from datetime import datetime

# 直接使用Redis
import redis

def get_redis():
    """获取Redis连接"""
    return redis.Redis(host='localhost', port=6379, decode_responses=False)

def generate_tick_data(bond_code, date_str, base_price, base_change, trend='up'):
    """生成模拟分时数据"""
    ticks = []
    
    # 交易时间 09:30:00 - 15:00:00
    time_points = []
    for h in [9, 10, 11, 13, 14]:
        for m in range(60):
            if h == 9 and m < 30:
                continue
            if h == 11 and m > 30:
                continue
            if h == 15 and m > 0:
                break
            for s in [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57]:
                time_points.append(f"{h:02d}:{m:02d}:{s:02d}")
    
    price = base_price
    change_pct = base_change
    
    for i, time_str in enumerate(time_points):
        # 根据趋势添加波动
        if trend == 'up':
            # 上涨趋势，整体向上波动
            drift = 0.001 if i > len(time_points) / 2 else -0.0005
        else:
            # 下跌趋势，整体向下波动
            drift = -0.001 if i > len(time_points) / 2 else 0.0005
        
        price_change = random.uniform(-0.03, 0.03) + drift
        price += price_change
        change_pct += random.uniform(-0.015, 0.015) + drift * 100
        
        tick = {
            'time': time_str,
            'price': round(price, 3),
            'change_pct': round(change_pct, 2),
            'amount': round(random.uniform(10000, 50000), 2),
            'volume': round(random.uniform(100, 500), 2),
            'high': round(price + random.uniform(0, 0.3), 3),
            'low': round(price - random.uniform(0, 0.3), 3),
            'open': round(base_price, 3),
            'pre_close': round(base_price * (1 - base_change/100), 3),
        }
        ticks.append(tick)
    
    return ticks

def write_to_redis(bond_code, date_str, ticks):
    """直接写入Redis"""
    r = get_redis()
    
    key = f"bond:tick:{bond_code}:{date_str}"
    index_key = f"bond:tick:index:{date_str}"
    
    # 构造批量数据
    mapping = {}
    for tick in ticks:
        time_str = tick['time']
        mapping[time_str] = json.dumps(tick, ensure_ascii=False)
    
    # Pipeline执行
    pipe = r.pipeline()
    pipe.hset(key, mapping=mapping)
    pipe.sadd(index_key, bond_code)
    pipe.expire(key, 16 * 3600)  # 16小时过期
    pipe.expire(index_key, 16 * 3600)
    pipe.execute()
    
    return True

def main():
    """填充测试数据"""
    print("=" * 50)
    print("填充Redis测试数据 - 20260717")
    print("=" * 50)
    
    date_str = "20260717"
    
    # 三江转债 - 上涨趋势（红色）
    print("\n📊 生成三江转债数据...")
    sanjiang_ticks = generate_tick_data("111060", date_str, 115.50, 2.35, trend='up')
    print(f"   生成 {len(sanjiang_ticks)} 条数据")
    print(f"   起始涨跌幅: {sanjiang_ticks[0]['change_pct']}%")
    print(f"   结束涨跌幅: {sanjiang_ticks[-1]['change_pct']}%")
    
    # 盛德转债 - 下跌趋势（绿色）
    print("\n📊 生成盛德转债数据...")
    shengde_ticks = generate_tick_data("113064", date_str, 108.20, -1.85, trend='down')
    print(f"   生成 {len(shengde_ticks)} 条数据")
    print(f"   起始涨跌幅: {shengde_ticks[0]['change_pct']}%")
    print(f"   结束涨跌幅: {shengde_ticks[-1]['change_pct']}%")
    
    # 写入Redis
    print("\n💾 写入Redis...")
    
    try:
        write_to_redis("111060", date_str, sanjiang_ticks)
        print(f"   三江转债(111060): ✅ 成功")
    except Exception as e:
        print(f"   三江转债(111060): ❌ 失败 - {e}")
    
    try:
        write_to_redis("113064", date_str, shengde_ticks)
        print(f"   盛德转债(113064): ✅ 成功")
    except Exception as e:
        print(f"   盛德转债(113064): ❌ 失败 - {e}")
    
    # 验证
    print("\n🔍 验证数据...")
    r = get_redis()
    
    key1 = f"bond:tick:111060:{date_str}"
    key2 = f"bond:tick:113064:{date_str}"
    
    count1 = r.hlen(key1)
    count2 = r.hlen(key2)
    
    print(f"   三江转债: {count1} 条")
    print(f"   盛德转债: {count2} 条")
    
    # 读取样本
    data1 = r.hgetall(key1)
    if data1:
        first_key = list(data1.keys())[0]
        first_tick = json.loads(data1[first_key])
        print(f"   三江样本: {first_tick['time']} 涨跌幅:{first_tick['change_pct']}%")
    
    data2 = r.hgetall(key2)
    if data2:
        first_key = list(data2.keys())[0]
        first_tick = json.loads(data2[first_key])
        print(f"   盛德样本: {first_tick['time']} 涨跌幅:{first_tick['change_pct']}%")
    
    print("\n" + "=" * 50)
    print("✅ 测试数据填充完成")
    print("=" * 50)
    print("\n测试URL:")
    print(f"  http://localhost:8080/api/bond/tick/111060")
    print(f"  http://localhost:8080/api/bond/tick/113064")

if __name__ == "__main__":
    main()
