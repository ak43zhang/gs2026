import math
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path

import adata
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import log_util, pandas_display_config,config_util,mysql_util,redis_util,string_enum

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config("common.url")
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接（关闭自动解码，以支持压缩）
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)

# ------------------------------
# 配置参数
BATCH_SIZE = 400          # 每批股票数量
MAX_WORKERS = 13           # 并发线程数（可根据需要调整）
INTERVAL = 3              # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
MAX_SAVE_TIMESTAMPS = 10000
WINDOW_SECONDS = 15

# 从数据库加载股票代码列表
sql = string_enum.AG_STOCK_SQL5
code_df = pd.read_sql(sql, con=con)
code_list = code_df.values.tolist()
STOCK_CODES = [x[0] for x in code_list]   # 例如 ['600000', '000001', ...]

STOCK_COLUMNS = ['code', 'name', 'zf_30', 'momentum', 'volume_change_rate', 'amount_now',
                   'zf_30_rank','momentum_rank','amount_rank','total_score_rank',
                   'zf_30_pct_rank', 'momentum_pct_rank', 'amount_pct_rank', 'volume_change_pct_rank',
                   'total_score','change_pct','change_pct_zq', 'rq', 'time']

def calculate_top30_v3(df_now: pd.DataFrame, df_prev: pd.DataFrame, dt: datetime, weights: dict = None) -> pd.DataFrame:
    """
    增强版：计算指定秒数内涨幅与量价动能，采用多因子加权综合评分，返回前30只最具上攻潜力的股票。

    算法升级点：
        - 动态价格区间（根据股票代码前缀区分主板/创业板/科创板/可转债）
        - 多因子加权（涨幅、动能、成交额、可选成交量变化率），百分位数排名后加权
        - 对极端值进行缩尾处理（1%）
        - 增强数据清洗（检查当前时刻数据）
        - 支持窗口时间调整（适应A股/可转债不同噪声水平）
        - 处理空数据及排名并列

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 前一时刻（当前时刻 - window_seconds）数据。
        dt (datetime): 当前时刻，用于生成日期时间。
        weights (dict): 各因子权重，格式：
            {'zf_30': 0.3, 'momentum': 0.4, 'amount': 0.2, 'volume_change_rate': 0.1}
            若为None则使用默认权重（涨幅30%，动能40%，成交额30%，成交量变化率0%）。

    Returns:
        pd.DataFrame: 包含以下列，按 total_score 升序排列，最多30行。
            - code: 股票代码
            - name: 股票简称
            - zf_30: 窗口涨幅（%）
            - momentum: 动能指标（涨幅 × 成交额变化率 × 10000）
            - volume_change_rate: 成交量变化率（当前成交量 / 前一成交量 - 1）
            - amount_now: 当前成交额
            - zf_30_pct_rank: 涨幅百分位数排名（0~1，越大越好）
            - momentum_pct_rank: 动能百分位数排名
            - amount_pct_rank: 成交额百分位数排名
            - volume_change_pct_rank: 成交量变化率百分位数排名（若权重为0则不输出）
            - total_score: 综合得分（加权百分位数排名之和，值越小排名越前）
            - rq: 日期 YYYYMMDD
            - time: 时间 HH:MM:SS
    """
    # 默认权重（涨幅30%，动能40%，成交额30%，成交量变化率0%）
    if weights is None:
        weights = {'zf_30': 0.5, 'momentum': 0.5, 'amount': 0.0, 'volume_change_rate': 0.0}
    # 确保权重和为1
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "权重之和必须为1"

    # 复制避免修改原始数据
    df_now = df_now.copy()
    df_prev = df_prev.copy()

    # 统一股票代码为6位字符串
    df_now['code'] = df_now['code'].astype(str).str.zfill(6)
    df_prev['code'] = df_prev['code'].astype(str).str.zfill(6)

    df_now = df_now.drop_duplicates(subset=['code'], keep='first')
    df_prev = df_prev.drop_duplicates(subset=['code'], keep='first')

    # 将核心列转换为数值，无法转换的设为NaN
    num_cols = ['price', 'volume', 'amount', 'change_pct']
    for col in num_cols:
        df_now[col] = pd.to_numeric(df_now[col], errors='coerce')
        df_prev[col] = pd.to_numeric(df_prev[col], errors='coerce')

    # 增强清洗：删除当前时刻价格、成交量、成交额为NaN或<=0的行
    df_now = df_now[(df_now['price'] > 0) & (df_now['volume'] > 0) & (df_now['amount'] > 0)]
    df_prev = df_prev[(df_prev['price'] > 0) & (df_prev['volume'] > 0) & (df_prev['amount'] > 0)]

    # 合并两个时刻数据（内连接）
    merged = pd.merge(
        df_now[['code', 'name', 'price', 'volume', 'amount', 'change_pct']],
        df_prev[['code', 'price', 'volume', 'amount', 'change_pct']],
        on='code',
        suffixes=(f'_now', f'_prev'),
        how='inner',
        validate='1:1'  # 假设股票代码唯一
    )
    if merged.empty:
        # 空数据返回空DataFrame（保持列结构）
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- 动态价格区间 ----------
    # 根据股票代码前缀设置价格上下限（可自定义扩展）
    def get_price_bounds(code_series):
        bounds = []
        for code in code_series:
            if code.startswith(('600','601','603','605','000','001','002')):
                bounds.append((3, 100))      # 主板
            elif code.startswith('300'):
                bounds.append((5, 200))       # 创业板
            elif code.startswith('688'):
                bounds.append((10, 500))       # 科创板
            elif code.startswith(('11','12','123','127')):  # 可转债代码常见前缀
                bounds.append((110, 250))      # 可转债价格范围较宽
            else:
                bounds.append((1, 1000))       # 其他（北交所等）
        return bounds

    price_bounds = get_price_bounds(merged['code'])
    merged['price_min'] = [b[0] for b in price_bounds]
    merged['price_max'] = [b[1] for b in price_bounds]

    # 过滤价格区间：前一时刻价格必须在对应区间内
    merged = merged[
        (merged['price_prev'] >= merged['price_min']) &
        (merged['price_prev'] <= merged['price_max'])
    ].copy()
    merged.drop(columns=['price_min', 'price_max'], inplace=True)

    if merged.empty:
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- ST股票剔除 ----------
    pattern = re.compile(r'ST|\*ST|退', flags=re.IGNORECASE)
    merged = merged[~merged['name'].str.contains(pattern, na=False)]

    if merged.empty:
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- 计算指标 ----------
    # 窗口涨幅（百分比）
    merged['zf_30'] = ((merged['price_now'] - merged['price_prev']) / merged['price_prev'] * 100).round(2)

    # 成交额变化率（带缩尾保护）
    amount_prev_abs = merged['amount_prev'].abs()
    merged['amount_change_rate'] = ((merged['amount_now'] - merged['amount_prev']) / (amount_prev_abs + 1e-6)).round(2)
    # 成交量变化率
    merged['volume_change_rate'] = ((merged['volume_now'] - merged['volume_prev']) / (merged['volume_prev'].abs() + 1e-6)).round(2)

    # 对变化率进行缩尾（1%和99%分位数）
    # for col in ['amount_change_rate', 'volume_change_rate']:
    #     lower = merged[col].quantile(0.01)
    #     upper = merged[col].quantile(0.99)
    #     merged[col] = merged[col].astype(float).clip(lower, upper)

    # 动能指标 = 涨幅 × 成交额变化率 × 10000
    merged['momentum'] = (merged['zf_30'] * merged['amount_change_rate'] * 10000).round(2)

    # 当前成交额（便于输出）
    # merged['amount_now'] = merged['amount_now']
    # merged['change_pct_now'] = merged['amount_now']

    # ---------- 对核心因子进行缩尾 ----------
    # for col in ['zf_30', 'momentum', 'amount_now', 'volume_change_rate']:
    #     lower = merged[col].quantile(0.01)
    #     upper = merged[col].quantile(0.99)
    #     merged[col] = merged[col].astype(float).clip(lower, upper)

    # ---------- 计算百分位数排名（越大越好） ----------
    merged['zf_30_rank'] = merged['zf_30'].rank(method='min', ascending=False)
    merged['momentum_rank'] = merged['momentum'].rank(method='min', ascending=False)
    merged['amount_rank'] = merged['amount_now'].rank(method='min', ascending=False)
    merged['zf_30_pct_rank'] = (merged['zf_30'].rank(method='min', pct=True)).round(2)          # 0~1
    merged['momentum_pct_rank'] = (merged['momentum'].rank(method='min', pct=True)).round(2)
    merged['amount_pct_rank'] = (merged['amount_now'].rank(method='min', pct=True)).round(2)
    merged['volume_change_pct_rank'] = (merged['volume_change_rate'].rank(method='min', pct=True)).round(2)


    # ---------- 加权综合得分（值越小越好，即排名越靠前） ----------
    # 由于百分位数是越大越好，我们将其转换为越小越好：1 - pct_rank，然后加权求和
    merged['total_score'] = (
        weights['zf_30'] * (1 - merged['zf_30_pct_rank']) +
        weights['momentum'] * (1 - merged['momentum_pct_rank']) +
        weights['amount'] * (1 - merged['amount_pct_rank']) +
        weights['volume_change_rate'] * (1 - merged['volume_change_pct_rank'])
    ).round(4)

    merged['total_score_rank'] = merged['total_score'].rank(method='min', ascending=True).round(3)

    # ---------- 添加日期时间 ----------
    merged['rq'] = dt.strftime('%Y%m%d')
    merged['time'] = dt.strftime('%H:%M:%S')

    # ---------- 排序与取前30（处理并列） ----------
    # 按 total_score 升序，若相同则按 momentum 降序（认为动能强者优先）
    top_k = math.ceil(len(merged) * 0.05)
    final_df = merged.sort_values(['total_score', 'momentum'], ascending=[True, False]).head(top_k)


    # 选择并排列输出列
    # output_cols = ['code', 'name', 'zf_30', 'momentum', 'volume_change_rate', 'amount_now',
    #                'zf_30_rank','momentum_rank','amount_rank',
    #                'zf_30_pct_rank', 'momentum_pct_rank', 'amount_pct_rank', 'volume_change_pct_rank',
    #                'total_score', 'rq', 'time']
    # 若成交量变化率权重为0，可选择性不输出该列（为保持统一，仍输出但值可能无意义）
    # final_df = final_df[STOCK_COLUMNS].reset_index(drop=True)

    return final_df

def calculate_top30_v2(df_now: pd.DataFrame, df_prev: pd.DataFrame, dt: datetime,
                       stock_code, short_name, price, volume, amount) -> pd.DataFrame:
    """
    计算30秒内涨幅与动能指标，返回综合排名前30的股票信息。

    算法步骤：
        1. 合并当前时刻（df_now）与30秒前时刻（df_prev）的数据，仅保留共有的股票。
        2. 根据 `stock_code` 参数值动态设置价格筛选区间：
           - 若 `stock_code == 'stock_code'`，价格区间为 [3, 100]
           - 否则价格区间为 [120, 250]
        3. 剔除价格、成交量、成交额为 NaN 或 0 的行，并过滤不在价格区间内的股票。
        4. 剔除名称包含 ST、*ST、退 等字样（不区分大小写）的股票。
        5. 计算指标：
           - `zf_30`：30秒涨幅（百分比）
           - `amount_diff`：成交额差值（当前 - 30秒前）
           - `amount_change_rate`：成交额变化率 = amount_diff / |prev_amount|
           - `momentum`：动能 = zf_30 * amount_change_rate * 10000
        6. 分别取涨幅、动能、当前成交额排名前10%的股票代码（向上取整），取三者交集。
        7. 在交集内计算倒序排名（值越大名次越前，使用 `method='min'`）：
           - `zf_30_rank`、`momentum_rank`、`amount_rank`
        8. 计算综合得分 `all_score = zf_30_rank + momentum_rank`，取得分最小的30只股票。

    Args:
        df_now (pd.DataFrame): 当前时刻的股票数据，必须包含参数中指定的列。
        df_prev (pd.DataFrame): 30秒前的股票数据，列名与 df_now 一致。
        dt (datetime): 当前时刻，用于生成日期（rq）和时间（time）字段。
        stock_code (str): 股票代码的列名（如 'stock_code'）。
        short_name (str): 股票简称的列名（如 'short_name'）。
        price (str): 价格列名（如 'price'）。
        volume (str): 成交量列名（如 'volume'，当日累计量）。
        amount (str): 成交额列名（如 'amount'）。

    Returns:
        pd.DataFrame: 包含以下列的 DataFrame，按 all_score 升序排列（值越小排名越前），
                      最多返回 30 行，若交集不足 30 则返回全部交集。
            - code: 股票代码（str，6位数字，前导补零）
            - name: 股票简称
            - zf_30: 30秒涨幅（百分比，保留两位小数）
            - zf_30_rank: 在交集内的涨幅倒序排名（1 为最高）
            - momentum: 动能指标（可能为负数）
            - momentum_rank: 在交集内的动能倒序排名
            - amount_rank: 在交集内的当前成交额倒序排名
            - all_score: 综合得分 = zf_30_rank + momentum_rank
            - rq: 日期（格式 YYYYMMDD）
            - time: 时间（格式 HH:MM:SS）
    """
    # 复制DataFrame以避免修改原始数据
    df_now = df_now.copy()
    df_prev = df_prev.copy()

    # 统一合并键（股票代码）类型为字符串
    df_now[stock_code] = df_now[stock_code].astype(str).str.zfill(6)
    df_prev[stock_code] = df_prev[stock_code].astype(str).str.zfill(6)

    # 将价格、成交量和成交额列转换为数值类型，无法转换的设为NaN
    df_now[price] = pd.to_numeric(df_now[price], errors='coerce')
    df_prev[price] = pd.to_numeric(df_prev[price], errors='coerce')
    df_now[volume] = pd.to_numeric(df_now[volume], errors='coerce')
    df_prev[volume] = pd.to_numeric(df_prev[volume], errors='coerce')
    df_now[amount] = pd.to_numeric(df_now[amount], errors='coerce')
    df_prev[amount] = pd.to_numeric(df_prev[amount], errors='coerce')

    # 删除价格、成交量或成交额为NaN的行
    df_now = df_now.dropna(subset=[price, volume, amount])
    df_prev = df_prev.dropna(subset=[price, volume, amount])

    # 合并两个时刻的数据（内连接，只保留共同股票）
    merged = pd.merge(
        df_now[[stock_code, short_name, price, volume, amount]],
        df_prev[[stock_code, price, volume, amount]],
        on=stock_code,
        suffixes=('_now', '_prev'),
        how='inner'
    )

    # 根据股票代码列名设置价格区间（保留原有逻辑）
    if stock_code == 'stock_code':
        price_min, price_max = 3, 100
    else:
        price_min, price_max = 110, 250

    # 过滤无效数据及价格范围
    merged = merged[
        (merged[f'{price}_prev'] != 0) & merged[f'{price}_prev'].notna()
        & (merged[f'{volume}_prev'] != 0) & merged[f'{volume}_prev'].notna()
        & (merged[f'{amount}_prev'] != 0) & merged[f'{amount}_prev'].notna()
        & (merged[f'{price}_prev'] >= price_min) & (merged[f'{price}_prev'] <= price_max)
    ].copy()

    # 计算30秒涨幅（百分比）
    merged['zf_30'] = ((merged[f'{price}_now'] - merged[f'{price}_prev']) / merged[f'{price}_prev'] * 100).round(2)

    # 计算30秒成交额变化（差值）和成交额变化率
    merged['amount_diff'] = merged[f'{amount}_now'] - merged[f'{amount}_prev']
    merged['amount_change_rate'] = (merged['amount_diff'] / (merged[f'{amount}_prev'].abs() + 1e-6)).round(2)

    # 计算动能指标：涨幅 × 成交额变化率，放大10000便于观察
    merged['momentum'] = (merged['zf_30'] * merged['amount_change_rate'] * 10000).round(2)

    # 剔除ST股票
    pattern = r'ST|\*ST|退|st|\*st'
    merged = merged[~merged[short_name].str.contains(pattern, na=False, case=True)]

    # 获取涨幅前N和动能前N的股票代码,成交总额前N
    total_rows = len(merged)
    top_k = math.ceil(total_rows * 0.2)  # 前 10% 的行数，向上取整确保至少一行
    gain_codes = merged.nlargest(top_k, 'zf_30')[stock_code].tolist()
    momentum_codes = merged.nlargest(top_k, 'momentum')[stock_code].tolist()
    amount_codes = merged.nlargest(top_k, f'{amount}_now')[stock_code].tolist()

    # 取交集
    union_codes = set(gain_codes) & set(momentum_codes)   # & set(amount_codes)

    # 从merged中提取这些股票的完整记录
    result_df = merged[merged[stock_code].isin(union_codes)].copy()

    # 添加日期和时间字段
    result_df['rq'] = dt.strftime('%Y%m%d')
    result_df['time'] = dt.strftime('%H:%M:%S')

    # 在并集内部计算倒序排名
    # 先计算正序排名（值越大排名越小，即最大值排名为1）
    result_df['zf_30_rank'] = result_df['zf_30'].rank(method='min', ascending=False)
    result_df['momentum_rank'] = result_df['momentum'].rank(method='min', ascending=False)
    result_df['amount_rank'] = result_df[f'{amount}_now'].rank(method='min', ascending=False)

    # 计算综合得分
    result_df['all_score'] = result_df['zf_30_rank'] + result_df['momentum_rank']

    # 重命名股票代码和名称列
    result_df = result_df.rename(columns={stock_code: 'code', short_name: 'name'})

    # 按all_score降序排序取前N，并选择所需字段
    final_df = result_df.nsmallest(30, 'all_score')[
        ['code', 'name', 'zf_30', 'zf_30_rank', 'momentum', 'momentum_rank', 'rq', 'time', 'amount_rank', 'all_score']
    ].reset_index(drop=True)

    return final_df


def save_dataframe(df: pd.DataFrame, table_name: str, time_full: str,
                   expire_seconds: int, use_compression: bool = False) -> None:
    """
    统一保存 DataFrame 到 MySQL 和 Redis。

    Args:
        df (pd.DataFrame): 要存储的 DataFrame。
        table_name (str): 表名（MySQL 表名，也是 Redis 键前缀）。
        time_full (str): 时间点字符串，如 '15:00:00'。
        expire_seconds (int): Redis 数据过期时间（秒）。
        use_compression (bool): 是否对 Redis 数据启用压缩（默认 False）。
    """
    # 1. 写入 MySQL
    try:
        df.to_sql(table_name, con=engine, if_exists='append', index=False, method='multi')
        print(f"已写入 MySQL 表 {table_name}，共 {len(df)} 条记录")
    except Exception as e:
        print(f"MySQL 写入失败: {e}")

    # 2. 写入 Redis
    redis_util.save_dataframe_to_redis(df, table_name, time_full, expire_seconds, use_compression)


def batch_codes(codes, batch_size):
    """
    将代码列表分批，每批最多 batch_size 个。

    Args:
        codes (list): 股票代码列表。
        batch_size (int): 每批最大数量。

    Returns:
        list of list: 分批后的代码列表。
    """
    return [codes[i:i + batch_size] for i in range(0, len(codes), batch_size)]


def fetch_batch(batch):
    """
    调用API获取单批数据，返回DataFrame。

    Args:
        batch (list): 一批股票代码。

    Returns:
        pd.DataFrame: 获取的数据，如果失败则返回空 DataFrame。
    """
    try:
        # 假设list_market_current返回DataFrame或可转为DataFrame的结构
        df = adata.stock.market.list_market_current(batch)
        return df
    except Exception as e:
        print(f"批次 {batch[:5]}... 请求失败: {e}")
        return pd.DataFrame()  # 返回空DataFrame避免中断


def fetch_all_concurrently(codes):
    """
    并发获取所有代码的数据，合并后返回一个DataFrame。

    Args:
        codes (list): 所有股票代码列表。

    Returns:
        pd.DataFrame: 合并后的数据，如果没有任何数据则返回空 DataFrame。
    """
    batches = batch_codes(codes, BATCH_SIZE)
    all_data = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_batch = {executor.submit(fetch_batch, batch): batch for batch in batches}

        for future in as_completed(future_to_batch):
            df = future.result()
            if not df.empty:
                all_data.append(df)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    else:
        return pd.DataFrame()


def write_to_mysql(df, table_name):
    """
    将DataFrame写入MySQL表（使用 engine.begin 自动提交事务）。

    Args:
        df (pd.DataFrame): 要写入的数据。
        table_name (str): 目标表名。
    """
    if df is None or df.empty:
        logger.error("数据为空，跳过写入")
    else:
        with engine.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            print(f"已写入 {len(df)} 行到表 {table_name}")


def is_trading_time(dt):
    """
    判断给定时间是否在A股交易时段内（周一至周五，9:30-11:30 和 13:00-15:00）。

    Args:
        dt (datetime): 待判断的时间。

    Returns:
        bool: True 如果在交易时段内，否则 False。
    """
    if dt.weekday() >= 5:  # 周六、周日
        return False
    t = dt.time()
    # 上午交易时段
    if dt_time(9, 25) <= t <= dt_time(11, 30):
        return True
    # 下午交易时段
    if dt_time(13, 0) <= t <= dt_time(15, 0):
        return True
    return False


def next_trading_start(dt):
    """
    计算下一个交易开始时间（从当前时间之后最近的交易时段起点）。

    Args:
        dt (datetime): 当前时间。

    Returns:
        datetime: 下一个交易开始时间点。
    """
    # 如果当前在交易时段内，理论上不应调用此函数，但为安全返回当前
    if is_trading_time(dt):
        return dt

    # 定义交易时段边界
    morning_start = dt_time(9, 25)
    morning_end = dt_time(11, 30)
    afternoon_start = dt_time(13, 0)
    afternoon_end = dt_time(15, 0)

    current_date = dt.date()
    current_time = dt.time()

    # 情况1：当前时间在上午开始之前（即9:30之前）
    if current_time < morning_start:
        candidate = datetime.combine(current_date, morning_start)
        # 如果当天是周末，需要跳到下周一
        if candidate.weekday() >= 5:
            days_to_monday = (7 - candidate.weekday()) % 7
            candidate += timedelta(days=days_to_monday)
        return candidate

    # 情况2：当前时间在上午交易时段内（正常情况下不会进入此分支，但保留）
    if morning_start <= current_time <= morning_end:
        return dt

    # 情况3：当前时间在上午结束后、下午开始前（11:30 - 13:00）
    if morning_end < current_time < afternoon_start:
        candidate = datetime.combine(current_date, afternoon_start)
        # 下午开始时间不可能落在周末，因为上午交易时段已排除周末
        return candidate

    # 情况4：当前时间在下午交易时段内（正常情况下不会进入）
    if afternoon_start <= current_time <= afternoon_end:
        return dt

    # 情况5：当前时间在下午结束后（15:00之后）
    # 下一个交易开始是下一个工作日的9:30
    next_day = current_date + timedelta(days=1)
    candidate = datetime.combine(next_day, morning_start)
    # 如果下一天是周末，继续向后找周一
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def is_past_1500(dt):
    """
    判断给定时间是否超过当天的15:00。

    Args:
        dt (datetime): 待判断的时间。

    Returns:
        bool: True 如果 dt > 当天15:00，否则 False。
    """
    return dt > datetime.combine(dt.date(), dt_time(15, 0))


def get_market_stats(df_now: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    计算当前时刻的涨跌统计以及与前一分钟相比的涨跌统计，合并为宽表返回。
    返回结果中包含 time 字段，取自 df_now 的 time 列。
    所有比率列已转换为 float 类型，保证后续数值比较的稳定性。

    Args:
        df_now (pd.DataFrame): 当前时刻的数据，必须包含 'time'、code 和 change_pct 列。
        df_prev (pd.DataFrame): 前一分钟的数据，必须包含 code 和 change_pct 列（可为空）。

    Returns:
        pd.DataFrame: 单行宽表，包含当前统计、分钟统计和 time 字段。
                      各统计字段说明见代码内部。

    Raises:
        ValueError: 如果必要列缺失或 df_prev 非空但缺少必要列。
    """
    # ---------- 0. 提取时间 ----------
    if 'time' not in df_now.columns:
        raise ValueError("df_now 必须包含 'time' 列")
    time_value = df_now['time'].iloc[0]

    # ---------- 1. 确保 change_pct 列为数值类型 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        raise ValueError(f"df_now 必须包含 'code' 和 'change_pct' 列")

    # 转换 change_pct 为数值，无法转换的变为 NaN
    df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')
    # 丢弃 change_pct 为 NaN 的行，仅保留有效数据
    df_now = df_now.dropna(subset=['change_pct'])

    # 对 df_prev 做相同处理（如果存在且非空）
    if df_prev is not None and not df_prev.empty:
        if not all(col in df_prev.columns for col in required_cols):
            raise ValueError(f"df_prev 必须包含 'code' 和 'change_pct' 列")
        df_prev['change_pct'] = pd.to_numeric(df_prev['change_pct'], errors='coerce')
        df_prev = df_prev.dropna(subset=['change_pct'])

    # ---------- 2. 当前统计 ----------
    total_cur = len(df_now)
    if total_cur == 0:
        cur_up = cur_down = cur_flat = 0
        cur_up_ratio = cur_down_ratio = cur_flat_ratio = 0.0
        cur_up_down_ratio = np.nan
    else:
        cur_up = (df_now['change_pct'] > 0).sum()
        cur_down = (df_now['change_pct'] < 0).sum()
        cur_flat = (df_now['change_pct'].eq(0)).sum()
        cur_up_ratio = round(cur_up / total_cur * 100, 2)
        cur_down_ratio = round(cur_down / total_cur * 100, 2)
        cur_flat_ratio = round(cur_flat / total_cur * 100, 2)
        if cur_down == 0:
            cur_up_down_ratio = None
        else:
            cur_up_down_ratio = round(cur_up / cur_down * 100, 2)

    # ---------- 3. 分钟统计 ----------
    if df_prev is None or df_prev.empty:
        min_up = min_down = min_flat = min_total = 0
        min_up_ratio = min_down_ratio = min_flat_ratio = 0.0
        min_up_down_ratio = np.nan
    else:
        # 统一 stock_code 为字符串类型（避免合并时类型冲突）
        df_now['code'] = df_now['code'].astype(str)
        if df_prev is not None and not df_prev.empty:
            df_prev['code'] = df_prev['code'].astype(str)

        # 然后进行合并
        merged = pd.merge(
            df_now[['code', 'change_pct']],
            df_prev[['code', 'change_pct']],
            on='code',
            suffixes=('_cur', '_prev'),
            how='inner'
        )

        min_total = len(merged)
        if min_total == 0:
            min_up = min_down = min_flat = 0
            min_up_ratio = min_down_ratio = min_flat_ratio = 0.0
            min_up_down_ratio = np.nan
        else:
            diff = merged['change_pct_cur'] - merged['change_pct_prev']
            min_up = (diff > 0).sum()
            min_down = (diff < 0).sum()
            min_flat = (diff.eq(0)).sum()
            min_up_ratio = round(min_up / min_total * 100, 2)
            min_down_ratio = round(min_down / min_total * 100, 2)
            min_flat_ratio = round(min_flat / min_total * 100, 2)
            if min_down == 0:
                min_up_down_ratio = None
            else:
                min_up_down_ratio = round(min_up / min_down * 100, 2)

    # ---------- 4. 合并为宽表（包含 time）----------
    result = pd.DataFrame([{
        'time': time_value,
        'cur_up': cur_up,
        'cur_down': cur_down,
        'cur_flat': cur_flat,
        'cur_total': total_cur,
        'cur_up_ratio': cur_up_ratio,
        'cur_down_ratio': cur_down_ratio,
        'cur_flat_ratio': cur_flat_ratio,
        'cur_up_down_ratio': cur_up_down_ratio,
        'min_up': min_up,
        'min_down': min_down,
        'min_flat': min_flat,
        'min_total': min_total,
        'min_up_ratio': min_up_ratio,
        'min_down_ratio': min_down_ratio,
        'min_flat_ratio': min_flat_ratio,
        'min_up_down_ratio': min_up_down_ratio
    }])

    # ---------- 5. 强制将比率列转换为 float（避免后续字符串比较错误）----------
    ratio_cols = [
        'cur_up_ratio', 'cur_down_ratio', 'cur_flat_ratio', 'cur_up_down_ratio',
        'min_up_ratio', 'min_down_ratio', 'min_flat_ratio', 'min_up_down_ratio'
    ]
    result[ratio_cols] = result[ratio_cols].astype(float)

    return result


def judge_market_strength(stats_row):
    """
    基于 get_market_stats 返回的一行数据，多维度判断市场强弱及转换信号。
    返回结果为单行宽表，包含原始统计字段及新增的判断字段。

    Args:
        stats_row (pd.Series 或 pd.DataFrame): get_market_stats 返回的一行数据，
                                                如果是 DataFrame 必须只有一行。

    Returns:
        pd.DataFrame: 单行宽表，包含原始统计字段以及新增的：
                      strength_score, state, signal, base_score, trend_score。

    Raises:
        ValueError: 如果 stats_row 包含多行数据。
    """
    # 确保输入为 Series
    if isinstance(stats_row, pd.DataFrame):
        if len(stats_row) > 1:
            raise ValueError("stats_row 只能包含一行数据，请使用 .iloc[0] 传入 Series")
        stats_row = stats_row.iloc[0]

    # ---------- 强制转换为浮点数（避免字符串与数字比较错误）----------
    # 将需要用到的指标全部转为 float（np.inf / np.nan 也能正确处理）
    cur_up_ratio = float(stats_row['cur_up_ratio'])
    cur_down_ratio = float(stats_row['cur_down_ratio'])
    cur_up_down_ratio = float(stats_row['cur_up_down_ratio'])
    min_up_ratio = float(stats_row['min_up_ratio'])
    min_down_ratio = float(stats_row['min_down_ratio'])
    min_up_down_ratio = float(stats_row['min_up_down_ratio'])
    min_up = float(stats_row['min_up'])
    min_down = float(stats_row['min_down'])
    cur_total = float(stats_row['cur_total'])

    # --- 1. 当前强度基础评分（0-100）---
    base_score = cur_up_ratio

    # 涨跌比修正
    if not pd.isna(cur_up_down_ratio) and cur_up_down_ratio is not None:
        if cur_up_down_ratio > 200:
            base_score += min(cur_up_down_ratio - 200, 200) * 0.1
        elif cur_up_down_ratio < 50:
            base_score -= (50 - cur_up_down_ratio) * 0.2
    elif cur_up_down_ratio is None:
        base_score += 20

    base_score = max(0.0, min(100.0, base_score))

    # --- 2. 趋势修正（基于分钟变化）---
    trend_score = (min_up_ratio - 50) * 0.8
    trend_score = max(-20.0, min(20.0, trend_score))

    strength_score = base_score + trend_score
    strength_score = max(0.0, min(100.0, strength_score))

    # --- 3. 市场状态划分 ---
    if strength_score >= 80:
        state = "极强"
    elif strength_score >= 60:
        state = "强"
    elif strength_score <= 20:
        state = "极弱"
    elif strength_score <= 40:
        state = "弱"
    else:
        state = "温和"

    # --- 4. 转换信号识别 ---
    signal = "无"
    if cur_up_ratio <= 40 and min_up_ratio > 55 and min_up > min_down:
        signal = "弱转强"
    elif cur_up_ratio >= 60 and min_down_ratio > 55 and min_down > min_up:
        signal = "强转弱"
    else:
        if cur_up_ratio <= 40 and not pd.isna(min_up_down_ratio) and min_up_down_ratio > 200:
            signal = "弱转强（潜在）"
        elif cur_up_ratio >= 60 and not pd.isna(min_up_down_ratio) and min_up_down_ratio < 50:
            signal = "强转弱（潜在）"

    # --- 5. 构造结果 DataFrame：合并原始统计字段与新增字段 ---
    original_dict = stats_row.to_dict()
    original_dict.update({
        'strength_score': round(strength_score, 2),
        'state': state,
        'signal': signal,
        'base_score': round(base_score, 2),
        'trend_score': round(trend_score, 2)
    })
    result_df = pd.DataFrame([original_dict])
    return result_df
# 源字段
SOURCE_STOCK_FULL_COLUMNS = ['stock_code', 'short_name', 'price','change','change_pct', 'volume', 'amount']
# 统一后字段 'code', 'name', 'price','change','change_pct', 'volume', 'amount'

def deal_gp_works(loop_start):
    """
    单个轮询周期的主处理函数：获取股票数据、存储实时数据、计算前30秒指标及大盘强度。

    Args:
        loop_start (datetime): 当前轮询开始时间。
    """
    # 添加时间字段（HH:MM:SS）
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        df_now = fetch_all_concurrently(STOCK_CODES)
        if df_now.empty:
            # 数据为空，创建占位空DataFrame（包含后续计算所需的全部列）
            df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)
        else:
            df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)
    except Exception as e:
        logger.error(f"获取股票数据异常: {e}")
        df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)

    df_now['time'] = time_full

    # 存储股票实时数据
    sssj_table = f"monitor_gp_sssj_{date_str}"
    save_dataframe(df_now, sssj_table, time_full, EXPIRE_SECONDS)

    # 获取前30秒的数据（从 Redis 加载）
    window_seconds_offset = (WINDOW_SECONDS + INTERVAL - 1) // INTERVAL
    df_prev = redis_util.load_dataframe_by_offset(sssj_table, offset=window_seconds_offset, use_compression=False)

    # 计算并存储大盘强度
    culculate_gp_apqd_top30(df_now, df_prev, date_str, time_full, loop_start)


def culculate_gp_apqd_top30(df_now, df_prev, date_str, time_full, loop_start):
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
    if 'stock_code' in df_now.columns and 'code' not in df_now.columns:
        rename_map['stock_code'] = 'code'
    if 'short_name' in df_now.columns and 'name' not in df_now.columns:
        rename_map['short_name'] = 'name'
    if rename_map:
        df_now = df_now.rename(columns=rename_map)
        if df_prev is not None and not df_prev.empty:
            df_prev = df_prev.rename(columns=rename_map)

    # ---------- 确保必要列存在 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        raise ValueError(f"df_now 缺少必要列 {required_cols}，当前列：{df_now.columns.tolist()}")

    # ---------- 计算大盘强度 ----------
    judge30 = judge_market_strength(get_market_stats(df_now, df_prev))
    apqd_table = f"monitor_gp_apqd_{date_str}"
    save_dataframe(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    if df_prev is not None and not df_prev.empty:
        top30_df = calculate_top30_v3(df_now, df_prev, loop_start)   # v3 内部已处理列名
        if not top30_df.empty:
            gp_top30_table = f"monitor_gp_top30_{date_str}"
            save_dataframe(top30_df, gp_top30_table, time_full, EXPIRE_SECONDS)
            # 增加上攻排行 - 顶级游资+超级短线量化思路
            redis_util.update_attack_ranking(top30_df, data_type='stock', rq=date_str, time_str=time_full)


def run_monitor_loop_synced(process_func, interval=INTERVAL):
    """
    同步监控主循环：在 interval 秒的整数倍时刻执行 process_func。
    使用本模块的时间判断函数。
    """
    while True:
        now = time.time()
        # 计算下一个整数倍时刻
        next_time = ((now + interval) // interval) * interval
        sleep_seconds = next_time - now
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        target_dt = datetime.fromtimestamp(next_time)
        if not is_trading_time(target_dt):
            if is_past_1500(target_dt):
                print(f"当前时间 {target_dt} 已过15:00，程序退出")
                redis_util.close_redis()
                sys.exit(0)
            next_start = next_trading_start(target_dt)
            sleep_until = (next_start - datetime.now()).total_seconds()
            if sleep_until > 0:
                print(f"当前不在交易时间，休眠 {sleep_until:.2f} 秒直到 {next_start.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(sleep_until)
            continue

        # print(f"开始获取数据... {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        process_func(target_dt)

        if is_past_1500(datetime.now()):
            print("已过15:00，程序退出")
            redis_util.close_redis()
            sys.exit(0)


if __name__ == "__main__":
    run_monitor_loop_synced(deal_gp_works, interval=INTERVAL)