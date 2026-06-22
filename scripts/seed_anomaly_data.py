"""将今日所有涨停过的股票写入 stock_anomaly 表，用于验证异动分析流程"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import json
from datetime import date
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import redis

url = config_util.get_config('common.url')
engine = create_engine(url)
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

trading_date = date.today().strftime('%Y-%m-%d')  # 2026-06-22
date_str = trading_date.replace('-', '')  # 20260622
sssj_table = f"monitor_gp_sssj_{date_str}"

print(f"查询表: {sssj_table}")
print(f"查找今日所有涨停过的股票（任意时间点涨幅>=9.8%）")

with engine.connect() as conn:
    # 1. 查找所有涨停过的股票及其首次涨停时间
    sql = text(f"""
        SELECT 
            stock_code,
            short_name,
            MIN(time) as first_zt_time,
            MAX(price) as max_price,
            MAX(change_pct) as max_change_pct
        FROM {sssj_table}
        WHERE change_pct >= 9.8
        GROUP BY stock_code, short_name
        ORDER BY first_zt_time
    """)
    result = conn.execute(sql)
    zt_stocks = result.fetchall()
    
    print(f"今日涨停过的股票数: {len(zt_stocks)}")
    
    if not zt_stocks:
        print("无涨停股票")
        sys.exit(0)

    # 2. 写入 stock_anomaly
    inserted = 0
    skipped = 0
    
    for row in zt_stocks:
        code = row[0]
        name = row[1]
        first_zt_time = row[2]
        max_price = float(row[3]) if row[3] else 0
        max_pct = float(row[4]) if row[4] else 0
        
        # 检查是否已存在（避免重复写入）
        check_sql = text("SELECT COUNT(*) FROM stock_anomaly WHERE trading_date=:td AND stock_code=:c AND anomaly_type='zt_hit'")
        check_result = conn.execute(check_sql, {'td': trading_date, 'c': code})
        if check_result.scalar() > 0:
            skipped += 1
            continue
        
        # 查 watchlist
        wl_raw = redis_client.hget(f"anomaly:watchlist:{trading_date}", code)
        pre_messages = None
        if wl_raw:
            try:
                wl_info = json.loads(wl_raw)
                pre_messages = json.dumps(wl_info.get('messages', []), ensure_ascii=False)
            except:
                pass
        
        # 写入
        insert_sql = text("""
            INSERT INTO stock_anomaly 
            (trading_date, stock_code, stock_name, anomaly_type, anomaly_time,
             price, change_pct, continuous_zt, ai_status,
             pre_forecast_messages, forecast_match)
            VALUES (:td, :code, :name, 'zt_hit', :atime,
                    :price, :pct, 0, 'pending',
                    :pm, 'pending')
        """)
        conn.execute(insert_sql, {
            'td': trading_date, 'code': code, 'name': name,
            'atime': str(first_zt_time), 'price': max_price, 'pct': max_pct,
            'pm': pre_messages
        })
        inserted += 1
        
        wl_tag = 'WL' if wl_raw else '--'
        print(f"  [{wl_tag}] {code} {name} {first_zt_time} +{max_pct:.2f}%")
    
    conn.commit()
    
    print(f"\n写入完成: {inserted} 条新记录")
    print(f"已存在跳过: {skipped} 条")
    print(f"总计: {len(zt_stocks)} 只涨停股票")
    print(f"\n可启动 anomaly_analyzer 验证分析流程:")
    print(f"  python -m gs2026.analysis.worker.realtime.anomaly_analyzer")
