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

    def fetch_data(table_name):
        """尝试获取指定表的最新数据，最多等待 max_wait 秒"""
        start = time.time()
        for _ in range(max_retries):
            if time.time() - start > max_wait:
                return None
            df = redis_util.load_dataframe_by_offset(table_name, offset=0, use_compression=False)
            if df is not None and not df.empty:
                if 'time' in df.columns and df['time'].iloc[0] == time_full:
                    return df
            time.sleep(retry_delay)
        return None

    # 并发提交两个任务
    future_zq = _executor.submit(fetch_data, zq_top30_table)
    future_gp = _executor.submit(fetch_data, gp_top30_table)

    # 等待两个任务完成（内部超时控制，不会阻塞太久）
    wait([future_zq, future_gp], return_when=ALL_COMPLETED)

    zq_df = future_zq.result()
    gp_df = future_gp.result()

    # 任一数据缺失则跳过本次分析
    if gp_df is None or zq_df is None or gp_df.empty or zq_df.empty:
        print("gp_df 或者 zq_df 数据为空或时间不匹配，本次跳过")
        return

    # 后续数据处理（保持不变）
    zq_df = zq_df[(zq_df['total_score'] <= 5) & (zq_df['momentum'] > 100) & (zq_df['zf_30'] > 0.2) & (zq_df['amount_rank']<30)]
    gp_df = gp_df[(gp_df['zf_30'] > 0.2) & (gp_df['total_score'] <= 60)]
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