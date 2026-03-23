"""
实时监控获取债券数据——集思录
"""

import time
import warnings
from pathlib import Path

import adata
import akshare as ak
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config('common.url')

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)

# ------------------------------
# 配置参数
INTERVAL = 3           # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
WINDOW_SECONDS = 15
# ------------------------------
def get_bond_jsl():
    """
    数据源——集思录——满足3秒，缺少成交量字段
    :return:
    """
    my_jsl_cookie = ''
    df = ak.bond_cb_jsl(cookie=my_jsl_cookie)
    df_filtered = df[(df['现价'] > 100) & (df['现价'] < 250)]
    return df_filtered

def get_bond_adata():
    """
    数据源——adata——满足3秒
    :return:
    """
    df = adata.bond.market.list_market_current()
    df_filtered = df[(df['price'] > 110) & (df['price'] < 250)]
    return df_filtered


def get_bond(data_source: str) -> pd.DataFrame:
    """
    根据数据源名称获取债券数据，始终返回一个 DataFrame。
    如果数据源不存在，返回空的 DataFrame。
    """
    handlers = {
        'jsl': get_bond_jsl,
        'adata': get_bond_adata,
    }

    func = handlers.get(data_source)
    if func is not None:
        return func()

    print(f"警告：未知的数据源 '{data_source}'，返回空 DataFrame。")
    return pd.DataFrame()

SOURCE_BOND_FULL_COLUMNS = ['bond_code',
                            'bond_name',
                            'price','open','high','low',
                            'pre_close','change','change_pct',
                            'volume', 'amount']

def deal_zq_works(loop_start):
    """
        处理债券数据工作流
        获取债券实时数据，格式化后存储到 Redis，并加载历史窗口数据用于分析。
        Args:
            loop_start: 循环开始时间，用于生成日期和时间字符串
        Returns:
            None
        Raises:
            Exception: 记录异常日志，不影响主流程继续
        """
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        df_now = get_bond('adata')
        if df_now.empty:
            logger.info(f"获取债券数据为空: {date_str} {time_full}")
            return
        df_now['bond_code'] = df_now['bond_code'].astype(str).str.zfill(6)
    except ConnectionError as e:
        logger.error(f"网络连接异常: {e}")
        time.sleep(60)
        return

    except ValueError as e:
        logger.error(f"数据格式错误: {e}")
        return

    except KeyError as e:
        logger.error(f"数据缺少必要列 'bond_code': {e}")
        return

    except Exception as e:
        # 捕获其他未预期的异常
        logger.error(f"获取债券数据异常: {e}", exc_info=True)
        time.sleep(60)
        return

    df_now['time'] = time_full

    # 存储股票实时数据
    sssj_table = f"monitor_zq_sssj_{date_str}"
    msac.save_dataframe(df_now, sssj_table, time_full, EXPIRE_SECONDS)

    # 获取前30秒的数据（从 Redis 加载）
    window_seconds_offset = (WINDOW_SECONDS + INTERVAL - 1) // INTERVAL
    df_prev = redis_util.load_dataframe_by_offset(sssj_table,
                                                  offset=window_seconds_offset,
                                                  use_compression=False)

    # 计算并存储大盘强度
    culculate_zq_apqd_top30(df_now, df_prev, date_str, time_full, loop_start)


def culculate_zq_apqd_top30(df_now, df_prev, date_str, time_full, loop_start):
    """
    计算大盘强度（APQD）和涨幅/涨速前30榜单，并存储。

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 30秒前数据（可能为空）。
        date_str (str): 日期字符串 YYYYMMDD。
        time_full (str): 时间字符串 HH:MM:SS。
        loop_start (datetime): 轮询开始时间。
    """
    # ---------- 列名标准化：将原始列名映射为统一名称 ----------
    rename_map = {}
    if 'bond_code' in df_now.columns and 'code' not in df_now.columns:
        rename_map['bond_code'] = 'code'
    if 'bond_name' in df_now.columns and 'name' not in df_now.columns:
        rename_map['bond_name'] = 'name'
    if rename_map:
        df_now = df_now.rename(columns=rename_map)
        if df_prev is not None and not df_prev.empty:
            df_prev = df_prev.rename(columns=rename_map)

    # ---------- 确保必要列存在 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        raise ValueError(f"df_now 缺少必要列 {required_cols}，当前列：{df_now.columns.tolist()}")

    # ---------- 计算大盘强度 ----------
    judge30 = msac.judge_market_strength(msac.get_market_stats(df_now, df_prev))
    apqd_table = f"monitor_zq_apqd_{date_str}"
    msac.save_dataframe(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    if df_prev is not None and not df_prev.empty:
        top30_df = msac.calculate_top30_v3(df_now, df_prev, loop_start)   # v3 内部已处理列名
        if not top30_df.empty:
            gp_top30_table = f"monitor_zq_top30_{date_str}"
            result_df = msac.attack_conditions(top30_df, rank_name='bond')
            msac.save_dataframe(result_df, gp_top30_table, time_full, EXPIRE_SECONDS)
            # 上攻排行
            rank_result = redis_util.update_rank_redis(result_df, 'bond', date_str=date_str)
            # 收盘时保存到 MySQL
            if time_full == "15:00:00":
                msac.save_rank_to_mysql(rank_result, 'bond', date_str)




if __name__ == "__main__":
    msac.run_monitor_loop_synced(deal_zq_works, interval=INTERVAL)
