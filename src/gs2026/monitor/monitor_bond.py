"""
实时监控获取债券数据——集思录
"""

import time
import warnings
import sys
from pathlib import Path

import adata
import akshare as ak
import pandas as pd
from sqlalchemy.exc import SAWarning

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

# ========== 区间次数缓存导入（可删除块开始）==========
try:
    from gs2026.monitor.window_count_cache import get_window_count
    _window_count_enabled = True
except ImportError:
    _window_count_enabled = False
    def get_window_count(*args, **kwargs):
        return 0
# 可删除块结束

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

# 债券数据源优先级（按顺序降级，首个为主数据源）
BOND_DATA_SOURCES = ['adata','akshare']

url = config_util.get_config('common.url')
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

# 【修复】添加 charset=utf8mb4 支持 emoji
# 替换 utf8 为 utf8mb4
url = url.replace('charset=utf8', 'charset=utf8mb4')
if 'charset=utf8mb4' not in url:
    if '?' in url:
        url += '&charset=utf8mb4'
    else:
        url += '?charset=utf8mb4'

engine = config_util.get_engine(pool_size=20, max_overflow=30)
# 注意：不要创建全局连接，使用 with engine.connect() 上下文管理器
mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接
try:
    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
except Exception as e:
    logger.error(f"Redis 初始化失败: {e}")
    sys.exit(1)

# ------------------------------
# 配置参数
INTERVAL = 3           # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
WINDOW_SECONDS = 15
# 表结构检查缓存（避免每tick查MySQL元数据）
_zq_table_schema_checked = set()
_zq_table_schema_no_body = set()

# ====== 1分钟字段缓存（纯内存，每分钟更新一次基准）======
_min1_base_minute = None      # 当前基准所属分钟 '09:32'
_min1_base_pct = {}           # { bond_code: change_pct }
_min1_base_amt = {}           # { bond_code: amount }


def compute_min1_fields(df_now, time_full):
    """
    1分钟字段计算（纯内存，零IO）
    - 每分钟第一个tick: 缓存当前数据为基准（min1=0）
    - 同分钟后续tick: 内存向量化计算
    - 冷启动/宕机: 自身为基准（min1=0）
    """
    global _min1_base_minute, _min1_base_pct, _min1_base_amt

    current_minute = time_full[:5]  # '09:32:45' → '09:32'
    code_col = 'bond_code' if 'bond_code' in df_now.columns else 'code'

    # 新分钟 or 冷启动 → 当前tick就是基准
    if _min1_base_minute != current_minute:
        _min1_base_pct = dict(zip(df_now[code_col], df_now['change_pct']))
        _min1_base_amt = dict(zip(df_now[code_col], df_now['amount']))
        _min1_base_minute = current_minute
        logger.debug(f"[1分钟] 新基准 minute={current_minute}, bonds={len(_min1_base_pct)}")

    # 向量化计算
    base_pct = df_now[code_col].map(_min1_base_pct).fillna(df_now['change_pct'])
    base_amt = df_now[code_col].map(_min1_base_amt).fillna(df_now['amount'])

    df_now['min1_change_pct'] = (df_now['change_pct'] - base_pct).round(4)
    df_now['min1_amount'] = (df_now['amount'] - base_amt).round(0)
    df_now['min1_amount_rank'] = df_now['min1_amount'].rank(ascending=False, method='min').astype(int)

    return df_now


# ====== 趋势指标计算（slope_short, slope_long, peak_vol_bias, high_distance）======
from collections import deque

WINDOW_SHORT = 60    # 3分钟
WINDOW_LONG = 300    # 15分钟

_slope_buf_short = {}   # { bond_code: deque(maxlen=60) }
_slope_buf_long = {}    # { bond_code: deque(maxlen=300) }
_peak_vol_state = {}    # { bond_code: {'max_amount': float, 'price_at_max': float} }
_high_state = {}        # { bond_code: {'max_cpct': float} }
_indicator_date = None
_indicator_recovered = False


def _calc_slope(buf):
    """从deque计算线性回归斜率（最小二乘法）"""
    n = len(buf)
    if n < 3:
        return 0.0
    sum_x = n * (n - 1) / 2
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6
    sum_y = 0.0
    sum_xy = 0.0
    for i, y in enumerate(buf):
        sum_y += y
        sum_xy += i * y
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def _recover_indicators(engine, date):
    """ONE-TIME启动恢复peak_vol和high_distance"""
    global _peak_vol_state, _high_state, _indicator_recovered
    if _indicator_recovered:
        return
    try:
        from sqlalchemy import text as sa_text
        table = f"monitor_zq_sssj_{date}"
        sql = sa_text(f"""
            SELECT bond_code, MAX(amount) as max_amt, MAX(change_pct) as max_cpct
            FROM {table}
            GROUP BY bond_code
        """)
        sql2 = sa_text(f"""
            SELECT t.bond_code, t.price
            FROM {table} t
            INNER JOIN (
                SELECT bond_code, MAX(amount) as max_amt FROM {table} GROUP BY bond_code
            ) m ON t.bond_code = m.bond_code AND t.amount = m.max_amt
            GROUP BY t.bond_code
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
            for r in rows:
                code, max_amt, max_cpct = r[0], float(r[1]), float(r[2])
                _peak_vol_state[code] = {'max_amount': max_amt, 'price_at_max': 0}
                _high_state[code] = {'max_cpct': max_cpct}
            rows2 = conn.execute(sql2).fetchall()
            for r in rows2:
                if r[0] in _peak_vol_state:
                    _peak_vol_state[r[0]]['price_at_max'] = float(r[1])
        _indicator_recovered = True
        logger.info(f"[indicators] 恢复成功: {len(rows)} 只债券")
    except Exception as e:
        logger.warning(f"[indicators] 恢复失败(降级运行): {e}")
        _indicator_recovered = True


def compute_indicators(df_now, current_date, engine=None):
    """
    计算4个趋势指标（增量，常规路径零IO）
    - slope_short: 3分钟滚动斜率
    - slope_long: 15分钟滚动斜率
    - peak_vol_bias: 放量高点偏离度
    - high_distance: 日内高点距离
    """
    global _slope_buf_short, _slope_buf_long
    global _peak_vol_state, _high_state
    global _indicator_date, _indicator_recovered

    # 日期切换 → 清空
    if _indicator_date != current_date:
        _slope_buf_short = {}
        _slope_buf_long = {}
        _peak_vol_state = {}
        _high_state = {}
        _indicator_recovered = False
        _indicator_date = current_date

    # 首次恢复
    if not _indicator_recovered and engine:
        _recover_indicators(engine, current_date)

    code_col = 'bond_code' if 'bond_code' in df_now.columns else 'code'
    slopes_s = []
    slopes_l = []
    biases = []
    high_dists = []

    for _, row in df_now.iterrows():
        code = row[code_col]
        cpct = float(row['change_pct'])
        price = float(row['price'])
        amount = float(row['amount'])

        # slope_short
        if code not in _slope_buf_short:
            _slope_buf_short[code] = deque(maxlen=WINDOW_SHORT)
        _slope_buf_short[code].append(cpct)
        slopes_s.append(round(_calc_slope(_slope_buf_short[code]), 6))

        # slope_long
        if code not in _slope_buf_long:
            _slope_buf_long[code] = deque(maxlen=WINDOW_LONG)
        _slope_buf_long[code].append(cpct)
        slopes_l.append(round(_calc_slope(_slope_buf_long[code]), 6))

        # peak_vol_bias
        if code not in _peak_vol_state:
            _peak_vol_state[code] = {'max_amount': 0, 'price_at_max': price}
        pv = _peak_vol_state[code]
        if amount > pv['max_amount']:
            pv['max_amount'] = amount
            pv['price_at_max'] = price
        bias = (price - pv['price_at_max']) / pv['price_at_max'] * 100 if pv['price_at_max'] > 0 else 0
        biases.append(round(bias, 4))

        # high_distance
        if code not in _high_state:
            _high_state[code] = {'max_cpct': cpct}
        hs = _high_state[code]
        if cpct > hs['max_cpct']:
            hs['max_cpct'] = cpct
        high_dists.append(round(cpct - hs['max_cpct'], 4))

    df_now['slope_short'] = slopes_s
    df_now['slope_long'] = slopes_l
    df_now['peak_vol_bias'] = biases
    df_now['high_distance'] = high_dists
    return df_now


# ====== 大盘趋势指标（市场级，每tick一组值）======
_mkt_slope_buf_short = deque(maxlen=WINDOW_SHORT)
_mkt_slope_buf_long = deque(maxlen=WINDOW_LONG)
_mkt_peak_vol = {'max_total_amt': 0, 'pct_at_max': 0.0}
_mkt_high = {'max_avg_pct': -999.0}
_mkt_date = None

# ====== 大盘扩展指标（加权斜率/变化率/加速度）======
_mkt_ext_price_cache = []       # [(seconds, avg_pct), ...] 保留2.5分钟
_mkt_ext_prev_slope = 0.0       # 上一tick大盘加权斜率
_mkt_ext_date = None            # 日期切换检测


def compute_mkt_ext_indicators(df_now, time_full, current_date):
    """大盘加权斜率指标（每tick一次，O(K)计算 K≈50）
    
    Returns:
        (mkt_weighted_slope_2m, mkt_change_1m_pct, mkt_price_acceleration)
    """
    global _mkt_ext_price_cache, _mkt_ext_prev_slope, _mkt_ext_date

    # 日期切换 → 清空
    if _mkt_ext_date != current_date:
        _mkt_ext_price_cache = []
        _mkt_ext_prev_slope = 0.0
        _mkt_ext_date = current_date

    avg_pct = float(df_now['change_pct'].mean())
    current_seconds = _time_to_seconds(time_full)

    # 追加 + 清理过期（保留150秒 = 5倍half_life）
    _mkt_ext_price_cache.append((current_seconds, avg_pct))
    cutoff = current_seconds - 150
    _mkt_ext_price_cache = [(ts, p) for ts, p in _mkt_ext_price_cache if ts >= cutoff]

    # 1. 加权斜率（EWLR, half_life=30s）
    if len(_mkt_ext_price_cache) >= 2:
        prices = [p for _, p in _mkt_ext_price_cache]
        times = [t for t, _ in _mkt_ext_price_cache]
        mkt_ws = round(_calc_weighted_slope(prices, times, half_life=30), 6)
    else:
        mkt_ws = 0.0

    # 2. 1分钟变化率
    target_ts = current_seconds - 60
    pct_1m_ago = None
    for ts, p in reversed(_mkt_ext_price_cache):
        if ts <= target_ts:
            pct_1m_ago = p
            break
    mkt_c1p = round(avg_pct - pct_1m_ago, 4) if pct_1m_ago is not None else 0.0

    # 3. 加速度（当前斜率 - 上一tick斜率）
    mkt_pa = round(mkt_ws - _mkt_ext_prev_slope, 6)
    _mkt_ext_prev_slope = mkt_ws

    return mkt_ws, mkt_c1p, mkt_pa


def compute_market_indicators(df_now, current_date):
    """
    计算大盘趋势指标（基于全市场平均涨跌幅）
    每tick调用一次，O(1)，零IO
    结果广播到df_now所有行（同tick所有bond共享）
    """
    global _mkt_slope_buf_short, _mkt_slope_buf_long
    global _mkt_peak_vol, _mkt_high, _mkt_date

    # 日期切换 → 清空
    if _mkt_date != current_date:
        _mkt_slope_buf_short = deque(maxlen=WINDOW_SHORT)
        _mkt_slope_buf_long = deque(maxlen=WINDOW_LONG)
        _mkt_peak_vol = {'max_total_amt': 0, 'pct_at_max': 0.0}
        _mkt_high = {'max_avg_pct': -999.0}
        _mkt_date = current_date

    # 计算大盘数据
    avg_pct = float(df_now['change_pct'].mean())
    total_amt = float(df_now['amount'].sum())

    # slope_short
    _mkt_slope_buf_short.append(avg_pct)
    mkt_ss = round(_calc_slope(_mkt_slope_buf_short), 6)

    # slope_long
    _mkt_slope_buf_long.append(avg_pct)
    mkt_sl = round(_calc_slope(_mkt_slope_buf_long), 6)

    # peak_vol_bias
    if total_amt > _mkt_peak_vol['max_total_amt']:
        _mkt_peak_vol['max_total_amt'] = total_amt
        _mkt_peak_vol['pct_at_max'] = avg_pct
    mkt_pvb = round(avg_pct - _mkt_peak_vol['pct_at_max'], 4)

    # high_distance
    if avg_pct > _mkt_high['max_avg_pct']:
        _mkt_high['max_avg_pct'] = avg_pct
    mkt_hd = round(avg_pct - _mkt_high['max_avg_pct'], 4)

    # 广播到所有行
    df_now['mkt_slope_short'] = mkt_ss
    df_now['mkt_slope_long'] = mkt_sl
    df_now['mkt_peak_vol_bias'] = mkt_pvb
    df_now['mkt_high_distance'] = mkt_hd
    return df_now


# ====== 扩展指标计算（weighted_slope_2m, change_1m_pct, price_acceleration）======
# 使用与原有指标相同的模式：全局缓存 + 增量计算

_ext_price_cache = {}       # { bond_code: [(timestamp, price), ...] }
_ext_slope_cache = {}       # { bond_code: last_slope }
_ext_date = None


def _time_to_seconds(time_str):
    """将HHMMSS或HH:MM:SS转换为当天秒数"""
    try:
        if ':' in time_str:
            # HH:MM:SS 格式
            parts = time_str.split(':')
            hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            # HHMMSS 格式
            hh = int(time_str[:2])
            mm = int(time_str[2:4])
            ss = int(time_str[4:6])
        return hh * 3600 + mm * 60 + ss
    except:
        return 0


def _calc_weighted_slope(prices, times, half_life=30):
    """
    计算指数加权斜率（精确计算）
    
    参数:
        prices: 价格列表
        times: 时间列表（秒）
        half_life: 半衰期（秒）
    """
    if len(prices) < 2:
        return 0.0
    
    import numpy as np
    prices_arr = np.array(prices, dtype=np.float64)
    times_arr = np.array(times, dtype=np.float64)
    
    # 指数权重
    lambda_param = np.log(2) / half_life
    current_time = times_arr[-1]
    weights = np.exp(-lambda_param * (current_time - times_arr))
    weights = weights / np.sum(weights)
    
    # 加权回归
    t_mean = np.sum(weights * times_arr)
    p_mean = np.sum(weights * prices_arr)
    cov = np.sum(weights * (times_arr - t_mean) * (prices_arr - p_mean))
    var = np.sum(weights * (times_arr - t_mean) ** 2)
    
    return float(cov / var) if var != 0 else 0.0


def compute_ext_indicators(df_now, time_full, current_date):
    """
    计算扩展指标（纯内存，零IO）
    - weighted_slope_2m: 2分钟加权斜率
    - change_1m_pct: 1分钟变化率
    - price_acceleration: 价格加速度
    
    设计原则:
    - 与原有指标计算模式一致（全局缓存 + 增量）
    - 精确计算，不接受近似
    - 400+债券规模优化
    """
    global _ext_price_cache, _ext_slope_cache, _ext_date
    
    # 日期切换 → 清空
    if _ext_date != current_date:
        _ext_price_cache = {}
        _ext_slope_cache = {}
        _ext_date = current_date
    
    code_col = 'bond_code' if 'bond_code' in df_now.columns else 'code'
    current_seconds = _time_to_seconds(time_full)
    
    weighted_slopes = []
    change_1m = []
    accelerations = []
    
    for _, row in df_now.iterrows():
        code = row[code_col]
        price = float(row['price'])
        
        # 更新价格缓存（保留2.5分钟数据）
        if code not in _ext_price_cache:
            _ext_price_cache[code] = []
        _ext_price_cache[code].append((current_seconds, price))
        
        # 清理过期数据（保留2.5分钟 = 150秒）
        cutoff = current_seconds - 150
        _ext_price_cache[code] = [
            (ts, p) for ts, p in _ext_price_cache[code] if ts >= cutoff
        ]
        
        cache = _ext_price_cache[code]
        
        # 计算加权斜率（2分钟窗口）
        if len(cache) >= 2:
            cache_prices = [p for _, p in cache]
            cache_times = [t for t, _ in cache]
            ws = round(_calc_weighted_slope(cache_prices, cache_times, half_life=30), 6)
        else:
            ws = 0.0
        weighted_slopes.append(ws)
        
        # 计算1分钟变化率
        if len(cache) >= 2:
            target_ts = current_seconds - 60
            price_1m_ago = None
            for ts, p in reversed(cache):
                if ts <= target_ts:
                    price_1m_ago = p
                    break
            if price_1m_ago is not None and price_1m_ago != 0:
                c1p = round((price - price_1m_ago) / price_1m_ago * 100, 4)
            else:
                c1p = 0.0
        else:
            c1p = 0.0
        change_1m.append(c1p)
        
        # 计算加速度（当前斜率 - 上一周期斜率）
        prev_slope = _ext_slope_cache.get(code, 0.0)
        pa = round(ws - prev_slope, 6)
        accelerations.append(pa)
        
        # 保存当前斜率用于下次
        _ext_slope_cache[code] = ws
    
    # 计算大盘扩展指标（每tick一次）
    mkt_ws, mkt_c1p, mkt_pa = compute_mkt_ext_indicators(df_now, time_full, current_date)

    # 构建ext_indicators JSON列（替代独立字段）
    import json
    ext_indicators_list = []
    for i in range(len(df_now)):
        ext_indicators_list.append(json.dumps({
            'weighted_slope_2m': weighted_slopes[i],
            'change_1m_pct': change_1m[i],
            'price_acceleration': accelerations[i],
            'mkt_weighted_slope_2m': mkt_ws,
            'mkt_change_1m_pct': mkt_c1p,
            'mkt_price_acceleration': mkt_pa,
        }, ensure_ascii=False))
    
    df_now['ext_indicators'] = ext_indicators_list
    
    return df_now


# ------------------------------
def get_bond_jsl(max_retries=3, retry_delay=2):
    """
    数据源——集思录——满足3秒，缺少成交量字段，带重试
    :return: DataFrame 或空 DataFrame
    """
    for attempt in range(max_retries):
        try:
            my_jsl_cookie = ''
            df = ak.bond_cb_jsl(cookie=my_jsl_cookie)
            if df is not None and not df.empty:
                return df
        except ValueError as e:
            logger.warning(f"集思录数据格式错误(尝试{attempt+1}/{max_retries}): {e}")
        except ConnectionError as e:
            logger.warning(f"集思录网络连接失败(尝试{attempt+1}/{max_retries}): {e}")
        except Exception as e:
            logger.warning(f"集思录请求异常(尝试{attempt+1}/{max_retries}): {e}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay * (attempt + 1))
    
    logger.error("集思录数据获取失败，已达最大重试次数")
    return pd.DataFrame()

def get_bond_adata(max_retries=3, retry_delay=2):
    """
    数据源——adata——满足3秒，带重试
    :return: DataFrame 或空 DataFrame
    """
    for attempt in range(max_retries):
        try:
            df = adata.bond.market.list_market_current()
            if df is not None and not df.empty:
                return df
            # 空结果也重试
        except ValueError as e:
            # JSON解析失败（API返回空/错误内容）
            logger.warning(f"adata数据格式错误(尝试{attempt+1}/{max_retries}): {e}")
        except ConnectionError as e:
            logger.warning(f"adata网络连接失败(尝试{attempt+1}/{max_retries}): {e}")
        except Exception as e:
            logger.warning(f"adata请求异常(尝试{attempt+1}/{max_retries}): {e}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay * (attempt + 1))  # 递增退避
    
    logger.error("adata数据获取失败，已达最大重试次数")
    return pd.DataFrame()

def get_bond_akshare(max_retries=3, retry_delay=2):
    """
    数据源——akshare——全量可转债实时行情（约0.7秒），带重试
    使用 ak.bond_zh_hs_cov_spot() 一次性获取全部可转债数据
    :return: DataFrame 或空 DataFrame
    """
    for attempt in range(max_retries):
        try:
            df = ak.bond_zh_hs_cov_spot()
            if df is not None and not df.empty:
                # 列名标准化（与adata格式对齐）
                df = df.rename(columns={
                    'code': 'bond_code',
                    'name': 'bond_name',
                    'trade': 'price',
                    'settlement': 'pre_close',
                    'pricechange': 'change',
                    'changepercent': 'change_pct',
                    'ticktime': 'time',
                })
                # 数值类型转换（akshare返回字符串，adata返回float）
                float_cols = ['price', 'open', 'high', 'low', 'pre_close', 'change', 'change_pct']
                for col in float_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                # volume/amount 转 float（与adata一致）
                for col in ['volume', 'amount']:
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                # 仅保留标准列
                keep_cols = SOURCE_BOND_FULL_COLUMNS + ['time']
                df = df[[c for c in keep_cols if c in df.columns]]
                return df
        except ValueError as e:
            logger.warning(f"akshare数据格式错误(尝试{attempt+1}/{max_retries}): {e}")
        except ConnectionError as e:
            logger.warning(f"akshare网络连接失败(尝试{attempt+1}/{max_retries}): {e}")
        except Exception as e:
            logger.warning(f"akshare请求异常(尝试{attempt+1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            time.sleep(retry_delay * (attempt + 1))

    logger.error("akshare数据获取失败，已达最大重试次数")
    return pd.DataFrame()

def get_bond(data_source: str) -> pd.DataFrame:
    """
    根据数据源名称获取债券数据，始终返回一个 DataFrame。
    如果数据源不存在，返回空的 DataFrame。
    """
    handlers = {
        'jsl': get_bond_jsl,
        'adata': get_bond_adata,
        'akshare': get_bond_akshare,
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


def get_bond_with_fallback(time_full: str) -> pd.DataFrame:
    """按 BOND_DATA_SOURCES 优先级依次尝试获取债券数据，支持自动降级。

    内置异常处理：网络异常等待60秒，数据格式/列缺失直接返回空DataFrame。
    成功获取后自动补零 bond_code。

    :param time_full: 当前时间字符串（仅用于日志）
    :return: 标准化后的 DataFrame（含 bond_code 补零）或空 DataFrame
    """
    for i, source in enumerate(BOND_DATA_SOURCES):
        try:
            df = get_bond(source)
            if not df.empty:
                df['bond_code'] = df['bond_code'].astype(str).str.zfill(6)
                if i > 0:
                    chain = '→'.join(BOND_DATA_SOURCES[:i + 1])
                    logger.warning(f"[{time_full}] 数据源降级成功: {chain}")
                return df
            tail = '，尝试下一数据源' if i < len(BOND_DATA_SOURCES) - 1 else ''
            logger.warning(f"[{time_full}] {source} 获取债券数据为空{tail}")

        except ConnectionError as e:
            logger.error(f"[{time_full}] {source} 网络连接异常: {e}")
            if i == len(BOND_DATA_SOURCES) - 1:
                time.sleep(60)
        except ValueError as e:
            logger.error(f"[{time_full}] {source} 数据格式错误: {e}")
        except KeyError as e:
            logger.error(f"[{time_full}] {source} 数据缺少必要列: {e}")
        except Exception as e:
            logger.error(f"[{time_full}] {source} 获取数据异常: {e}", exc_info=True)
            if i == len(BOND_DATA_SOURCES) - 1:
                time.sleep(60)

    logger.error(f"[{time_full}] 所有数据源均失败: {BOND_DATA_SOURCES}")
    return pd.DataFrame()


# ====== 量化选债自动筛选（参考买点候选模式）======
_qs_scheme_cache = None
_qs_scheme_cache_time = 0
_QS_CACHE_TTL = 30  # 方案缓存30秒
_qs_seen_this_minute = {}  # 每分钟每债去重: {bond_code_HHMM: True}
_qs_last_minute = ''       # 上一次处理的分钟


def _load_qs_schemes(engine):
    """从MySQL加载在用方案"""
    from sqlalchemy import text as sa_text
    import json as _json
    sql = sa_text("""
        SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct,
               max_hold_time, price_offset, offset_mode
        FROM quant_screen_schemes
        WHERE is_active = 1 AND use_realtime = 1
    """)
    with engine.connect() as conn:
        result = conn.execute(sql)
        schemes = []
        for row in result:
            schemes.append({
                'name': row.scheme_name,
                'conditions': _json.loads(row.conditions_json) if row.conditions_json else [],
                'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                'max_hold_time': row.max_hold_time,
                'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                'offset_mode': row.offset_mode or 'fixed',
            })
        return schemes


def run_quant_screen_on_tick(df_now, date_str, time_full, engine):
    """
    每tick自动执行量化选债（参考买点候选模式）
    Redis实时快照 + MySQL历史记录
    每分钟每债仅保存首次命中
    """
    global _qs_scheme_cache, _qs_scheme_cache_time, _qs_seen_this_minute, _qs_last_minute
    import time as _time
    import json as _json

    try:
        # 0. 展开 ext_indicators JSON 为独立列（供筛选引擎使用）
        if 'ext_indicators' in df_now.columns:
            import pandas as pd
            ext_parsed = df_now['ext_indicators'].apply(
                lambda x: _json.loads(x) if isinstance(x, str) and x else {}
            )
            ext_expanded = pd.json_normalize(ext_parsed)
            for col in ext_expanded.columns:
                if col not in df_now.columns:
                    df_now[col] = ext_expanded[col].values

        # 1. 方案缓存（30秒TTL）
        now = _time.time()
        if _qs_scheme_cache is None or (now - _qs_scheme_cache_time) > _QS_CACHE_TTL:
            _qs_scheme_cache = _load_qs_schemes(engine)
            _qs_scheme_cache_time = now
            logger.debug(f"[量化选债] 刷新方案缓存: {len(_qs_scheme_cache)}个")

        if not _qs_scheme_cache:
            return

        # 2. 统一筛选引擎
        from gs2026.dashboard2.services.quant_screen_core import (
            apply_scheme_conditions,
            save_quant_screen_hits,
        )
        matches, stats = apply_scheme_conditions(df_now, _qs_scheme_cache)

        # 3. Redis实时快照（每tick都写，参考买点候选模式）
        live_data = _json.dumps({
            'time': time_full,
            'matches': matches,
            'stats': stats,
            'scheme_count': len(_qs_scheme_cache),
        }, ensure_ascii=False)
        redis_key = f"quant_screen_live:{date_str}"
        redis_util._get_redis_client().set(redis_key, live_data, ex=30)

        # 4. MySQL历史记录（每分钟每债仅保存首次）
        if matches:
            # 当前分钟（HHMM）
            time_clean = time_full.replace(':', '')
            current_minute = time_clean[:4]
            
            # 新的一分钟，清空去重字典
            if current_minute != _qs_last_minute:
                _qs_seen_this_minute = {}
                _qs_last_minute = current_minute
            
            # 过滤已保存的债券
            new_matches = []
            for m in matches:
                bond_code = m.get('bond_code', '')
                if bond_code not in _qs_seen_this_minute:
                    _qs_seen_this_minute[bond_code] = True
                    new_matches.append(m)
            
            if new_matches:
                save_quant_screen_hits(
                    date_str, time_full, new_matches[:20],
                    _qs_scheme_cache, df_now, engine
                )
                logger.info(f"[量化选债] tick={time_full} 命中{len(matches)}条 保存{len(new_matches)}条")

    except Exception as e:
        logger.warning(f"[量化选债] 执行失败(不影响主流程): {e}")


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

    df_now = get_bond_with_fallback(time_full)
    if df_now.empty:
        return

    df_now['time'] = time_full

    # 【新增】计算债券实体红绿柱（直接使用open字段）
    if 'open' in df_now.columns:
        df_now['is_body_up'] = (df_now['price'] > df_now['open']).astype(int)
        df_now['is_body_down'] = (df_now['price'] < df_now['open']).astype(int)
        df_now['is_body_flat'] = (df_now['price'] == df_now['open']).astype(int)
        logger.info(f"[债券] 实体红绿柱 红:{df_now['is_body_up'].sum()} "
                   f"绿:{df_now['is_body_down'].sum()} 平:{df_now['is_body_flat'].sum()}")
    else:
        logger.warning("[债券] 无open字段，无法计算实体红绿柱")

    # 【优化】检查表结构，缓存结果避免每tick查MySQL元数据
    sssj_table = f"monitor_zq_sssj_{date_str}"
    if sssj_table not in _zq_table_schema_checked:
        try:
            from sqlalchemy import inspect
            inspector = inspect(msac.engine)
            if inspector.has_table(sssj_table):
                columns = [c['name'] for c in inspector.get_columns(sssj_table)]
                if 'is_body_up' not in columns:
                    _zq_table_schema_no_body.add(sssj_table)
                    logger.info(f"[债券] 表{sssj_table}已存在且无is_body列，后续自动删除这些列")
            _zq_table_schema_checked.add(sssj_table)
        except Exception as e:
            logger.warning(f"[债券] 检查表结构失败: {e}")

    if sssj_table in _zq_table_schema_no_body:
        df_now = df_now.drop(columns=['is_body_up', 'is_body_down', 'is_body_flat'], errors='ignore')

    # 【新增】1分钟字段计算（纯内存，零IO）
    df_now = compute_min1_fields(df_now, time_full)

    # 【新增】金额排名（纯内存，零IO）
    code_col = 'bond_code' if 'bond_code' in df_now.columns else 'code'
    if 'amount' in df_now.columns:
        df_now['amount_rank'] = df_now['amount'].rank(ascending=False, method='min').astype(int)

    # 【新增】趋势指标（slope_short, slope_long, peak_vol_bias, high_distance）
    df_now = compute_indicators(df_now, date_str, engine=engine)

    # 【新增】大盘趋势指标（市场级，广播到所有行）
    df_now = compute_market_indicators(df_now, date_str)

    # 【新增】扩展指标计算（weighted_slope_2m, change_1m_pct, price_acceleration）
    # 纯内存计算，零IO，与原有指标计算模式一致
    df_now = compute_ext_indicators(df_now, time_full, date_str)

    # 【新增】量化选债自动筛选（参考买点候选模式：Redis快照+MySQL历史）
    run_quant_screen_on_tick(df_now, date_str, time_full, engine)

    # 存储债券实时数据
    msac.save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)

    # 获取前30秒的数据（从 Redis 加载）
    # 早盘特殊处理：9:30:00-9:30:15使用最早时间戳作为基准
    from datetime import time as dt_time
    time_obj = loop_start.time()
    is_early_morning = (dt_time(9, 30, 0) <= time_obj < dt_time(9, 30, 15))
    
    if is_early_morning:
        # 早盘9:30:00-9:30:15：获取最早时间戳作为基准
        # 【修复】跳过集合竞价数据（09:30之前的时间点债券无成交量，会导致zf_30/momentum为NaN）
        r = redis_util._get_redis_client()
        ts_key = f"{sssj_table}:timestamps"
        all_times = r.lrange(ts_key, 0, -1)
        decoded = [t.decode() if isinstance(t, bytes) else t for t in all_times]
        post_930 = [t for t in decoded if t >= "09:30:00"]
        
        earliest_time = post_930[0] if post_930 else None
        
        if earliest_time:
            df_prev = redis_util.load_dataframe_by_key(f"{sssj_table}:{earliest_time}", use_compression=False)
            logger.info(f"[早盘-债券] {time_full} 使用最早数据({earliest_time})作为基准，共{len(df_prev) if df_prev is not None else 0}条")
        else:
            logger.warning(f"[早盘-债券] {time_full} 无法找到09:30之后的时间戳，跳过计算")
            df_prev = None
    else:
        # 正常15秒区间
        window_seconds_offset = (WINDOW_SECONDS + INTERVAL - 1) // INTERVAL
        df_prev = redis_util.load_dataframe_by_offset(sssj_table,
                                                      offset=window_seconds_offset,
                                                      use_compression=False)

    # 计算并存储大盘强度
    culculate_zq_apqd_top30(df_now, df_prev, date_str, time_full, loop_start, is_early_morning)


def culculate_zq_apqd_top30(df_now, df_prev, date_str, time_full, loop_start, is_early_morning=False):
    """
    计算大盘强度（APQD）和涨幅/涨速前30榜单，并存储。

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 30秒前数据（可能为空）。
        date_str (str): 日期字符串 YYYYMMDD。
        time_full (str): 时间字符串 HH:MM:SS。
        loop_start (datetime): 轮询开始时间。
        is_early_morning (bool): 是否为早盘9:30:00-9:30:15时段。
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

    # 【优化】仅在is_body_up不存在时重新计算实体红绿柱
    if 'is_body_up' not in df_now.columns and 'open' in df_now.columns:
        df_now['is_body_up'] = (df_now['price'] > df_now['open']).astype(int)
        df_now['is_body_down'] = (df_now['price'] < df_now['open']).astype(int)
        df_now['is_body_flat'] = (df_now['price'] == df_now['open']).astype(int)

    # ---------- 【修复】统一 code 列类型为 str ----------
    # df_now 来自 adata（code 是 str），df_prev 来自 Redis JSON 反序列化（code 可能变成 int64）
    # 类型不一致会导致 set_index().reindex() 全部 NaN，tick 统计归零
    df_now['code'] = df_now['code'].astype(str)
    if df_prev is not None and not df_prev.empty:
        df_prev['code'] = df_prev['code'].astype(str)

    # ---------- 【调试日志】降级为DEBUG避免性能开销 ----------
    logger.debug(
        f"[债券大盘] time={time_full} df_now={len(df_now)}行 "
        f"change_pct_ge0={(df_now['change_pct']>0).sum()} "
        f"change_pct_le0={(df_now['change_pct']<0).sum()} "
        f"change_pct_mean={df_now['change_pct'].mean():.4f} "
        f"change_pct_min={df_now['change_pct'].min():.4f} "
        f"change_pct_max={df_now['change_pct'].max():.4f}"
    )
    if df_prev is not None and not df_prev.empty:
        logger.debug(
            f"[债券大盘] df_prev={len(df_prev)}行 "
            f"change_pct_ge0={(df_prev['change_pct']>0).sum()} "
            f"change_pct_le0={(df_prev['change_pct']<0).sum()}"
        )
    else:
        logger.debug(f"[债券大盘] df_prev is None or empty — 首次运行无历史可比数据")

    # ---------- 计算大盘强度 ----------
    stats_result = msac.get_market_stats(df_now, df_prev)
    logger.debug(
        f"[债券大盘] get_market_stats result: "
        f"cur_up={stats_result.get('cur_up',[0])[0] if 'cur_up' in stats_result.columns else 0}, "
        f"cur_down={stats_result.get('cur_down',[0])[0] if 'cur_down' in stats_result.columns else 0}, "
        f"min_up={stats_result.get('min_up',[0])[0] if 'min_up' in stats_result.columns else 0}, "
        f"min_down={stats_result.get('min_down',[0])[0] if 'min_down' in stats_result.columns else 0}"
    )
    judge30 = msac.judge_market_strength(stats_result)
    apqd_table = f"monitor_zq_apqd_{date_str}"

    # 债券大盘平均涨幅
    judge30['avg_change_pct'] = round(df_now['change_pct'].mean(), 4)

    # ---------- 计算大盘阶段（上升/下降/反弹/回落/震荡） ----------
    try:
        phase, strength, momentum = msac._compute_phase_for_tick(
            engine, apqd_table,
            int(judge30['body_up'].iloc[0]), int(judge30['body_down'].iloc[0]),
            int(judge30['min_up'].iloc[0]), int(judge30['min_down'].iloc[0])
        )
        judge30['market_phase'] = phase
        judge30['phase_strength'] = strength
        judge30['phase_momentum'] = momentum
    except Exception as e:
        judge30['market_phase'] = 'neutral'
        judge30['phase_strength'] = 'weak'
        judge30['phase_momentum'] = 0.0
        msac.logger.warning(f"[债券] 计算大盘阶段失败: {e}")

    msac.save_dataframe_async(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    if df_prev is not None and not df_prev.empty:
        top30_df = msac.calculate_top30_v3(df_now, df_prev, loop_start)   # v3 内部已处理列名
        if not top30_df.empty:
            zq_top30_table = f"monitor_zq_top30_{date_str}"
            result_df = msac.attack_conditions(top30_df, rank_name='bond', engine=engine, table_name=zq_top30_table)
            msac.save_dataframe_async(result_df, zq_top30_table, time_full, EXPIRE_SECONDS)
            # 上攻排行
            rank_result = redis_util.update_rank_redis(result_df, 'bond', date_str=date_str)
            # 【新增】早盘标记
            if is_early_morning:
                logger.info(f"[早盘-债券] {time_full} 完成上攻排行计算（使用最早时间基准）")
            # 收盘时保存到 MySQL
            if time_full == "15:00:00":
                msac.save_rank_to_mysql(rank_result, 'bond', date_str)




if __name__ == "__main__":
    msac.run_monitor_loop_synced(deal_zq_works, interval=INTERVAL)

