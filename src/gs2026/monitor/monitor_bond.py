"""
实时监控获取债券数据——集思录
"""

import time
import warnings
import sys
import os
from pathlib import Path

import adata
import akshare as ak
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SAWarning

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

# ========== Redis缓存导入（可插拔）==========
try:
    from gs2026.redis import write_tick_async, is_cache_enabled, CacheConfig
    _redis_cache_available = True
except ImportError as e:
    _redis_cache_available = False
    logger = log_util.get_logger(__name__)
    logger.warning(f"[monitor_bond] Redis缓存模块未安装: {e}")

# ========== 区间次数缓存导入（可删除块开始）==========
try:
    from gs2026.monitor.window_count_cache import get_window_count
    _window_count_enabled = True
except ImportError:
    _window_count_enabled = False
    def get_window_count(*args, **kwargs):
        return 0
# 可删除块结束
# ========== TDX连接缓存（新增）==========
_tdx_api = None              # TDX API连接缓存
_tdx_connected = False       # 连接状态
_tdx_last_used = 0           # 最后使用时间
_bond_codes_cache = None     # 债券代码列表缓存
_bond_codes_cache_time = 0   # 缓存时间戳
_CACHE_TTL = 3600            # 缓存有效期（秒）

# TDX服务器列表
# ====== TDX Servers Loader (auto-refresh from config) ======
import json
import os as _os

def _load_tdx_servers():
    """Load fresh TDX servers from configs/tdx_ips.json"""
    cfg_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        'configs', 'tdx_ips.json'
    )
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        srvs = cfg.get("servers", [])
        if srvs:
            # Convert to (ip, port) tuples
            return [(s["ip"], s["port"]) for s in srvs[:15]]
    except Exception:
        pass
    return None

_TDX_DYNAMIC = _load_tdx_servers()
if _TDX_DYNAMIC is not None:
    TDX_SERVERS = _TDX_DYNAMIC
else:
    # Use hardcoded TDX_SERVERS below
    pass

# [Original TDX_SERVERS as fallback]
TDX_SERVERS = [
    ('202.108.253.139', 80),
    ('123.125.108.90', 7709),
    ('218.75.126.9', 7709),
    ('202.108.253.131', 7709),

    ("119.147.212.81", 7709),
    ("119.147.212.82", 7709),
    ("119.147.212.83", 7709),
    ("121.14.104.69", 7709),
    ("121.14.104.70", 7709),
    ("106.120.74.86", 7709),
    ("114.80.63.45", 7709),
    ("117.184.140.156", 7709),
    ("113.105.73.88", 7709),
    ("114.80.149.19", 7709),
    ("hq.cjis.cn", 7709),
    ("sztdx.gtjas.com", 7709),
    ("shtdx.gtjas.com", 7709)
]

# ========== TDX 服务器池管理（增强版）==========
_tdx_server_status = {}  # 服务器状态: {server: {'healthy': bool, 'fail_count': int, 'last_check': float}}
_tdx_server_index = 0    # 当前服务器索引
_tdx_max_fail_count = 3  # 连续失败次数阈值
_tdx_health_check_interval = 300  # 健康检查间隔（秒）

def _init_server_status():
    """初始化服务器状态"""
    global _tdx_server_status
    if not _tdx_server_status:
        _tdx_server_status = {
            server: {'healthy': True, 'fail_count': 0, 'last_check': 0}
            for server in TDX_SERVERS
        }

def _get_healthy_servers():
    """获取健康的服务器列表"""
    _init_server_status()
    now = time.time()
    healthy = []
    
    for server, status in _tdx_server_status.items():
        # 不健康的服务器，超过间隔后尝试恢复
        if not status['healthy']:
            if now - status['last_check'] > _tdx_health_check_interval:
                status['healthy'] = True  # 临时恢复，下次连接时验证
                status['fail_count'] = 0
                healthy.append(server)
        else:
            healthy.append(server)
    
    return healthy

def _update_server_status(server, success):
    """更新服务器状态"""
    _init_server_status()
    status = _tdx_server_status[server]
    status['last_check'] = time.time()
    
    if success:
        status['healthy'] = True
        status['fail_count'] = 0
    else:
        status['fail_count'] += 1
        if status['fail_count'] >= _tdx_max_fail_count:
            status['healthy'] = False
            logger.warning(f"[tdx] 服务器 {server} 标记为不健康（连续失败{status['fail_count']}次）")

def _get_next_server():
    """获取下一个可用服务器（轮询+健康优先）"""
    global _tdx_server_index
    healthy = _get_healthy_servers()
    
    if not healthy:
        # 没有健康服务器，重置所有状态
        logger.warning("[tdx] 没有健康服务器，重置状态")
        _init_server_status()
        healthy = TDX_SERVERS
    
    # 轮询选择
    server = healthy[_tdx_server_index % len(healthy)]
    _tdx_server_index = (_tdx_server_index + 1) % len(healthy)
    return server


# ========== TDX连接管理函数（增强版）==========
def _get_tdx_api(max_retries=3, timeout=3):
    """获取或创建TdxHq_API连接（带服务器池和自动切换）"""
    global _tdx_api, _tdx_connected, _tdx_last_used
    
    # 检查现有连接是否有效
    if _tdx_api and _tdx_connected:
        try:
            # 简单验证：获取市场数量
            _ = _tdx_api.get_security_count(0)
            _tdx_last_used = time.time()
            return _tdx_api
        except Exception:
            logger.debug("[tdx] 现有连接失效，重新连接")
            _tdx_connected = False
            try:
                _tdx_api.close()
            except:
                pass
            _tdx_api = None
    
    # 尝试连接服务器
    for attempt in range(max_retries):
        server = _get_next_server()
        host, port = server
        
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            api.connect(host, port, time_out=timeout)
            
            # 验证连接：获取市场数量
            test_count = api.get_security_count(0)
            if test_count is None:
                raise Exception("返回空数据")
            
            # 连接成功
            _tdx_api = api
            _tdx_connected = True
            _tdx_last_used = time.time()
            _update_server_status(server, True)
            
            if attempt > 0:
                logger.info(f"[tdx] 第{attempt+1}次尝试后连接成功: {host}:{port}")
            else:
                logger.debug(f"[tdx] 连接成功: {host}:{port}")
            return api
            
        except Exception as e:
            logger.debug(f"[tdx] 连接失败 {host}:{port}: {e}")
            _update_server_status(server, False)
            try:
                api.close()
            except:
                pass
            
            # 短暂延迟后重试
            if attempt < max_retries - 1:
                time.sleep(0.2 * (attempt + 1))
    
    logger.error(f"[tdx] 所有服务器连接失败（尝试{max_retries}次）")
    return None


# ========== TDX 请求限流器（防止频繁调用被封）==========
_tdx_last_request_time = 0
_tdx_min_request_interval = 0.02  # 最小请求间隔（秒），每秒最多50次

def _tdx_rate_limit():
    """请求限流，防止频繁调用"""
    global _tdx_last_request_time
    now = time.time()
    elapsed = now - _tdx_last_request_time
    if elapsed < _tdx_min_request_interval:
        time.sleep(_tdx_min_request_interval - elapsed)
    _tdx_last_request_time = time.time()


def _get_bond_codes_cached(api):
    """获取可转债代码列表（带1小时缓存）"""
    global _bond_codes_cache, _bond_codes_cache_time
    
    now = time.time()
    if _bond_codes_cache and (now - _bond_codes_cache_time) < _CACHE_TTL:
        return _bond_codes_cache
    
    bonds = []
    try:
        # 深圳 (market=0): 12开头
        _tdx_rate_limit()
        count = api.get_security_count(0)
        if count is None:
            logger.warning("[tdx] 获取深圳市场证券数量失败，返回None")
            count = 0
        for start in range(0, count, 1000):
            _tdx_rate_limit()
            items = api.get_security_list(0, start)
            if items:
                for s in items:
                    if s['code'].startswith('12'):
                        bonds.append((0, s['code'], s.get('name', '')))
        
        # 上海 (market=1): 11开头
        _tdx_rate_limit()
        count = api.get_security_count(1)
        if count is None:
            logger.warning("[tdx] 获取上海市场证券数量失败，返回None")
            count = 0
        for start in range(0, count, 1000):
            _tdx_rate_limit()
            items = api.get_security_list(1, start)
            if items:
                for s in items:
                    if s['code'].startswith('11'):
                        bonds.append((1, s['code'], s.get('name', '')))
        
        _bond_codes_cache = bonds
        _bond_codes_cache_time = now
        logger.info(f"[tdx] 缓存债券代码: {len(bonds)}只")
    except Exception as e:
        logger.error(f"[tdx] 获取债券代码失败: {e}")
    
    return bonds



# ========== 交易助手适配器（可插拔模块）==========
try:
    from gs2026.monitor.trader_adapter import on_hit as trader_on_hit, get_adapter
    _trader_enabled = True
except ImportError:
    _trader_enabled = False

# 【v7统一】关闭旧trader_adapter自动下单，避免与auto_trader双重下单
# 保留导入供其他用途，但命中时不自动触发
_trader_enabled = False
# 可插拔模块结束

# ========== 自动止盈止损交易Hook（新增）==========
try:
    import sys
    from pathlib import Path
    # 从项目根目录计算路径
    _project_root = Path(__file__).resolve().parent.parent.parent.parent  # src/gs2026/monitor -> src/gs2026 -> src -> project_root
    _trader_script_path = _project_root / 'scripts' / 'huatai_trader'
    if str(_trader_script_path) not in sys.path:
        sys.path.insert(0, str(_trader_script_path))
    from trade_hook import init_trade_hook, on_hit as auto_trader_on_hit, on_tick as auto_trader_on_tick
    _auto_trader_enabled = True
except ImportError as e:
    _auto_trader_enabled = False
    # logger.warning(f"[auto_trader] 模块导入失败: {e}")
# 可插拔模块结束

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

# ========== 交易助手配置 ==========
if _trader_enabled:
    import yaml as _yaml
    # 从统一配置文件读取 filter 段
    _trader_config_path = Path(__file__).resolve().parent
    for _i in range(6):
        _candidate = _trader_config_path / 'configs' / 'huatai_trader' / 'config.yaml'
        if _candidate.exists():
            break
        _trader_config_path = _trader_config_path.parent
    
    if _candidate.exists():
        with open(_candidate, 'r', encoding='utf-8') as _f:
            _full_config = _yaml.safe_load(_f)
        TRADER_CONFIG = _full_config.get('filter', {})
        logger.info(f"[trader] 从 {_candidate} 加载配置")
    else:
        TRADER_CONFIG = {
            'enabled': True,
            'check_trading_time': False,
            'allowed_schemes': [],
            'blocked_schemes': [],
            'min_interval_seconds': 10,
            'max_daily_triggers': 50,
            'request_timeout': 5,
            'price_range': {'min': 50, 'max': 200},
        }
        logger.warning("[trader] 未找到 configs/huatai_trader/config.yaml，使用默认配置")
    
    # 补充适配器需要的字段
    TRADER_CONFIG.setdefault('trader_api_url', f"http://{_full_config.get('server', {}).get('host', '127.0.0.1')}:{_full_config.get('server', {}).get('port', 8081)}")
    TRADER_CONFIG.setdefault('notifications', {'sound': True, 'console': True, 'windows_toast': False})
    
    get_adapter(TRADER_CONFIG)
    logger.info("[trader] 交易助手适配器已加载")
# ========== 交易助手配置结束 ==========

# ========== 自动止盈止损交易Hook配置（新增）==========
# 注意：monitor_bond 只负责HTTP推送命中信号，不直接初始化trade_hook
# trade_hook 由 main.py 启动的 server 进程初始化
# 如果 _auto_trader_enabled 为 True，说明模块导入成功，HTTP推送可用
if _auto_trader_enabled:
    logger.info("[auto_trader] 自动止盈止损模块已加载，HTTP推送可用")
else:
    logger.info("[auto_trader] 自动止盈止损模块未加载")
# ========== 自动交易Hook配置结束 ==========

# ========== Redis缓存配置（可插拔）==========
if _redis_cache_available:
    # 从环境变量读取开关
    _cache_enabled = os.getenv('BOND_TICK_CACHE_ENABLED', 'true').lower() == 'true'
    CacheConfig.ENABLED = _cache_enabled
    logger.info(f"[monitor_bond] 分时图Redis缓存: {'启用' if _cache_enabled else '禁用'}")
# ========== Redis缓存配置结束 ==========

# 债券数据源优先级（按顺序降级，首个为主数据源）
BOND_DATA_SOURCES = ['tdx','adata','akshare']

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


def _get_pending_bonds_snapshot(current_date):
    """
    获取个券快照（recover_snapshot 内部按日期缓存，多次调用零额外开销）

    返回 bonds_snapshot dict 或 None。
    """
    try:
        from gs2026.monitor.snapshot_cache import recover_snapshot
        _mkt_snap, bonds_snap = recover_snapshot(current_date, engine=_get_snapshot_engine())
        return bonds_snap
    except Exception as e:
        logger.warning(f"[快照] 个券快照查询异常(降级): {e}")
        return None


def _snap_recover_bond_slopes(current_date):
    """
    从快照恢复个券斜率缓存 _slope_buf_short/long（#14-15）

    恢复失败时保持空dict（原行为，前60tick斜率从0累积）。
    """
    global _slope_buf_short, _slope_buf_long

    bonds_snap = _get_pending_bonds_snapshot(current_date)
    if not bonds_snap:
        return

    try:
        cnt = 0
        for code, data in bonds_snap.items():
            ss = data.get('ss')
            sl = data.get('sl')
            if ss:
                _slope_buf_short[code] = deque(ss, maxlen=WINDOW_SHORT)
            if sl:
                _slope_buf_long[code] = deque(sl, maxlen=WINDOW_LONG)
            cnt += 1
        logger.info(f"[快照] 个券斜率缓存已恢复: {cnt}只债券")
    except Exception as e:
        logger.warning(f"[快照] 个券斜率恢复解析失败(降级): {e}")


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

    # 日期切换 → 清空（先尝试从快照恢复斜率缓存）
    if _indicator_date != current_date:
        _slope_buf_short = {}
        _slope_buf_long = {}
        _peak_vol_state = {}
        _high_state = {}
        _indicator_recovered = False
        _indicator_date = current_date
        # 从快照恢复个券斜率缓存（_slope_buf_short/long, #14-15）
        _snap_recover_bond_slopes(current_date)

    # 首次恢复（_peak_vol_state/_high_state 保留原有MySQL恢复机制）
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
    """
    【已废弃】大盘扩展指标计算已合并到 compute_ext_indicators
    保留此函数以兼容旧代码，内部调用统一函数 calc_mkt_ext_indicators
    
    Returns:
        (mkt_weighted_slope_2m, mkt_change_1m_pct, mkt_price_acceleration)
    """
    global _mkt_ext_price_cache, _mkt_ext_prev_slope, _mkt_ext_date

    # 日期切换 → 清空
    if _mkt_ext_date != current_date:
        _mkt_ext_price_cache.clear()
        _mkt_ext_prev_slope = 0.0
        _mkt_ext_date = current_date

    avg_pct = float(df_now['change_pct'].mean())
    current_seconds = _time_to_seconds(time_full)

    # 追加数据（deque自动限制长度）
    _mkt_ext_price_cache.append((current_seconds, avg_pct))

    # 【重构】调用统一计算函数
    mkt_prev = _mkt_ext_prev_slope if _mkt_ext_prev_slope != 0.0 else None
    result = calc_mkt_ext_indicators(_mkt_ext_price_cache, mkt_prev)
    
    # 更新全局状态
    if result['mkt_weighted_slope_2m'] is not None:
        _mkt_ext_prev_slope = result['mkt_weighted_slope_2m']

    return (
        result.get('mkt_weighted_slope_2m', 0.0) or 0.0,
        result.get('mkt_change_1m_pct', 0.0) or 0.0,
        result.get('mkt_price_acceleration', 0.0) or 0.0
    )


def _mkt_snap_recover_market_indicators(current_date):
    """
    从快照恢复大盘斜率缓存/放量/高点状态（#8-11）

    Returns:
        True 恢复成功，False 需要走原清零逻辑
    """
    global _mkt_slope_buf_short, _mkt_slope_buf_long, _mkt_peak_vol, _mkt_high

    mkt_snap = None
    try:
        from gs2026.monitor.snapshot_cache import recover_snapshot
        mkt_snap, _bonds_snap = recover_snapshot(current_date, engine=_get_snapshot_engine())
    except Exception as e:
        logger.warning(f"[快照] 大盘指标恢复异常(降级清零): {e}")
        return False

    if not mkt_snap:
        return False

    try:
        _mkt_slope_buf_short = deque(mkt_snap.get('mss', []), maxlen=WINDOW_SHORT)
        _mkt_slope_buf_long = deque(mkt_snap.get('msl', []), maxlen=WINDOW_LONG)
        _mkt_peak_vol = {
            'max_total_amt': mkt_snap.get('pv_amt', 0),
            'pct_at_max': mkt_snap.get('pv_pct', 0.0),
        }
        _mkt_high = {'max_avg_pct': mkt_snap.get('hi_pct', -999.0)}
        logger.info(f"[快照] 大盘指标已恢复: mss={len(_mkt_slope_buf_short)}点 "
                    f"msl={len(_mkt_slope_buf_long)}点")
        return True
    except Exception as e:
        logger.warning(f"[快照] 大盘指标恢复解析失败(降级清零): {e}")
        return False


def compute_market_indicators(df_now, current_date):
    """
    计算大盘趋势指标（基于全市场平均涨跌幅）
    每tick调用一次，O(1)，零IO
    结果广播到df_now所有行（同tick所有bond共享）
    """
    global _mkt_slope_buf_short, _mkt_slope_buf_long
    global _mkt_peak_vol, _mkt_high, _mkt_date

    # 日期切换 → 清空（先尝试从快照恢复，失败才清零）
    if _mkt_date != current_date:
        if not _mkt_snap_recover_market_indicators(current_date):
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
# 【重构】缓存扩展为15分钟窗口（maxlen=300, 保留900秒）
# 注意：deque已在文件顶部导入

# 个券扩展指标缓存 - 15分钟窗口
_ext_price_cache = {}       # { bond_code: deque(maxlen=300) }  # 改为deque限制最大长度
_ext_slope_cache = {}       # { bond_code: last_slope }
_ext_date = None

# 大盘扩展指标缓存 - 15分钟窗口  
_mkt_ext_price_cache = deque(maxlen=300)  # 【修改】maxlen=60→300
_mkt_ext_prev_slope = 0.0
_mkt_ext_date = None

# ====== 大盘日内趋势环境指标（VWAP/高低点/多周期斜率）======
_mkt_trend_date = None
_mkt_trend_vwap_sum_pv = 0.0    # Σ(mkt_pct × total_amount)
_mkt_trend_vwap_sum_v = 0.0     # Σ(total_amount)
_mkt_trend_day_high = -999.0    # 日内大盘涨跌幅最高值
_mkt_trend_day_low = 999.0      # 日内大盘涨跌幅最低值
_mkt_trend_last_new_low_time = None  # 最后一次创新低的时间(秒)
_mkt_trend_slope_10m_cache = deque(maxlen=500)  # 10min EWLR缓存(750s/3s≈250, 留余量)

# ====== 大盘形态识别指标 ======
_mkt_shape_date = None
_mkt_shape_history = []         # [(time_sec, mkt_vs_open_pct), ...] 用于形态计算

# ====== 快照缓存（中间状态持久化）======
_snapshot_engine = None            # 模块级MySQL engine引用（供快照恢复/备份用）


def set_snapshot_engine(engine):
    """设置快照模块使用的MySQL engine（主循环启动时调用一次）"""
    global _snapshot_engine
    _snapshot_engine = engine


def _get_snapshot_engine():
    """获取快照用engine（未设置则返回None，走Redis-only模式）"""
    return _snapshot_engine


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


def compute_mkt_shape(dependencies: dict, history: list) -> str:
    """
    计算大盘形态（实时+回填共用）
    
    5种形态：
        - 单边上行: 开盘即最低，当前>0，回落不显著
        - 单边下行: 开盘即最高，当前<0，回升不显著
        - 低开高走: 低点不在开头，回升显著，当前>0
        - 高开低走: 高点不在开头，回落显著，当前<0
        - 横盘: 振幅<0.5%或其他条件不满足
    
    Args:
        dependencies: {'mkt_vs_open_pct': float}
        history: [{'mkt_vs_open_pct': float, 'time_sec': int}, ...]
    
    Returns:
        形态名: '单边上行'/'单边下行'/'低开高走'/'高开低走'/'横盘'
    """
    if len(history) < 10:
        return '横盘'
    
    # 合并历史和当前
    vs_values = [h.get('mkt_vs_open_pct', 0) for h in history]
    cur_pct = dependencies.get('mkt_vs_open_pct', 0)
    vs_values.append(cur_pct)
    
    high_pct = max(vs_values)
    low_pct = min(vs_values)
    total_range = high_pct - low_pct
    
    # 横盘判定
    if total_range < 0.5:
        return '横盘'
    
    # 位置计算
    n = len(vs_values)
    high_idx = vs_values.index(high_pct)
    low_idx = vs_values.index(low_pct)
    high_pos = high_idx / (n - 1) if n > 1 else 0
    low_pos = low_idx / (n - 1) if n > 1 else 0
    
    # 阈值
    sig = total_range * 0.5 if total_range > 0 else 0.001
    recovery = cur_pct - low_pct
    drawdown = high_pct - cur_pct
    
    # 形态判定
    if low_pos < 0.2 and cur_pct > 0 and drawdown < sig:
        return '单边上行'
    if high_pos < 0.2 and cur_pct < 0 and recovery < sig:
        return '单边下行'
    if low_pos > 0.2 and recovery > sig and cur_pct > 0:
        return '低开高走'
    if high_pos > 0.2 and drawdown > sig and cur_pct < 0:
        return '高开低走'
    
    return '横盘'


def compute_mkt_shape_detail(dependencies: dict, history: list) -> str:
    """
    计算大盘形态详情（实时+回填共用）
    
    Args:
        dependencies: {'mkt_vs_open_pct': float}
        history: [{'mkt_vs_open_pct': float, 'time_sec': int}, ...]
    
    Returns:
        形态详细说明
    """
    if len(history) < 10:
        return '数据不足'
    
    vs_values = [h.get('mkt_vs_open_pct', 0) for h in history]
    cur_pct = dependencies.get('mkt_vs_open_pct', 0)
    vs_values.append(cur_pct)
    
    high_pct = max(vs_values)
    low_pct = min(vs_values)
    total_range = high_pct - low_pct
    
    n = len(vs_values)
    high_idx = vs_values.index(high_pct)
    low_idx = vs_values.index(low_pct)
    high_pos = high_idx / (n - 1) if n > 1 else 0
    low_pos = low_idx / (n - 1) if n > 1 else 0
    
    sig = total_range * 0.5 if total_range > 0 else 0.001
    recovery = cur_pct - low_pct
    drawdown = high_pct - cur_pct
    
    if total_range < 0.5:
        return f'振幅{total_range:.2f}%<0.5%'
    if low_pos < 0.2 and cur_pct > 0 and drawdown < sig:
        return f'开盘即最低，当前{cur_pct:+.2f}%'
    if high_pos < 0.2 and cur_pct < 0 and recovery < sig:
        return f'开盘即最高，当前{cur_pct:+.2f}%'
    if low_pos > 0.2 and recovery > sig and cur_pct > 0:
        return f'低点在{low_pos:.0%}，回升{recovery:.2f}%'
    if high_pos > 0.2 and drawdown > sig and cur_pct < 0:
        return f'高点在{high_pos:.0%}，回落{drawdown:.2f}%'
    
    return f'高{high_pct:+.2f}% 低{low_pct:+.2f}% 收{cur_pct:+.2f}%'


def calc_bond_ext_indicators(price_history, prev_slope=None):
    """
    【统一个券扩展指标计算函数】
    
    输入: price_history - deque of (timestamp_seconds, price) 或 list
          prev_slope - 上一周期的斜率值（用于计算加速度）
    输出: dict 包含以下字段:
        - weighted_slope_2m: 2分钟加权斜率 (half_life=30s)
        - weighted_slope_5m: 5分钟加权斜率 (half_life=60s)  【渐进式】
        - weighted_slope_15m: 15分钟加权斜率 (half_life=180s) 【渐进式】
        - change_1m_pct: 1分钟价格变化率%
        - price_acceleration: 价格加速度 (当前斜率 - 上一周期斜率)
    
    设计原则:
    - 纯函数，无全局状态，可安全用于回填和实时计算
    - 零IO，纯内存计算
    - 渐进式计算：数据不足时用现有全部数据，不返回None
    
    最小数据点要求:
        - 2分钟斜率: 5个点（严格窗口）
        - 5分钟斜率: 5个点（渐进式，约15秒即可）
        - 15分钟斜率: 8个点（渐进式，约24秒即可）
    """
    import numpy as np
    
    result = {
        'weighted_slope_2m': None,
        'weighted_slope_5m': None,
        'weighted_slope_15m': None,
        'change_1m_pct': None,
        'price_acceleration': None,
    }
    
    if not price_history or len(price_history) < 2:
        return result
    
    # 转换为numpy数组
    times_arr = np.array([t for t, _ in price_history], dtype=np.float64)
    prices_arr = np.array([p for _, p in price_history], dtype=np.float64)
    current_time = times_arr[-1]
    current_price = prices_arr[-1]
    
    # === 2分钟加权斜率 (half_life=30s, 窗口120s) ===
    # 严格窗口：必须满足5个点在120秒内
    mask_2m = times_arr > current_time - 120
    if np.sum(mask_2m) >= 5:
        result['weighted_slope_2m'] = round(
            _calc_weighted_slope(prices_arr[mask_2m], times_arr[mask_2m], half_life=30), 6
        )
    
    # === 5分钟加权斜率 (half_life=60s) 【渐进式】===
    # 只要有5个点以上就用全部数据计算，不限制窗口
    if len(times_arr) >= 5:
        result['weighted_slope_5m'] = round(
            _calc_weighted_slope(prices_arr, times_arr, half_life=60), 6
        )
    
    # === 15分钟加权斜率 (half_life=180s) 【渐进式】===
    # 只要有8个点以上就用全部数据计算，不限制窗口
    if len(times_arr) >= 8:
        result['weighted_slope_15m'] = round(
            _calc_weighted_slope(prices_arr, times_arr, half_life=180), 6
        )
    
    # === 1分钟变化率 ===
    target_ts = current_time - 60
    idx_1m = np.searchsorted(times_arr, target_ts, side='left')
    if idx_1m > 0 and idx_1m < len(prices_arr):
        price_1m_ago = prices_arr[idx_1m]
        if price_1m_ago > 0:
            result['change_1m_pct'] = round((current_price - price_1m_ago) / price_1m_ago * 100, 4)
    
    # === 价格加速度 ===
    if result['weighted_slope_2m'] is not None and prev_slope is not None:
        result['price_acceleration'] = round(result['weighted_slope_2m'] - prev_slope, 6)
    
    return result


def calc_mkt_ext_indicators(mkt_price_history, prev_slope=None):
    """
    【统一大盘扩展指标计算函数】
    
    输入: mkt_price_history - deque of (timestamp_seconds, avg_pct) 或 list
          prev_slope - 上一周期的斜率值（用于计算加速度）
    输出: dict 包含以下字段:
        - mkt_weighted_slope_2m: 大盘2分钟加权斜率 (half_life=30s)
        - mkt_weighted_slope_5m: 大盘5分钟加权斜率 (half_life=60s) 【新增】
        - mkt_weighted_slope_15m: 大盘15分钟加权斜率 (half_life=180s) 【新增】
        - mkt_change_1m_pct: 大盘1分钟变化率%
        - mkt_price_acceleration: 大盘价格加速度
    
    设计原则:
    - 纯函数，无全局状态，可安全用于回填和实时计算
    - 零IO，纯内存计算
    - 与个券计算逻辑保持一致
    
    最小数据点要求:
        - 2分钟斜率: 5个点
        - 5分钟斜率: 10个点
        - 15分钟斜率: 20个点
    """
    import numpy as np
    
    result = {
        'mkt_weighted_slope_2m': None,
        'mkt_weighted_slope_5m': None,
        'mkt_weighted_slope_15m': None,
        'mkt_change_1m_pct': None,
        'mkt_price_acceleration': None,
    }
    
    if not mkt_price_history or len(mkt_price_history) < 2:
        return result
    
    # 转换为numpy数组
    times_arr = np.array([t for t, _ in mkt_price_history], dtype=np.float64)
    pcts_arr = np.array([p for _, p in mkt_price_history], dtype=np.float64)
    current_time = times_arr[-1]
    current_pct = pcts_arr[-1]
    
    # === 2分钟加权斜率 ===
    mask_2m = times_arr > current_time - 120
    if np.sum(mask_2m) >= 5:
        result['mkt_weighted_slope_2m'] = round(
            _calc_weighted_slope(pcts_arr[mask_2m], times_arr[mask_2m], half_life=30), 6
        )
    
    # === 5分钟加权斜率 【渐进式】===
    # 只要有5个点以上就用全部数据计算
    if len(times_arr) >= 5:
        result['mkt_weighted_slope_5m'] = round(
            _calc_weighted_slope(pcts_arr, times_arr, half_life=75), 6
        )
    
    # === 15分钟加权斜率 【渐进式】===
    # 只要有8个点以上就用全部数据计算
    if len(times_arr) >= 8:
        result['mkt_weighted_slope_15m'] = round(
            _calc_weighted_slope(pcts_arr, times_arr, half_life=180), 6
        )
    
    # === 1分钟变化率 ===
    target_ts = current_time - 60
    idx_1m = np.searchsorted(times_arr, target_ts, side='left')
    if idx_1m > 0 and idx_1m < len(pcts_arr):
        pct_1m_ago = pcts_arr[idx_1m]
        result['mkt_change_1m_pct'] = round(current_pct - pct_1m_ago, 4)
    
    # === 加速度 ===
    if result['mkt_weighted_slope_2m'] is not None and prev_slope is not None:
        result['mkt_price_acceleration'] = round(result['mkt_weighted_slope_2m'] - prev_slope, 6)
    
    return result


def _mkt_snap_recover_market_trend(current_date):
    """
    从快照恢复大盘趋势中间状态（VWAP/日内极值/斜率缓存/形态历史）

    恢复成功则填充内存变量，失败则归零（保持原行为）。
    仅在日期切换时调用一次。
    """
    global _mkt_trend_vwap_sum_pv, _mkt_trend_vwap_sum_v
    global _mkt_trend_day_high, _mkt_trend_day_low
    global _mkt_trend_last_new_low_time, _mkt_trend_slope_10m_cache
    global _mkt_shape_history

    mkt_snap = None
    try:
        from gs2026.monitor.snapshot_cache import recover_snapshot
        engine = _get_snapshot_engine()
        mkt_snap, _bonds_snap = recover_snapshot(current_date, engine=engine)
    except Exception as e:
        logger.warning(f"[快照] 大盘趋势恢复异常(降级归零): {e}")
        mkt_snap = None

    if mkt_snap:
        _mkt_trend_vwap_sum_pv = mkt_snap.get('vwap_pv', 0.0)
        _mkt_trend_vwap_sum_v = mkt_snap.get('vwap_v', 0.0)
        _mkt_trend_day_high = mkt_snap.get('day_hi', -999.0)
        _mkt_trend_day_low = mkt_snap.get('day_lo', 999.0)
        _mkt_trend_last_new_low_time = mkt_snap.get('nlow_t')
        _mkt_trend_slope_10m_cache = deque(
            [(int(t), p) for t, p in mkt_snap.get('s10m', [])], maxlen=500)
        _mkt_shape_history = [
            {'time_sec': int(t), 'mkt_vs_open_pct': p}
            for t, p in mkt_snap.get('shape_h', [])
        ]
        logger.info(f"[快照] 大盘趋势已恢复: vwap_v={_mkt_trend_vwap_sum_v:.0f} "
                    f"s10m={len(_mkt_trend_slope_10m_cache)}点 "
                    f"shape_h={len(_mkt_shape_history)}点")
    else:
        # 降级：原逻辑归零
        _mkt_trend_vwap_sum_pv = 0.0
        _mkt_trend_vwap_sum_v = 0.0
        _mkt_trend_day_high = -999.0
        _mkt_trend_day_low = 999.0
        _mkt_trend_last_new_low_time = None
        _mkt_trend_slope_10m_cache.clear()
        _mkt_shape_history = []


def compute_mkt_trend_indicators(df_now, time_full, current_date):
    """
    计算大盘日内趋势环境指标（每tick调用）
    
    新增指标：
        - mkt_vs_open_pct: 大盘涨跌幅（所有债券change_pct均值）
        - mkt_vwap_bias: 大盘VWAP偏离（当前涨跌幅 - 成交额加权均价）
        - mkt_weighted_slope_10m: 大盘10分钟加权斜率（EWLR half_life=150s）
        - mkt_day_position: 日内位置%（0=日低, 100=日高）
        - mkt_new_low_distance: 距上次创新低的分钟数
        - mkt_shape: 大盘形态（单边上行/单边下行/低开高走/高开低走/横盘）
        - mkt_shape_detail: 形态详细说明
    
    Returns:
        dict 包含所有趋势环境指标
    """
    global _mkt_trend_date, _mkt_trend_vwap_sum_pv, _mkt_trend_vwap_sum_v
    global _mkt_trend_day_high, _mkt_trend_day_low
    global _mkt_trend_last_new_low_time, _mkt_trend_slope_10m_cache
    global _mkt_shape_date, _mkt_shape_history

    # 日期切换 → 重置（先尝试从快照恢复，失败才归零）
    if _mkt_trend_date != current_date:
        _mkt_snap_recover_market_trend(current_date)
        _mkt_trend_date = current_date

    # 形态历史日期切换（快照恢复已在上面统一处理）
    if _mkt_shape_date != current_date:
        if not _mkt_shape_history:  # 快照未恢复出形态历史时才清空
            _mkt_shape_history = []
        _mkt_shape_date = current_date

    current_seconds = _time_to_seconds(time_full)
    
    # === mkt_vs_open_pct: 大盘涨跌幅 ===
    mkt_vs_open_pct = round(float(df_now['change_pct'].mean()), 4)

    # === mkt_vwap_bias: VWAP偏离（成交额加权）===
    total_amount = float(df_now['amount'].sum())
    _mkt_trend_vwap_sum_pv += mkt_vs_open_pct * total_amount
    _mkt_trend_vwap_sum_v += total_amount
    mkt_vwap = _mkt_trend_vwap_sum_pv / _mkt_trend_vwap_sum_v if _mkt_trend_vwap_sum_v > 0 else 0.0
    mkt_vwap_bias = round(mkt_vs_open_pct - mkt_vwap, 4)

    # === mkt_day_position: 日内位置% ===
    if mkt_vs_open_pct > _mkt_trend_day_high:
        _mkt_trend_day_high = mkt_vs_open_pct
    if mkt_vs_open_pct < _mkt_trend_day_low:
        _mkt_trend_day_low = mkt_vs_open_pct

    if _mkt_trend_day_high > _mkt_trend_day_low:
        mkt_day_position = round(
            (mkt_vs_open_pct - _mkt_trend_day_low) / (_mkt_trend_day_high - _mkt_trend_day_low) * 100, 1
        )
    else:
        mkt_day_position = 50.0

    # === mkt_new_low_distance: 距上次创新低的分钟数 ===
    if mkt_vs_open_pct <= _mkt_trend_day_low:
        _mkt_trend_last_new_low_time = current_seconds

    if _mkt_trend_last_new_low_time is not None:
        mkt_new_low_distance = round((current_seconds - _mkt_trend_last_new_low_time) / 60.0, 1)
    else:
        mkt_new_low_distance = 999.0

    # === mkt_weighted_slope_10m: EWLR half_life=150s ===
    _mkt_trend_slope_10m_cache.append((current_seconds, mkt_vs_open_pct))
    import numpy as np
    if len(_mkt_trend_slope_10m_cache) >= 5:
        pcts = np.array([p for _, p in _mkt_trend_slope_10m_cache], dtype=np.float64)
        times = np.array([t for t, _ in _mkt_trend_slope_10m_cache], dtype=np.float64)
        mkt_weighted_slope_10m = round(_calc_weighted_slope(pcts, times, half_life=150), 6)
    else:
        mkt_weighted_slope_10m = 0.0

    # === mkt_shape / mkt_shape_detail: 大盘形态 ===
    # 添加当前点到历史
    _mkt_shape_history.append({
        'time_sec': current_seconds,
        'mkt_vs_open_pct': mkt_vs_open_pct
    })
    
    # 构建依赖和历史用于计算
    deps = {'mkt_vs_open_pct': mkt_vs_open_pct}
    history_for_calc = _mkt_shape_history[:-1] if len(_mkt_shape_history) > 1 else []
    
    mkt_shape = compute_mkt_shape(deps, history_for_calc)
    mkt_shape_detail = compute_mkt_shape_detail(deps, history_for_calc)

    return {
        'mkt_vs_open_pct': mkt_vs_open_pct,
        'mkt_vwap_bias': mkt_vwap_bias,
        'mkt_weighted_slope_10m': mkt_weighted_slope_10m,
        'mkt_day_position': mkt_day_position,
        'mkt_new_low_distance': mkt_new_low_distance,
        'mkt_shape': mkt_shape,
        'mkt_shape_detail': mkt_shape_detail,
    }


def _snap_recover_bond_ext(current_date):
    """
    从快照恢复个券扩展指标缓存 _ext_price_cache/_ext_slope_cache（#18-19）

    _ext_price_cache[code] = deque([(seconds, price), ...], maxlen=300)
    _ext_slope_cache[code] = last_slope(float)
    恢复失败时保持空dict（原行为）。
    """
    global _ext_price_cache, _ext_slope_cache

    bonds_snap = _get_pending_bonds_snapshot(current_date)
    if not bonds_snap:
        return

    try:
        cnt = 0
        for code, data in bonds_snap.items():
            epc = data.get('epc')
            if epc:
                _ext_price_cache[code] = deque(
                    [(int(t), float(p)) for t, p in epc], maxlen=300)
            esl = data.get('esl')
            if esl is not None:
                _ext_slope_cache[code] = esl
            cnt += 1
        logger.info(f"[快照] 个券扩展指标缓存已恢复: {cnt}只债券")
    except Exception as e:
        logger.warning(f"[快照] 个券扩展指标恢复解析失败(降级): {e}")


def compute_ext_indicators(df_now, time_full, current_date):
    """
    计算扩展指标（纯内存，零IO）- 【重构】调用统一函数 calc_bond_ext_indicators
    
    输出字段:
        - weighted_slope_2m: 2分钟加权斜率
        - weighted_slope_5m: 5分钟加权斜率 【新增】
        - weighted_slope_15m: 15分钟加权斜率 【新增】
        - change_1m_pct: 1分钟变化率
        - price_acceleration: 价格加速度
        - mkt_weighted_slope_2m: 大盘2分钟加权斜率
        - mkt_weighted_slope_5m: 大盘5分钟加权斜率 【新增】
        - mkt_weighted_slope_15m: 大盘15分钟加权斜率 【新增】
        - mkt_change_1m_pct: 大盘1分钟变化率
        - mkt_price_acceleration: 大盘价格加速度
    """
    global _ext_price_cache, _ext_slope_cache, _ext_date, _mkt_ext_price_cache, _mkt_ext_prev_slope
    
    # 日期切换 → 清空（先尝试从快照恢复扩展指标缓存 #18-19）
    if _ext_date != current_date:
        _ext_price_cache = {}
        _ext_slope_cache = {}
        _ext_date = current_date
        _snap_recover_bond_ext(current_date)
    
    code_col = 'bond_code' if 'bond_code' in df_now.columns else 'code'
    current_seconds = _time_to_seconds(time_full)
    
    # 【重构】使用deque存储，自动限制长度
    ext_list = []
    for _, row in df_now.iterrows():
        code = row[code_col]
        price = float(row['price'])
        
        # 初始化deque（maxlen=300，保留15分钟）
        if code not in _ext_price_cache:
            _ext_price_cache[code] = deque(maxlen=300)
        
        # 追加新数据
        _ext_price_cache[code].append((current_seconds, price))
        
        # 【重构】调用统一计算函数
        prev_slope = _ext_slope_cache.get(code)
        ext = calc_bond_ext_indicators(_ext_price_cache[code], prev_slope)
        
        # 更新prev_slope用于下次计算加速度
        if ext['weighted_slope_2m'] is not None:
            _ext_slope_cache[code] = ext['weighted_slope_2m']
        
        ext_list.append(ext)
    
    # 【重构】调用统一大盘计算函数
    # 计算市场平均涨跌幅
    avg_pct = float(df_now['change_pct'].mean())
    _mkt_ext_price_cache.append((current_seconds, avg_pct))
    
    mkt_prev = _mkt_ext_prev_slope if _mkt_ext_prev_slope != 0.0 else None
    mkt_ext = calc_mkt_ext_indicators(_mkt_ext_price_cache, mkt_prev)
    
    if mkt_ext['mkt_weighted_slope_2m'] is not None:
        _mkt_ext_prev_slope = mkt_ext['mkt_weighted_slope_2m']
    
    # 计算大盘日内趋势环境指标
    mkt_trend = compute_mkt_trend_indicators(df_now, time_full, current_date)
    
    # 合并个券和大盘指标
    import json
    ext_indicators_list = []
    for ext in ext_list:
        combined = {**ext, **mkt_ext, **mkt_trend}
        ext_indicators_list.append(json.dumps(combined, ensure_ascii=False))
    
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

def get_bond_tdx(filter_valid=True):
    """
    通过pytdx获取可转债实时行情，转换为统一结构（3秒级实时）
    
    优化点：
    1. 连接复用 - 使用模块级连接缓存
    2. 代码缓存 - 债券代码列表1小时缓存
    3. 价格精度 - 修正TDX价格字段（除以100）
    4. 有效过滤 - 只返回price>0且volume>0的数据
    5. 3秒级实时 - get_security_quotes直接返回当前快照
    
    Args:
        filter_valid: 是否只返回有效数据（价格>0且成交量>0）
    
    Returns:
        DataFrame: 统一结构的债券数据
    """
    try:
        # 获取或复用连接
        api = _get_tdx_api()
        if not api:
            logger.warning("[tdx] 无法获取API连接")
            return pd.DataFrame()
        
        # 获取债券代码（带缓存）
        bonds = _get_bond_codes_cached(api)
        if not bonds:
            logger.warning("[tdx] 无债券代码")
            return pd.DataFrame()
        
        # 批量获取行情（每次80只）- 3秒级实时快照
        all_quotes = []
        for i in range(0, len(bonds), 80):
            batch = bonds[i:i+80]
            params = [(m, c) for m, c, n in batch]
            try:
                # 请求限流，防止频繁调用被封
                _tdx_rate_limit()
                quotes = api.get_security_quotes(params)
                if quotes:
                    all_quotes.extend(quotes)
            except Exception as e:
                logger.warning(f"[tdx] 批量获取行情失败: {e}")
                continue
        
        # 名称映射
        name_map = {c: n for m, c, n in bonds}
        
        # 转换为统一结构（价格精度修正：除以100）
        rows = []
        valid_count = 0
        invalid_count = 0
        
        for q in all_quotes:
            code = q.get('code', '')
            
            # 价格精度修正：TDX返回的价格是实际值的100倍
            price = q.get('price', 0) / 100
            pre_close = q.get('last_close', 0) / 100
            open_price = q.get('open', 0) / 100
            high = q.get('high', 0) / 100
            low = q.get('low', 0) / 100
            volume = q.get('vol', 0)
            amount = q.get('amount', 0)
            
            # 过滤无效数据（停牌/未交易）
            if filter_valid and (price <= 0 or volume <= 0):
                invalid_count += 1
                continue
            
            valid_count += 1
            
            # 计算涨跌额和涨跌幅
            change = price - pre_close
            change_pct = 0
            if pre_close and pre_close > 0:
                change_pct = (price - pre_close) / pre_close * 100
            
            rows.append({
                'bond_code': code,
                'bond_name': name_map.get(code, ''),
                'price': price,
                'open': open_price,
                'high': high,
                'low': low,
                'pre_close': pre_close,
                'volume': volume,
                'amount': amount,
                'change': round(change, 4),
                'change_pct': round(change_pct, 4),
            })
        
        df = pd.DataFrame(rows)
        
        if filter_valid:
            logger.info(f"[tdx] 获取{len(df)}只有效转债（过滤{invalid_count}只无效）")
        else:
            logger.info(f"[tdx] 获取{len(df)}只转债")
        
        return df
        
    except Exception as e:
        logger.error(f"[tdx] 获取行情失败: {e}")
        # 重置连接状态，下次会重新连接
        global _tdx_connected
        _tdx_connected = False
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
        'tdx': get_bond_tdx,  # ← 加这一行
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
        # 0. 展开 ext_indicators JSON 为独立列（使用统一函数）
        from gs2026.dashboard2.services.quant_screen_core import expand_ext_indicators
        df_now = expand_ext_indicators(df_now)

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
                
                # ========== 交易助手：取1分钟成交额最高的命中触发 ==========
                if _trader_enabled and new_matches:
                    # 从new_matches中找min1_amount最高的那个
                    best_match = None
                    best_amount = -1
                    for m in new_matches[:20]:
                        code = m.get('bond_code', '')
                        row = df_now[df_now['bond_code'] == code]
                        amt = float(row['min1_amount'].iloc[0]) if len(row) > 0 and 'min1_amount' in row.columns else 0
                        if amt > best_amount:
                            best_amount = amt
                            best_match = m
                    
                    if best_match:
                        # 异步调用，不阻塞主循环
                        import threading
                        _match = best_match  # 闭包捕获
                        def _trigger_trade():
                            try:
                                bond_code = _match.get('bond_code', '')
                                bond_name = _match.get('bond_name', '')
                                scheme_name = _match.get('scheme_names', [''])[0]
                                trader_on_hit(bond_code, bond_name, scheme_name=scheme_name)
                            except Exception as e:
                                logger.warning(f"[trader] {bond_code} 调用失败: {e}")
                        threading.Thread(target=_trigger_trade, daemon=True).start()
                # ==========================================================
                
                # ========== 自动止盈止损：所有命中信号推送到自动交易系统（新增）=========
                if _auto_trader_enabled and new_matches:
                    for m in new_matches[:5]:  # 最多前5个命中
                        try:
                            bond_code = m.get('bond_code', '')
                            bond_name = m.get('bond_name', '')
                            hit_price = m.get('price', 0)  # 修正：字段名是'price'不是'hit_price'
                            
                            # 从方案缓存中获取止盈止损参数
                            scheme_name = m.get('scheme_names', [''])[0]
                            scheme_config = {}
                            for s in _qs_scheme_cache:
                                if s.get('name') == scheme_name:
                                    scheme_config = s
                                    break
                            
                            scheme_detail = {
                                'name': scheme_name,
                                'take_profit': scheme_config.get('take_profit', 3.0),
                                'stop_loss': scheme_config.get('stop_loss', 2.0),
                                'max_hold_time': scheme_config.get('max_hold_time', 30),
                                'price_offset': scheme_config.get('price_offset', 0),
                                'offset_mode': scheme_config.get('offset_mode', 'fixed'),
                            }
                            lots = 1  # 默认1手
                            
                            # 通过HTTP推送到交易server(独立进程)
                            import requests as _req
                            _req.post(
                                'http://127.0.0.1:8081/api/auto_trade/hit',
                                json={
                                    'code': bond_code,
                                    'name': bond_name,
                                    'price': hit_price,
                                    'scheme': scheme_detail,
                                    'lots': lots,
                                },
                                timeout=3
                            )
                            logger.info(f"[auto_trader] 推送命中: {bond_code}")
                        except Exception as e:
                            logger.info(f"[auto_trader] 推送失败: {e}")
                # ==========================================================

    except Exception as e:
        logger.warning(f"[量化选债] 执行失败(不影响主流程): {e}")

    # 退出跟踪：检查未平仓信号（与回测Phase 3完全相同的TP/SL/超时逻辑）
    try:
        _track_pending_exits(df_now, date_str, time_full, engine)
    except Exception as e:
        logger.warning(f"[量化选债] 退出跟踪失败(不影响主流程): {e}")


def _track_pending_exits(df_now, date_str, time_full, engine):
    """
    跟踪未结算命中记录的触发判定（前端计算方案）
    
    核心逻辑：
    - 只查询未结算记录（is_locked=0）
    - 只判断触发条件，不UPDATE持仓中记录
    - 只UPDATE新触发的记录（设置exit_*, is_locked等）
    - 持仓中的浮动收益由前端实时计算
    """
    # 1. 只加载未结算记录（大幅减小查询量）
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, bond_code, tick_time, entry_price,
                   take_profit_price, stop_loss_price, max_hold_time
            FROM quant_screen_hits
            WHERE trade_date = :date AND is_locked = 0
        """), {'date': date_str})
        pending = result.fetchall()

    if not pending:
        return

    # 2. 构建当前价格字典
    price_map = {}
    for _, row in df_now.iterrows():
        code = row.get('bond_code', '')
        price_map[code] = float(row.get('price', 0))

    # 3. 当前时间转秒
    current_seconds = _time_to_seconds(time_full)
    time_clean = time_full.replace(':', '')

    # 4. 只处理触发判定（不处理持仓中）
    updates = []  # 只收集新触发的

    for row in pending:
        signal_id = row.id
        bond_code = row.bond_code
        entry_price = float(row.entry_price) if row.entry_price else 0
        tick_time_str = str(row.tick_time) if row.tick_time else ''

        if entry_price <= 0:
            continue

        # 获取当前价格
        current_price = price_map.get(bond_code)
        if current_price is None or current_price <= 0:
            continue

        # 入场时间（秒）
        entry_seconds = _time_to_seconds(tick_time_str)

        # 止盈价 / 止损价
        tp_price = float(row.take_profit_price) if row.take_profit_price else None
        sl_price = float(row.stop_loss_price) if row.stop_loss_price else None
        
        max_hold = int(row.max_hold_time) if row.max_hold_time else 30
        deadline_seconds = entry_seconds + max_hold * 60
        hold_seconds = current_seconds - entry_seconds

        # 【判断触发条件】（按优先级：止盈 > 止损 > 超时）
        
        # ① 止盈触发
        if tp_price and current_price >= tp_price:
            final_return_pct = round((tp_price - entry_price) / entry_price * 100, 4)
            updates.append({
                'id': signal_id,
                'exit_price': round(tp_price, 3),
                'exit_time': time_clean,
                'final_return_pct': final_return_pct,
                'hold_seconds': hold_seconds,
                'signal_status': 'profited',
                'lock_reason': 'take_profit'
            })
        
        # ② 止损触发
        elif sl_price and current_price <= sl_price:
            final_return_pct = round((sl_price - entry_price) / entry_price * 100, 4)
            updates.append({
                'id': signal_id,
                'exit_price': round(sl_price, 3),
                'exit_time': time_clean,
                'final_return_pct': final_return_pct,
                'hold_seconds': hold_seconds,
                'signal_status': 'stopped',
                'lock_reason': 'stop_loss'
            })
        
        # ③ 超时触发
        elif current_seconds >= deadline_seconds:
            final_return_pct = round((current_price - entry_price) / entry_price * 100, 4)
            updates.append({
                'id': signal_id,
                'exit_price': round(current_price, 3),
                'exit_time': time_clean,
                'final_return_pct': final_return_pct,
                'hold_seconds': max_hold * 60,
                'signal_status': 'timeout',
                'lock_reason': 'max_time'
            })
        
        # ④ 未触发：持仓中 → 【不UPDATE】，前端自己算
        # 什么都不做，继续下一个

    # 5. 只UPDATE新触发的记录（通常很少）
    if updates:
        with engine.connect() as conn:
            for u in updates:
                conn.execute(text("""
                    UPDATE quant_screen_hits
                    SET exit_price = :exit_price,
                        exit_time = :exit_time,
                        final_return_pct = :final_return_pct,
                        hold_seconds = :hold_seconds,
                        signal_status = :signal_status,
                        is_locked = 1,
                        locked_at = NOW(),
                        lock_reason = :lock_reason,
                        updated_at = NOW()
                    WHERE id = :id
                """), u)
            conn.commit()
        
        # 简洁日志
        profited = sum(1 for u in updates if u['lock_reason'] == 'take_profit')
        stopped = sum(1 for u in updates if u['lock_reason'] == 'stop_loss')
        timeout = sum(1 for u in updates if u['lock_reason'] == 'max_time')
        logger.info(f"[收益跟踪] 新触发{len(updates)}条: 止盈{profited}/止损{stopped}/超时{timeout}")


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
    import time
    tick_start = time.time()  # 【新增】tick开始时间
    
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    # 【新增】首次设置快照engine（幂等，供中间状态持久化/恢复用）
    if _get_snapshot_engine() is None:
        set_snapshot_engine(engine)

    # ========== 阶段1：数据采集 ==========
    t1 = time.time()
    df_now = get_bond_with_fallback(time_full)
    t1_elapsed = (time.time() - t1) * 1000
    if df_now.empty:
        return

    df_now['time'] = time_full

    # ========== 阶段2：数据清洗（实体红绿柱等） ==========
    t2 = time.time()

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

    t2_elapsed = (time.time() - t2) * 1000

    # ========== 阶段3：指标计算（1分钟字段、趋势指标、大盘指标、扩展指标） ==========
    t3 = time.time()

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

    t3_elapsed = (time.time() - t3) * 1000

    # ========== 阶段4：量化选债筛选 ==========
    t4 = time.time()

    # 【新增】量化选债自动筛选（参考买点候选模式：Redis快照+MySQL历史）
    run_quant_screen_on_tick(df_now, date_str, time_full, engine)

    t4_elapsed = (time.time() - t4) * 1000

    # ========== 阶段5：数据存储 ==========
    t5 = time.time()

    # 【修复】删除展开后的独立扩展指标列，避免与 ext_indicators JSON 列重复存储
    # 这些列由 expand_ext_indicators() 展开用于量化选债筛选，但不需要持久化到数据库
    # 【方案B】从 BACKTEST_FIELDS 动态获取所有 json_field 字段，字段定义单一来源，
    #          以后新增扩展字段无需再修改此处
    from gs2026.dashboard2.services.backtest_bond import BACKTEST_FIELDS
    ext_cols_to_drop = [f['name'] for f in BACKTEST_FIELDS if f.get('json_field')]
    for col in ext_cols_to_drop:
        if col in df_now.columns:
            del df_now[col]

    # 存储债券实时数据
    msac.save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)

    # 【新增】写入Redis缓存（可插拔，异步，失败不影响主流程）
    if _redis_cache_available and is_cache_enabled():
        _write_to_redis_cache(df_now, time_full, date_str)

    # 【新增】收集并存储中间状态快照（异步，失败不影响主流程）
    _save_intermediate_snapshot(date_str, time_full)

    t5_elapsed = (time.time() - t5) * 1000

    # ========== 阶段6：大盘强度计算 ==========
    t6 = time.time()

    # 获取前30秒的数据（从 Redis 加载）
    # 早盘特殊处理：9:30:00-9:30:15使用最早时间戳作为基准
    from datetime import time as dt_time
    time_obj = loop_start.time()
    is_early_morning = (dt_time(9, 30, 0) <= time_obj < dt_time(9, 30, 15))
    
    if is_early_morning:
        # 早盘9:30:00-9:30:15：获取最早时间戳作为基准
        # 【修复】跳过集合竞价数据（09:30之前的时间点债券无成交量，会导致zf_30/momentum为NaN）
        # 【问题5】统一走 get_early_morning_baseline（min_time="09:30:00"保持原行为：排除竞价）
        df_prev, earliest_time = redis_util.get_early_morning_baseline(sssj_table, min_time="09:30:00")
        if earliest_time:
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

    t6_elapsed = (time.time() - t6) * 1000

    # ========== 【性能监控】Tick周期总计 ==========
    tick_total = (time.time() - tick_start) * 1000
    logger.info(f"[债券-{time_full}] Tick总计: {tick_total:.1f}ms | "
                f"采集{t1_elapsed:.1f}ms | 清洗{t2_elapsed:.1f}ms | "
                f"指标{t3_elapsed:.1f}ms | 选债{t4_elapsed:.1f}ms | "
                f"保存{t5_elapsed:.1f}ms | 大盘{t6_elapsed:.1f}ms")

    # ========== 阶段7: 自动止盈止损持仓监控（新增）=========
    if _auto_trader_enabled:
        try:
            auto_trader_on_tick(df_now)
        except Exception as e:
            logger.debug(f"[auto_trader] on_tick异常: {e}")


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


# ========== 中间状态快照（持久化/恢复）==========
from concurrent.futures import ThreadPoolExecutor as _SnapThreadPool
_snapshot_executor = _SnapThreadPool(max_workers=1, thread_name_prefix="snapshot")
_snapshot_pending_future = None  # 【问题4】背压保护：上一快照存储的Future


def _collect_mkt_snapshot():
    """收集大盘中间状态（14字段，纯内存操作）"""
    return {
        'vwap_pv': _mkt_trend_vwap_sum_pv,
        'vwap_v': _mkt_trend_vwap_sum_v,
        'day_hi': _mkt_trend_day_high,
        'day_lo': _mkt_trend_day_low,
        'nlow_t': _mkt_trend_last_new_low_time,
        's10m': [[int(t), p] for t, p in _mkt_trend_slope_10m_cache],
        'shape_h': [[h['time_sec'], h['mkt_vs_open_pct']] for h in _mkt_shape_history[-500:]],
        'mss': list(_mkt_slope_buf_short),
        'msl': list(_mkt_slope_buf_long),
        'pv_amt': _mkt_peak_vol.get('max_total_amt', 0),
        'pv_pct': _mkt_peak_vol.get('pct_at_max', 0.0),
        'hi_pct': _mkt_high.get('max_avg_pct', -999.0),
        'ext_pc': [[int(t), p] for t, p in _mkt_ext_price_cache],
        'ext_ps': _mkt_ext_prev_slope,
    }


def _collect_bonds_snapshot():
    """收集个券中间状态（400只 × 7字段，纯内存操作）"""
    bonds = {}
    for code in _slope_buf_short.keys():
        pv = _peak_vol_state.get(code, {})
        hs = _high_state.get(code, {})
        bonds[code] = {
            'ss': list(_slope_buf_short.get(code, [])),
            'sl': list(_slope_buf_long.get(code, [])),
            'pamt': pv.get('max_amount', 0),
            'pprc': pv.get('price_at_max', 0),
            'hmax': hs.get('max_cpct', 0),
            'epc': [[int(t), p] for t, p in _ext_price_cache.get(code, [])],
            'esl': _ext_slope_cache.get(code, 0.0),
        }
    return bonds


def _save_intermediate_snapshot(date_str, time_full):
    """
    收集并异步存储中间状态快照

    在主tick末尾调用。收集为纯内存操作(<3ms)，存储提交到线程池不阻塞。
    任何异常均被消化，不影响主流程。

    【问题4优化】背压保护：若上一次快照存储仍在进行(线程池积压)，
    则跳过本tick收集，避免收集开销叠加+任务堆积。不影响计算逻辑，
    仅影响重启恢复精度(最多丢1-2tick，Redis覆盖写下tick即补齐)。
    """
    global _snapshot_pending_future
    try:
        # 背压检查：上一快照未完成则跳过本次收集
        pending = globals().get('_snapshot_pending_future')
        if pending is not None and not pending.done():
            return

        time_sec = _time_to_seconds(time_full)
        mkt_snap = _collect_mkt_snapshot()
        bonds_snap = _collect_bonds_snapshot()
        from gs2026.monitor.snapshot_cache import save_snapshot
        _snapshot_pending_future = _snapshot_executor.submit(
            save_snapshot, date_str, time_sec, mkt_snap, bonds_snap, _get_snapshot_engine()
        )
    except Exception as e:
        logger.warning(f"[快照] 收集/提交失败(不影响主流程): {e}")


# ========== Redis缓存辅助函数（可插拔）==========
def _write_to_redis_cache(df_now: pd.DataFrame, time_full: str, date_str: str):
    """
    批量Pipeline写入Redis（单线程，单次网络往返）
    
    优化：300个债券数据通过1个Pipeline执行，
    而非300个独立线程各自发起网络请求。
    
    性能：300债券 ≈ 5-10ms（1次RTT），而非300次RTT。
    """
    import json
    import threading

    def do_batch_write():
        try:
            from gs2026.utils.redis_util import _get_redis_client
            r = _get_redis_client()
            if not r:
                return

            index_key = f"bond:tick:index:{date_str}"
            expire_sec = 16 * 3600  # 16小时

            pipe = r.pipeline()
            count = 0

            for _, row in df_now.iterrows():
                bond_code = row.get('bond_code') or row.get('code')
                if not bond_code:
                    continue
                bond_code = str(bond_code)

                key = f"bond:tick:{bond_code}:{date_str}"
                data = json.dumps({
                    'time': time_full,
                    'price': float(row.get('price', 0)),
                    'change_pct': float(row.get('change_pct', 0)),
                    'amount': float(row.get('amount', 0)),
                    'volume': float(row.get('volume', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'open': float(row.get('open', 0)),
                    'pre_close': float(row.get('pre_close', 0)),
                }, ensure_ascii=False)

                pipe.hset(key, time_full, data)
                pipe.sadd(index_key, bond_code)
                pipe.expire(key, expire_sec)
                count += 1

            pipe.expire(index_key, expire_sec)
            pipe.execute()  # 单次网络往返

        except Exception as e:
            logger.debug(f"[RedisCache] Pipeline写入异常: {e}")

    # 单个异步线程执行批量写入（主流程零阻塞）
    threading.Thread(target=do_batch_write, daemon=True, name="RedisTickBatch").start()
# ========== Redis缓存辅助函数结束 ==========


if __name__ == "__main__":
    msac.run_monitor_loop_synced(deal_zq_works, interval=INTERVAL)


# ====== JSON字段注册表（供回填自动识别）======
JSON_FIELD_REGISTRY = {
    'mkt_shape': {
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_shape',
        'needs_history': True,
        'state_vars': ['_mkt_shape_history'],
    },
    'mkt_shape_detail': {
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_shape_detail',
        'needs_history': True,
        'state_vars': ['_mkt_shape_history'],
    },
}


def get_json_field_registry():
    """
    获取JSON字段注册表
    
    供 compute_engine.py 和 backfill_json_fields.py 自动读取
    
    Returns:
        dict: 字段注册表
    """
    return JSON_FIELD_REGISTRY


def compute_json_field(field_name: str, dependencies: dict, history: list = None):
    """
    通用JSON字段计算接口
    
    供 compute_engine.py 统一调用，无需为每个字段写单独方法
    
    Args:
        field_name: 字段名
        dependencies: 依赖字段值 {'mkt_vs_open_pct': 1.5, ...}
        history: 历史数据（如果needs_history=True）
    
    Returns:
        字段值
    
    Raises:
        ValueError: 字段不存在或计算函数不存在
    """
    registry = get_json_field_registry()
    if field_name not in registry:
        raise ValueError(f"未知字段: {field_name}")
    
    field_config = registry[field_name]
    computer_name = field_config['computer']
    
    # 获取计算函数
    computer = globals().get(computer_name)
    if computer is None:
        raise ValueError(f"计算函数不存在: {computer_name}")
    
    # 调用计算
    if field_config.get('needs_history') and history is not None:
        return computer(dependencies, history)
    else:
        return computer(dependencies)

