"""
实时监控股票债券上涨信号 - 串行执行，严格时间对齐
"""

import time
import warnings
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

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接（关闭自动解码，以支持压缩）
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
# 统一获取字典
mid_df = redis_util.get_dict("data_bond_ths")

# 检查股债映射数据是否加载成功
if mid_df is None or mid_df.empty:
    logger.warning("股债映射数据(data_bond_ths)未加载，将在运行时重试")
    mid_df = pd.DataFrame(columns=['stock_code', 'bond_code', 'name'])
else:
    logger.info(f"股债映射数据加载成功: {len(mid_df)}条记录")

# 尝试导入 WebSocket 通知模块（可选）
try:
    from gs2026.utils.websocket_notifier import notify_new_signal
    _websocket_available = True
except ImportError:
    _websocket_available = False
    logger.info("WebSocket 通知模块未安装，跳过实时推送")

# ------------------------------
# 配置参数
INTERVAL = 3              # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间（秒）
MAX_WAIT = 2.9            # 最大等待时间（必须 < INTERVAL）
RETRY_DELAY = 0.1         # 重试间隔（秒）
# ------------------------------

# 记录上次成功处理的数据时间，避免重复处理
_last_gp_time = None
_last_zq_time = None


def fetch_bond_data(table_name: str, target_time: str, max_wait: float = MAX_WAIT) -> pd.DataFrame:
    """
    获取债券数据（串行，先执行）
    
    Args:
        table_name: 表名
        target_time: 目标时间
        max_wait: 最大等待时间
    
    Returns:
        DataFrame 或 None
    """
    start = time.time()
    
    while (time.time() - start) < max_wait:
        df = redis_util.load_dataframe_by_offset(table_name, offset=0, use_compression=False)
        
        if df is not None and not df.empty and 'time' in df.columns:
            data_time = df['time'].iloc[0]
            # 精确匹配目标时间
            if data_time == target_time:
                return df
        
        time.sleep(RETRY_DELAY)
    
    return None


def fetch_stock_by_bond_time(table_name: str, bond_time: str, max_wait: float = MAX_WAIT) -> pd.DataFrame:
    """
    根据债券时间获取股票数据（严格时间对齐）
    
    Args:
        table_name: 表名
        bond_time: 债券时间（用于精确匹配）
        max_wait: 最大等待时间
    
    Returns:
        DataFrame 或 None
    """
    start = time.time()
    
    while (time.time() - start) < max_wait:
        df = redis_util.load_dataframe_by_offset(table_name, offset=0, use_compression=False)
        
        if df is not None and not df.empty and 'time' in df.columns:
            data_time = df['time'].iloc[0]
            # 严格匹配债券时间
            if data_time == bond_time:
                return df
        
        time.sleep(RETRY_DELAY)
    
    return None


def monitor_zs(loop_start):
    """
    监控股债联动信号（串行执行，严格时间对齐）
    
    流程：
    1. 获取债券数据（快）
    2. 用债券时间精确匹配股票数据
    3. 严格验证时间一致性
    4. 处理关联逻辑
    """
    global _last_gp_time, _last_zq_time
    
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")
    zq_top30_table = f"monitor_zq_top30_{date_str}"
    gp_top30_table = f"monitor_gp_top30_{date_str}"
    
    # ========== 步骤1: 获取债券数据 ==========
    zq_df = fetch_bond_data(zq_top30_table, time_full)
    
    if zq_df is None or zq_df.empty:
        logger.debug(f"债券数据未就绪: {time_full}")
        return
    
    zq_time = zq_df['time'].iloc[0]
    
    # 去重检查：如果已经处理过这个时间，跳过
    if zq_time == _last_zq_time:
        logger.debug(f"债券数据已处理过: {zq_time}，跳过")
        return
    
    # ========== 步骤2: 用债券时间获取股票数据 ==========
    gp_df = fetch_stock_by_bond_time(gp_top30_table, zq_time)
    
    if gp_df is None or gp_df.empty:
        logger.info(f"股票数据未就绪: 期望时间={zq_time}，跳过")
        return
    
    gp_time = gp_df['time'].iloc[0]
    
    # ========== 步骤3: 严格时间对齐验证 ==========
    if gp_time != zq_time:
        logger.warning(f"时间不一致: 债券={zq_time}, 股票={gp_time}，跳过")
        return
    
    # ========== 步骤4: 更新已处理时间标记 ==========
    _last_gp_time = gp_time
    _last_zq_time = zq_time
    
    logger.info(f"数据对齐成功: time={zq_time}, 债券={len(zq_df)}条, 股票={len(gp_df)}条")
    
    # ========== 步骤5: 检查并加载股债映射数据 ==========
    global mid_df
    if mid_df is None or mid_df.empty:
        logger.warning("股债映射数据为空，尝试重新加载...")
        mid_df = redis_util.get_dict("data_bond_ths")
        if mid_df is None or mid_df.empty:
            logger.error("股债映射数据加载失败，跳过关联")
            return
        logger.info(f"股债映射数据重载成功: {len(mid_df)}条记录")
    
    # ========== 步骤6: 后续数据处理 ==========
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
    
    if result.empty:
        logger.debug("关联结果为空")
        return
    
    # 保存结果
    result['time'] = zq_time
    msac.save_dataframe(result, f"monitor_combine_{date_str}", zq_time, EXPIRE_SECONDS)
    
    logger.info(f"关联成功: 共 {len(result)} 条记录")
    
    # ========== 步骤6: WebSocket 实时推送（可选）==========
    if _websocket_available and not result.empty:
        try:
            # 取第一条记录发送通知
            first_record = result.iloc[0].to_dict()
            notify_new_signal(first_record)
        except Exception as e:
            logger.debug(f"WebSocket 通知失败: {e}")


if __name__ == "__main__":
    msac.run_monitor_loop_synced(monitor_zs, interval=INTERVAL)
