"""
实时监控获取债券数据——银河数据（极致性能优化版）
目标：500只债券 < 1秒
优化策略：
1. 程序启动时加载全量债券基础信息（数据库查询一次）
2. 20并发异步请求
3. 长连接复用
4. 向量化数据处理
"""

import asyncio
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import adata
import akshare as ak
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
import yinhedata as yh

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config('common.url')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.MysqlTool(url)

# ------------------------------
# 极致性能配置参数
# ------------------------------
INTERVAL = 3                    # 轮询间隔（秒）
EXPIRE_SECONDS = 64800          # 过期时间
WINDOW_SECONDS = 15

# 并发配置
CONCURRENT_LIMIT = 50           # 并发数
BATCH_SIZE = 8                 # 每批10只（银河API限制最多10只/次）
DB_CACHE_TTL = 3600             # 基础数据缓存1小时

# 超时配置
REQUEST_TIMEOUT = 5             # 单请求超时(秒)
TOTAL_TIMEOUT = 5               # 总超时(秒)

# ------------------------------
# 全局缓存（程序启动时初始化）
# ------------------------------
_bond_meta = {}                 # 债券基础信息 {code: {name, pre_close, open, high, low}}
_bond_codes = []                # 全量债券代码列表
_db_last_update = None          # 上次数据库更新时间
_executor = ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT)


def init_bond_meta():
    """
    程序启动时执行：加载全量债券基础信息
    查询 data_bond_daily 表，缓存到内存
    """
    global _bond_meta, _bond_codes, _db_last_update
    
    try:
        logger.info("开始加载债券基础信息...")
        start_time = time.time()
        
        # 从数据库加载所有债券的最新信息
        sql = """
        SELECT 
            b.bond_code,
            b.bond_code as bond_name,
            b.close as pre_close,
            b.open,
            b.high,
            b.low
        FROM data_bond_daily b
        INNER JOIN (
            SELECT bond_code, MAX(date) as max_date
            FROM data_bond_daily
            WHERE date < CURDATE()
            GROUP BY bond_code
        ) latest ON b.bond_code = latest.bond_code 
            AND b.date = latest.max_date
        """
        
        df = pd.read_sql(sql, engine)
        
        if df.empty:
            logger.warning("数据库中没有债券基础信息")
            return
        
        # 转换为字典缓存
        _bond_meta = df.set_index('bond_code').to_dict('index')
        _bond_codes = [f"SH.{code}" if code.startswith('11') else f"SZ.{code}" 
                       for code in _bond_meta.keys()]
        _db_last_update = datetime.now()
        
        elapsed = time.time() - start_time
        logger.info(f"加载债券基础信息完成: {len(_bond_meta)} 只，耗时 {elapsed:.2f}s")
        
    except Exception as e:
        logger.error(f"加载债券基础信息失败: {e}")
        _bond_meta = {}
        _bond_codes = []


def check_and_refresh_cache():
    """检查缓存是否过期，需要时刷新"""
    global _db_last_update
    
    if _db_last_update is None:
        init_bond_meta()
        return
    
    elapsed = (datetime.now() - _db_last_update).seconds
    if elapsed > DB_CACHE_TTL:
        logger.info(f"债券基础信息缓存过期({elapsed}s)，重新加载...")
        init_bond_meta()


async def fetch_batch(codes: list) -> pd.DataFrame:
    """
    异步获取一批债券数据
    在线程池中执行同步的 yh.realtime_kzz_data
    注意：yh.realtime_kzz_data 限制最多10只
    """
    if not codes:
        return pd.DataFrame()
    
    # 限制每批最多10只
    if len(codes) > 10:
        codes = codes[:10]
    
    loop = asyncio.get_event_loop()
    
    try:
        # 在线程池中执行同步API调用，带超时
        df = await asyncio.wait_for(
            loop.run_in_executor(_executor, yh.realtime_kzz_data, codes),
            timeout=REQUEST_TIMEOUT
        )
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except asyncio.TimeoutError:
        logger.warning(f"批次请求超时: {len(codes)} 只")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"批次请求异常: {e}")
        return pd.DataFrame()


async def fetch_all_realtime(max_bonds: int = None) -> pd.DataFrame:
    """
    并发获取所有债券实时数据
    20并发，每批10只（银河API限制）
    
    Args:
        max_bonds: 最多获取的债券数量，None表示全部
    """
    if not _bond_codes:
        logger.error("债券代码列表为空")
        return pd.DataFrame()
    
    # 如果指定了最大数量，只取前N只
    codes_to_fetch = _bond_codes[:max_bonds] if max_bonds else _bond_codes
    
    # 分批（每批10只）
    batches = [codes_to_fetch[i:i+BATCH_SIZE] for i in range(0, len(codes_to_fetch), BATCH_SIZE)]
    
    logger.info(f"开始并发获取数据: {len(codes_to_fetch)} 只，{len(batches)} 批次，{CONCURRENT_LIMIT} 并发")
    
    # 使用信号量限制并发数
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    
    async def fetch_with_limit(codes):
        async with semaphore:
            return await fetch_batch(codes)
    
    # 并发执行所有批次
    start_time = time.time()
    results = await asyncio.gather(
        *[fetch_with_limit(batch) for batch in batches],
        return_exceptions=True
    )
    elapsed = time.time() - start_time
    
    # 合并结果（过滤失败的批次）
    valid_dfs = []
    success_count = 0
    for r in results:
        if isinstance(r, pd.DataFrame) and not r.empty:
            valid_dfs.append(r)
            success_count += len(r)
    
    logger.info(f"数据获取完成: 成功 {success_count}/{len(codes_to_fetch)} 只，耗时 {elapsed:.2f}s")
    
    if not valid_dfs:
        return pd.DataFrame()
    
    # 一次性concat（避免多次拷贝）
    return pd.concat(valid_dfs, ignore_index=True, copy=False)


def process_data_fast(df_yinhe: pd.DataFrame) -> pd.DataFrame:
    """
    高性能数据处理
    使用numpy向量化操作，避免pandas逐行循环
    """
    if df_yinhe.empty:
        return pd.DataFrame()
    
    start_time = time.time()
    n = len(df_yinhe)
    
    # 提取原始数据为numpy数组（向量化）
    codes_raw = df_yinhe['代码'].values.astype(str)
    prices = df_yinhe['价格'].values.astype(np.float32)
    volumes = df_yinhe['成交量'].values.astype(np.float32)
    amounts = df_yinhe['成交额'].values.astype(np.float32)
    times = df_yinhe['时间'].values.astype(str)
    
    # 快速提取bond_code（向量化字符串处理）
    # SH.113034 -> 113034, SZ.123054 -> 123054
    bond_codes = np.char.replace(np.char.replace(codes_raw, 'SH.', ''), 'SZ.', '')
    
    # 批量查询基础信息（使用预缓存的字典）
    names = np.empty(n, dtype='U50')
    pre_closes = np.empty(n, dtype=np.float32)
    opens = np.empty(n, dtype=np.float32)
    highs = np.empty(n, dtype=np.float32)
    lows = np.empty(n, dtype=np.float32)
    
    for i, code in enumerate(bond_codes):
        meta = _bond_meta.get(code, {})
        names[i] = meta.get('bond_name', '')
        pre_closes[i] = meta.get('pre_close', 0.0)
        opens[i] = meta.get('open', 0.0)
        highs[i] = meta.get('high', 0.0)
        lows[i] = meta.get('low', 0.0)
    
    # 向量化计算涨跌幅
    changes = prices - pre_closes
    change_pcts = np.where(
        pre_closes > 0,
        (changes / pre_closes * 100),
        0.0
    )
    
    # 一次性构造DataFrame（避免多次内存分配）
    result = pd.DataFrame({
        'bond_code': bond_codes,
        'bond_name': names,
        'price': prices,
        'open': opens,
        'high': highs,
        'low': lows,
        'pre_close': pre_closes,
        'change': changes,
        'change_pct': np.round(change_pcts, 2),
        'volume': volumes,
        'amount': amounts,
        'time': times,
    })
    
    # 过滤价格范围（向量化）
    mask = (result['price'] > 110) & (result['price'] < 250)
    result = result[mask].reset_index(drop=True)
    
    elapsed = time.time() - start_time
    logger.debug(f"数据处理完成: {len(result)} 只，耗时 {elapsed*1000:.1f}ms")
    
    return result


def get_bond_yinhe(max_bonds: int = 100, fallback_to_adata: bool = True) -> pd.DataFrame:
    """
    优化后的银河债券数据获取（极致性能版）
    
    性能目标：
    - 100只债券 < 1秒（默认）
    - 数据库查询：启动时一次
    - 并发：20并发异步请求
    - 数据处理：向量化
    
    Args:
        max_bonds: 最多获取的债券数量，默认100只（保证1秒内完成）
                 设为 None 获取全部（可能超过1秒）
        fallback_to_adata: 当银河数据失败时是否使用 adata 作为备选
    
    Returns:
        DataFrame: 与 get_bond_adata() 同构的数据
    """
    total_start = time.time()
    
    # 1. 检查并刷新缓存
    check_and_refresh_cache()
    
    if not _bond_codes:
        logger.error("债券代码列表为空，无法获取数据")
        if fallback_to_adata:
            logger.info("使用 adata 作为备选数据源")
            return get_bond_adata()
        return pd.DataFrame()
    
    # 2. 并发获取实时数据
    try:
        df_yinhe = asyncio.run(fetch_all_realtime(max_bonds=max_bonds))
    except Exception as e:
        logger.error(f"获取实时数据失败: {e}")
        df_yinhe = pd.DataFrame()
    
    if df_yinhe.empty:
        logger.warning("获取到的实时数据为空")
        if fallback_to_adata:
            logger.info("使用 adata 作为备选数据源")
            return get_bond_adata()
        return pd.DataFrame()
    
    # 3. 高性能数据处理
    result = process_data_fast(df_yinhe)
    
    total_elapsed = time.time() - total_start
    logger.info(f"get_bond_yinhe 完成: {len(result)} 只，总耗时 {total_elapsed*1000:.1f}ms")
    
    return result


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
        'yinhe': get_bond_yinhe
    }

    func = handlers.get(data_source)
    if func is not None:
        return func()

    logger.warning(f"未知的数据源 '{data_source}'，返回空 DataFrame。")
    return pd.DataFrame()


def deal_zq_works(loop_start):
    """
    处理债券数据工作流
    获取债券实时数据，格式化后存储到 Redis，并加载历史窗口数据用于分析。
    """
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        df_now = get_bond('yinhe')
        if df_now.empty:
            logger.info(f"获取债券数据为空: {date_str} {time_full}")
            return
    except ConnectionError as e:
        logger.error(f"网络连接异常: {e}")
        time.sleep(60)
        return
    except ValueError as e:
        logger.error(f"数据格式错误: {e}")
        return
    except KeyError as e:
        logger.error(f"数据缺少必要列: {e}")
        return
    except Exception as e:
        logger.error(f"获取债券数据异常: {e}", exc_info=True)
        time.sleep(60)
        return

    # 存储债券实时数据
    sssj_table = f"test_yinhe_monitor_zq_sssj_{date_str}"
    msac.save_dataframe(df_now, sssj_table, time_full, EXPIRE_SECONDS)
    logger.info(f"债券数据已保存: {date_str} {time_full}, {len(df_now)} 只")


# 程序启动时初始化
logger.info("=" * 50)
logger.info("债券监控模块初始化...")
init_bond_meta()
logger.info("=" * 50)


if __name__ == "__main__":
    msac.run_monitor_loop_synced(deal_zq_works, interval=INTERVAL)
