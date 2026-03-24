"""
实时监控股票债券上涨信号
"""

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config('common.url')
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接（关闭自动解码，以支持压缩）
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
# 统一获取字典
mid_df = redis_util.get_dict("data_bond_ths")

# ------------------------------
# 配置参数
INTERVAL = 3           # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
WINDOW_SECONDS = 15
# ------------------------------

# 全局线程池（在文件顶部定义）
_executor = ThreadPoolExecutor(max_workers=2)

def monitor_zs(loop_start):
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")
    zq_top30_table = f"monitor_zq_top30_{date_str}"
    gp_top30_table = f"monitor_gp_top30_{date_str}"

    max_retries = 30
    retry_delay = 0.1
    max_wait = 2.9  # 略小于 INTERVAL，保证整体返回不超时

    # 记录上次成功处理的数据时间，避免重复处理
    if not hasattr(monitor_zs, '_last_gp_time'):
        monitor_zs._last_gp_time = None
    if not hasattr(monitor_zs, '_last_zq_time'):
        monitor_zs._last_zq_time = None

    def fetch_data(table_name, last_processed_time=None):
        """
        尝试获取指定表的最新数据，最多等待 max_wait 秒。
        策略：
          1. 优先匹配当前 tick 的精确时间（time_full）
          2. 如果超时仍未匹配到，退而取 Redis 中的最新数据（只要比上次处理的更新即可）
        """
        start = time.time()
        latest_df = None

        for _ in range(max_retries):
            if time.time() - start > max_wait:
                break
            df = redis_util.load_dataframe_by_offset(table_name, offset=0, use_compression=False)
            if df is not None and not df.empty and 'time' in df.columns:
                data_time = df['time'].iloc[0]
                # 精确匹配当前 tick → 立即返回
                if data_time == time_full:
                    return df
                # 记录最新可用数据（只要不是上次已处理过的）
                if data_time != last_processed_time:
                    latest_df = df
            time.sleep(retry_delay)

        # 超时未精确匹配，使用最新可用数据（容忍1个tick的延迟）
        if latest_df is not None:
            data_time = latest_df['time'].iloc[0]
            logger.debug(f"{table_name} 未匹配到 {time_full}，使用最新数据 time={data_time}")
        return latest_df

    # 并发提交两个任务
    future_zq = _executor.submit(fetch_data, zq_top30_table, monitor_zs._last_zq_time)
    future_gp = _executor.submit(fetch_data, gp_top30_table, monitor_zs._last_gp_time)

    # 等待两个任务完成（内部超时控制，不会阻塞太久）
    wait([future_zq, future_gp], return_when=ALL_COMPLETED)

    zq_df = future_zq.result()
    gp_df = future_gp.result()

    # 任一数据缺失则跳过本次分析
    if gp_df is None or zq_df is None or gp_df.empty or zq_df.empty:
        missing = []
        if gp_df is None or (gp_df is not None and gp_df.empty):
            missing.append("gp_top30")
        if zq_df is None or (zq_df is not None and zq_df.empty):
            missing.append("zq_top30")
        logger.info(f"数据缺失 {missing}，本次跳过 (期望 time={time_full})")
        return

    # 更新已处理时间标记
    monitor_zs._last_gp_time = gp_df['time'].iloc[0]
    monitor_zs._last_zq_time = zq_df['time'].iloc[0]

    # 后续数据处理（保持不变）
    # zq_df = zq_df[(zq_df['total_score'] < 1) & (zq_df['momentum'] > 100) & (zq_df['zf_30'] > 0.2) & (zq_df['amount_rank']<30)]
    # gp_df = gp_df[(gp_df['zf_30'] > 0.2) & (gp_df['total_score_rank'] <= 60)]
    gp_df['code'] = gp_df['code'].astype(str).str.zfill(6)
    zq_df['code'] = zq_df['code'].astype(str).str.zfill(6)

    mid_df['stock_code'] = mid_df['stock_code'].astype(str).str.zfill(6)

    step1 = pd.merge(
        gp_df, mid_df,
        left_on='code', right_on='stock_code',
        how='inner', suffixes=('_gp', '_mid')
    )

    result = pd.merge(
        step1, zq_df,
        left_on='name_mid', right_on='name',
        how='inner', suffixes=('', '_zq')
    )

    if not result.empty:
        print("================================================================")
        print(time_full)
        table_name = f"monitor_combine_{date_str}"
        print(zq_df)
        result['time'] = time_full
        result_df = result[['code', 'name', 'code_gp', 'name_gp', 'zf_30', 'zf_30_zq','momentum_zq','momentum_rank_zq', 'amount_rank', 'amount_rank_zq',
                            'total_score_rank', 'total_score_rank_zq']]
        print(result_df)
        msac.save_dataframe(result, table_name, time_full, EXPIRE_SECONDS)




if __name__ == "__main__":
    msac.run_monitor_loop_synced(monitor_zs, interval=INTERVAL)