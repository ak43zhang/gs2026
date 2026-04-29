#!/usr/bin/env python3
"""
修复累计主力净额计算逻辑
替换 monitor_stock.py 中的 calculate_cumulative_main_net 函数
"""

def calculate_cumulative_main_net_v2(df, table_name, current_time, redis_client=None):
    """
    计算累计主力净额（改进版）
    
    不依赖上一时刻，而是找"上一个有累计值的时间点"
    
    Args:
        df: 当前时刻数据（包含 main_net_amount）
        table_name: 表名（如 monitor_gp_sssj_20260429）
        current_time: 当前时间（HH:MM:SS）
        redis_client: Redis客户端（可选）
    
    Returns:
        添加了 cumulative_main_net 列的 DataFrame
    """
    import pandas as pd
    from sqlalchemy import create_engine, text
    
    # 初始化累计值为当前值
    df['cumulative_main_net'] = df['main_net_amount'].fillna(0)
    
    try:
        # 方法1：从Redis时间戳列表找上一个有数据的时间点
        prev_time = None
        if redis_client:
            try:
                # 获取时间戳列表（按时间倒序）
                ts_key = f"{table_name}:timestamps"
                all_ts = redis_client.lrange(ts_key, 0, -1)
                
                if all_ts:
                    # 解码并排序
                    timestamps = sorted([
                        t.decode('utf-8') if isinstance(t, bytes) else t
                        for t in all_ts
                    ])
                    
                    # 找当前时间之前的最新时间
                    for ts in reversed(timestamps):
                        if ts < current_time:
                            prev_time = ts
                            break
            except Exception as e:
                print(f"从Redis获取时间戳失败: {e}")
        
        # 方法2：如果Redis没有，从MySQL查询
        if not prev_time:
            try:
                engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
                
                # 查询当前时间之前最新的时间点
                query = f"""
                    SELECT MAX(time) as prev_time
                    FROM {table_name}
                    WHERE time < '{current_time}'
                    LIMIT 1
                """
                
                with engine.connect() as conn:
                    result = conn.execute(text(query))
                    row = result.fetchone()
                    if row and row[0]:
                        prev_time = row[0]
            except Exception as e:
                print(f"从MySQL获取上一时间失败: {e}")
        
        # 如果找到上一时间点，查询累计值
        if prev_time:
            try:
                engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
                stock_codes = df['stock_code'].tolist()
                codes_str = ','.join([f"'{c}'" for c in stock_codes])
                
                query = f"""
                    SELECT stock_code, cumulative_main_net
                    FROM {table_name}
                    WHERE time = '{prev_time}' AND stock_code IN ({codes_str})
                    AND cumulative_main_net != 0
                """
                
                with engine.connect() as conn:
                    prev_cumulative = pd.read_sql(query, conn)
                    
                    if not prev_cumulative.empty:
                        # 合并上一时刻的累计值
                        df = df.merge(
                            prev_cumulative[['stock_code', 'cumulative_main_net']],
                            on='stock_code',
                            how='left',
                            suffixes=('', '_prev')
                        )
                        
                        # 计算新的累计值 = 上一累计值 + 当前值
                        df['cumulative_main_net_prev'] = df['cumulative_main_net_prev'].fillna(0)
                        df['cumulative_main_net'] = df['cumulative_main_net_prev'] + df['main_net_amount'].fillna(0)
                        
                        # 删除临时列
                        df = df.drop(columns=['cumulative_main_net_prev'], errors='ignore')
                        
                        print(f"[{current_time}] 从 {prev_time} 获取累计值，共 {len(prev_cumulative)} 只股票")
                    else:
                        print(f"[{current_time}] {prev_time} 无累计值数据，使用当前值")
            except Exception as e:
                print(f"查询上一时刻累计值失败: {e}")
        else:
            print(f"[{current_time}] 无上一时刻数据，使用当前值作为累计值")
            
    except Exception as e:
        print(f"计算累计主力净额失败: {e}")
        # 出错时使用当前值
        df['cumulative_main_net'] = df['main_net_amount'].fillna(0)
    
    return df


# 使用示例
if __name__ == "__main__":
    import pandas as pd
    from gs2026.utils import redis_util
    
    # 测试数据
    test_df = pd.DataFrame({
        'stock_code': ['000001', '000002', '300243'],
        'short_name': ['平安银行', '万科A', '测试'],
        'main_net_amount': [1000000, -500000, 2000000]
    })
    
    # 初始化Redis
    redis_util.init_redis(host='localhost', port=6379, decode_responses=False)
    client = redis_util._get_redis_client()
    
    # 测试计算
    result = calculate_cumulative_main_net_v2(
        test_df, 
        'monitor_gp_sssj_20260429', 
        '10:00:03',
        client
    )
    
    print("\n结果:")
    print(result[['stock_code', 'main_net_amount', 'cumulative_main_net']])
