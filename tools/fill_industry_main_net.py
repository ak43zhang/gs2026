"""
填充行业累计主力净额数据 - 优化版（批量处理）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.disable(logging.INFO)  # 关闭info日志减少输出

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

db_config = config_util.get_config('mysql', 'url')
if isinstance(db_config, dict):
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    url = db_config
engine = create_engine(url)

DATE_STR = '20260526'
SSSJ_TABLE = f'monitor_gp_sssj_{DATE_STR}'
TOP30_TABLE = f'monitor_gp_top30_{DATE_STR}'
HY_TABLE = f'monitor_hy_top30_{DATE_STR}'

def main():
    logging.disable(logging.INFO)
    from gs2026.monitor.monitor_stock import calculate_industry_topn
    from gs2026.utils import redis_util

    print(f"=== 填充行业累计主力净额: {DATE_STR} ===")

    # 1. 获取所有时间点
    with engine.connect() as conn:
        times_df = pd.read_sql(f"SELECT DISTINCT time FROM {SSSJ_TABLE} ORDER BY time ASC", conn)
    timepoints = times_df['time'].tolist()
    print(f"共 {len(timepoints)} 个时间点: {timepoints[0]} ~ {timepoints[-1]}")

    # 2. 删除旧表 + 清除Redis
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {HY_TABLE}"))
        conn.commit()
    print(f"已删除旧表 {HY_TABLE}")

    try:
        client = redis_util._get_redis_client()
        client.delete(f'rank:industry:code_{DATE_STR}')
        client.delete(f'rank:industry:code_name_{DATE_STR}')
        print("已清除 Redis keys")
    except Exception as e:
        print(f"清除 Redis 失败: {e}")

    # 3. 逐时间点处理（禁用日志后速度快得多）
    total_rows = 0
    success_count = 0
    batch_results = []

    for i, time_str in enumerate(timepoints):
        try:
            with engine.connect() as conn:
                all_stock_df = pd.read_sql(f"SELECT * FROM {SSSJ_TABLE} WHERE time = '{time_str}'", conn)
                top30_df = pd.read_sql(f"SELECT * FROM {TOP30_TABLE} WHERE time = '{time_str}'", conn)

            if all_stock_df.empty:
                continue

            hy_all_df = calculate_industry_topn(top30_df, all_stock_df, DATE_STR, time_str)
            if hy_all_df.empty:
                continue

            batch_results.append(hy_all_df)
            total_rows += len(hy_all_df)

            # 取 TOP5 更新 Redis
            hy_top5_df = hy_all_df.head(5)
            redis_util.update_rank_redis(hy_top5_df, 'industry', date_str=DATE_STR)
            success_count += 1

            # 每50个时间点批量写入MySQL
            if len(batch_results) >= 50:
                batch_df = pd.concat(batch_results, ignore_index=True)
                with engine.connect() as conn:
                    batch_df.to_sql(HY_TABLE, con=conn, if_exists='append', index=False)
                    conn.commit()
                batch_results = []

            if (i + 1) % 200 == 0:
                print(f"  进度: {i+1}/{len(timepoints)}，已处理 {success_count} 个有效时间点，{total_rows} 行")

        except Exception as e:
            print(f"  [错误] {time_str}: {e}")
            import traceback
            traceback.print_exc()
            break  # 遇到错误停止

    # 写入剩余批次
    if batch_results:
        batch_df = pd.concat(batch_results, ignore_index=True)
        with engine.connect() as conn:
            batch_df.to_sql(HY_TABLE, con=conn, if_exists='append', index=False)
            conn.commit()

    print(f"\n=== 完成 ===")
    print(f"成功: {success_count}/{len(timepoints)} 个时间点")
    print(f"总写入: {total_rows} 行")

    # 验证
    print(f"\n=== 验证 ===")
    with engine.connect() as conn:
        verify_df = pd.read_sql(f"""
            SELECT code, name, `count`, total, industry_cumulative_main_net, final_score, `rank`
            FROM {HY_TABLE}
            WHERE time = (SELECT MAX(time) FROM {HY_TABLE})
            ORDER BY `rank` ASC LIMIT 5
        """, conn)
        print(f"最后时间点 TOP5:")
        for _, row in verify_df.iterrows():
            print(f"  {row['rank']}. {row['name']}: 上涨{row['count']}/{row['total']}, "
                  f"主力净额={row['industry_cumulative_main_net']}, 得分={row['final_score']}")

if __name__ == '__main__':
    main()
