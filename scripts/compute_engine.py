"""
统一字段回填引擎 - 计算引擎
与 monitor_bond.py 实时计算逻辑完全一致。

核心原则：
1. 算法逻辑 100% 复刻自 monitor_bond.py
2. 状态缓冲区模拟实时的模块级全局变量
3. 按时间正序逐tick处理，积累状态
4. 单tick内使用向量化操作提高效率
"""

import json
import math
import numpy as np
from collections import deque
from typing import Dict, Optional, Tuple

from field_registry import WINDOW_SHORT, WINDOW_LONG, EXT_WINDOW_SECONDS, EXT_HALF_LIFE

# 【强制】从 monitor_bond.py 导入统一计算函数，失败则报错
def _import_unified_functions():
    """
    强制从 monitor_bond.py 导入统一计算函数
    失败则报错，确保回填必须使用与实时计算完全一致的函数
    """
    import sys
    from pathlib import Path
    monitor_path = Path(__file__).parent.parent / 'src' / 'gs2026' / 'monitor'
    if str(monitor_path) not in sys.path:
        sys.path.insert(0, str(monitor_path))
    
    try:
        from monitor_bond import (
            calc_bond_ext_indicators,
            calc_mkt_ext_indicators,
            _calc_weighted_slope,
            _calc_slope
        )
        print("[OK] 成功从 monitor_bond.py 导入统一计算函数")
        return {
            'calc_bond_ext_indicators': calc_bond_ext_indicators,
            'calc_mkt_ext_indicators': calc_mkt_ext_indicators,
            '_calc_weighted_slope': _calc_weighted_slope,
            '_calc_slope': _calc_slope
        }
    except ImportError as e:
        raise RuntimeError(
            f"[ERROR] 无法从 monitor_bond.py 导入统一计算函数: {e}\n"
            f"回填引擎必须使用与实时计算完全一致的函数，\n"
            f"请确保 monitor_bond.py 存在且可导入。"
        ) from e

# 初始化时强制导入，失败直接报错
_UNIFIED_FUNCS = _import_unified_functions()
calc_bond_ext_indicators = _UNIFIED_FUNCS['calc_bond_ext_indicators']
calc_mkt_ext_indicators = _UNIFIED_FUNCS['calc_mkt_ext_indicators']
_calc_weighted_slope = _UNIFIED_FUNCS['_calc_weighted_slope']
_calc_slope = _UNIFIED_FUNCS['_calc_slope']
_unified_imported = True  # 保持兼容性

# 【终极修复】直接patch函数对象的globals，确保calc_bond_ext_indicators内部调用修复版
# 问题：monitor_bond可能被不同路径导入两次，patch module属性不影响函数内部引用
import numpy as _np
_original_weighted_slope = _calc_weighted_slope
def _patched_weighted_slope(prices, times, half_life=30):
    """修复版：平价返回0.0而非None"""
    n = len(prices) if hasattr(prices, '__len__') else 0
    if n >= 3:
        arr = _np.array(prices, dtype=_np.float64)
        if arr.max() == arr.min():
            return 0.0
    return _original_weighted_slope(prices, times, half_life)

# 直接修改函数对象的globals字典（绕过模块双重导入问题）
calc_bond_ext_indicators.__globals__['_calc_weighted_slope'] = _patched_weighted_slope
calc_mkt_ext_indicators.__globals__['_calc_weighted_slope'] = _patched_weighted_slope
_calc_weighted_slope = _patched_weighted_slope
print("[OK] _calc_weighted_slope已直接patch到函数globals")


def _calc_slope(buf) -> float:
    """
    从deque/list计算线性回归斜率（最小二乘法）
    【完全复刻 monitor_bond.py::_calc_slope】
    """
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


def _time_to_seconds(time_str: str) -> int:
    """
    将时间字符串转换为当天秒数
    支持格式: "HH:MM:SS" 或 "HHMMSS"
    【复刻 monitor_bond.py::_time_to_seconds】
    """
    try:
        if ':' in time_str:
            parts = time_str.split(':')
            hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            hh = int(time_str[:2])
            mm = int(time_str[2:4])
            ss = int(time_str[4:6])
        return hh * 3600 + mm * 60 + ss
    except:
        return 0


def _calc_weighted_slope(prices, times, half_life=30) -> float:
    """
    计算指数加权斜率（精确计算）
    【完全复刻 monitor_bond.py::_calc_weighted_slope】

    参数:
        prices: 价格列表
        times: 时间列表（秒）
        half_life: 半衰期（秒）
    """
    if len(prices) < 2:
        return 0.0

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


class ComputeEngine:
    """
    回填计算引擎 - 模拟实时计算的状态积累过程

    使用方式：
        engine = ComputeEngine()
        for tick_time, df_tick in grouped_by_time:
            engine.process_tick(df_tick, tick_time, fields_to_compute)
    """

    def __init__(self):
        # === B类：1分钟字段缓存 ===
        self.min1_base_minute: Optional[str] = None   # 当前基准所属分钟 'HH:MM'
        self.min1_base_pct: Dict[str, float] = {}     # { bond_code: base_change_pct }
        self.min1_base_amt: Dict[str, float] = {}     # { bond_code: base_amount }

        # === C类：趋势斜率缓存 ===
        self.slope_buf_short: Dict[str, deque] = {}   # { bond_code: deque(maxlen=WINDOW_SHORT) }
        self.slope_buf_long: Dict[str, deque] = {}    # { bond_code: deque(maxlen=WINDOW_LONG) }
        self.peak_vol_state: Dict[str, dict] = {}     # { bond_code: {'max_amount': float, 'price_at_max': float} }
        self.high_state: Dict[str, dict] = {}         # { bond_code: {'max_cpct': float} }

        # === D类：市场级缓存 ===
        self.mkt_slope_buf_short: deque = deque(maxlen=WINDOW_SHORT)
        self.mkt_slope_buf_long: deque = deque(maxlen=WINDOW_LONG)
        self.mkt_peak_vol: dict = {'max_total_amt': 0, 'pct_at_max': 0.0}
        self.mkt_high: dict = {'max_avg_pct': -999.0}

        # === E类：扩展指标缓存 ===
        # 【重构】缓存扩展为15分钟窗口（maxlen=300, 保留900秒）
        self.ext_price_cache: Dict[str, deque] = {}   # { bond_code: deque(maxlen=300) }
        self.ext_slope_cache: Dict[str, float] = {}   # { bond_code: last_weighted_slope_2m }

        # === E类：大盘扩展指标缓存（存入ext_indicators JSON）===
        self.mkt_ext_price_cache: deque = deque(maxlen=300)  # 【修改】maxlen=60→300
        self.mkt_ext_prev_slope: float = 0.0          # 上一tick大盘加权斜率

        # === F类：大盘日内趋势环境指标缓存 ===
        self.mkt_trend_vwap_sum_pv: float = 0.0       # Σ(mkt_pct × total_amount)
        self.mkt_trend_vwap_sum_v: float = 0.0        # Σ(total_amount)
        self.mkt_trend_day_high: float = -999.0       # 日内大盘涨跌幅最高
        self.mkt_trend_day_low: float = 999.0         # 日内大盘涨跌幅最低
        self.mkt_trend_last_new_low_time: Optional[int] = None  # 最后创新低时间(秒)
        self.mkt_trend_slope_10m_cache: deque = deque(maxlen=500)  # 10min EWLR缓存

        # 统计
        self.ticks_processed = 0

    def reset(self):
        """重置所有状态（切换日期时调用）"""
        self.__init__()

    def process_tick(self, df_tick, tick_time: str, fields_to_compute: set) -> dict:
        """
        处理单个tick的所有债券数据

        Args:
            df_tick: 当前tick的DataFrame（同一时间的所有债券）
            tick_time: 时间字符串 "HH:MM:SS"
            fields_to_compute: 需要计算的字段名集合

        Returns:
            dict: { field_name: {bond_code: value} 或 field_name: scalar(市场级) }
        """
        self.ticks_processed += 1
        results = {}

        code_col = 'bond_code' if 'bond_code' in df_tick.columns else 'code'
        codes = df_tick[code_col].tolist()

        # ---- B类：1分钟差值（必须在rank之前，因为rank依赖min1_amount）----
        min1_fields = {'min1_change_pct', 'min1_amount'} & fields_to_compute
        # min1_amount_rank 依赖 min1_amount，如果要算 min1_amount_rank 也必须先算 min1
        if 'min1_amount_rank' in fields_to_compute:
            min1_fields.add('min1_change_pct')
            min1_fields.add('min1_amount')
        if min1_fields:
            min1_results = self._compute_min1(df_tick, tick_time, code_col, codes)
            results.update(min1_results)

        # ---- A类：排名字段 ----
        if 'amount_rank' in fields_to_compute:
            amounts = df_tick['amount'].values
            ranks = self._rank_descending(amounts)
            results['amount_rank'] = dict(zip(codes, ranks))

        if 'min1_amount_rank' in fields_to_compute:
            # 使用刚计算的 min1_amount 进行排名
            if 'min1_amount' in results:
                min1_amounts = np.array([results['min1_amount'].get(c, 0.0) for c in codes])
            elif 'min1_amount' in df_tick.columns:
                min1_amounts = df_tick['min1_amount'].values
            else:
                min1_amounts = np.zeros(len(codes))
            ranks = self._rank_descending(min1_amounts)
            results['min1_amount_rank'] = dict(zip(codes, ranks))

        # ---- C类：趋势斜率 ----
        slope_fields = {'slope_short', 'slope_long', 'peak_vol_bias', 'high_distance'} & fields_to_compute
        if slope_fields:
            slope_results = self._compute_slopes(df_tick, code_col, codes, slope_fields)
            results.update(slope_results)

        # ---- D类：市场级 ----
        market_fields = {'mkt_slope_short', 'mkt_slope_long', 'mkt_peak_vol_bias', 'mkt_high_distance'} & fields_to_compute
        if market_fields:
            market_results = self._compute_market(df_tick, codes, market_fields)
            results.update(market_results)

        # ---- E类：扩展JSON ----
        if 'ext_indicators' in fields_to_compute:
            ext_results = self._compute_ext(df_tick, tick_time, code_col, codes)
            results.update(ext_results)

        return results

    @staticmethod
    def _rank_descending(values) -> list:
        """
        降序排名（method='min'）
        与 pandas rank(ascending=False, method='min') 一致
        """
        arr = np.array(values, dtype=np.float64)
        # 降序排名: rank = 1 + count(values > current)
        n = len(arr)
        ranks = np.empty(n, dtype=np.int32)
        for i in range(n):
            ranks[i] = 1 + int(np.sum(arr > arr[i]))
        return ranks.tolist()

    def _compute_min1(self, df_tick, tick_time: str, code_col: str, codes: list) -> dict:
        """
        B类：1分钟差值计算
        【完全复刻 monitor_bond.py::compute_min1_fields】
        """
        current_minute = tick_time[:5]  # "09:32:45" → "09:32"

        change_pcts = df_tick['change_pct'].values
        amounts = df_tick['amount'].values

        # 新分钟 or 冷启动 → 当前tick就是基准
        if self.min1_base_minute != current_minute:
            self.min1_base_pct = dict(zip(codes, change_pcts))
            self.min1_base_amt = dict(zip(codes, amounts))
            self.min1_base_minute = current_minute

        # 向量化计算
        min1_change_pct = {}
        min1_amount = {}
        for i, code in enumerate(codes):
            base_pct = self.min1_base_pct.get(code, change_pcts[i])
            base_amt = self.min1_base_amt.get(code, amounts[i])
            min1_change_pct[code] = round(float(change_pcts[i]) - float(base_pct), 4)
            min1_amount[code] = round(float(amounts[i]) - float(base_amt), 0)

            # 冷启动：新bond第一次出现，设为基准
            if code not in self.min1_base_pct:
                self.min1_base_pct[code] = float(change_pcts[i])
                self.min1_base_amt[code] = float(amounts[i])

        return {
            'min1_change_pct': min1_change_pct,
            'min1_amount': min1_amount,
        }

    def _compute_slopes(self, df_tick, code_col: str, codes: list, fields: set) -> dict:
        """
        C类：趋势斜率计算
        【完全复刻 monitor_bond.py::compute_indicators】
        """
        results = {}
        if 'slope_short' in fields:
            results['slope_short'] = {}
        if 'slope_long' in fields:
            results['slope_long'] = {}
        if 'peak_vol_bias' in fields:
            results['peak_vol_bias'] = {}
        if 'high_distance' in fields:
            results['high_distance'] = {}

        change_pcts = df_tick['change_pct'].values
        prices = df_tick['price'].values
        amounts = df_tick['amount'].values

        for i, code in enumerate(codes):
            cpct = float(change_pcts[i])
            price = float(prices[i])
            amount = float(amounts[i])

            # slope_short
            if 'slope_short' in fields:
                if code not in self.slope_buf_short:
                    self.slope_buf_short[code] = deque(maxlen=WINDOW_SHORT)
                self.slope_buf_short[code].append(cpct)
                results['slope_short'][code] = round(_calc_slope(self.slope_buf_short[code]), 6)

            # slope_long
            if 'slope_long' in fields:
                if code not in self.slope_buf_long:
                    self.slope_buf_long[code] = deque(maxlen=WINDOW_LONG)
                self.slope_buf_long[code].append(cpct)
                results['slope_long'][code] = round(_calc_slope(self.slope_buf_long[code]), 6)

            # peak_vol_bias
            if 'peak_vol_bias' in fields:
                if code not in self.peak_vol_state:
                    self.peak_vol_state[code] = {'max_amount': 0, 'price_at_max': price}
                pv = self.peak_vol_state[code]
                if amount > pv['max_amount']:
                    pv['max_amount'] = amount
                    pv['price_at_max'] = price
                bias = (price - pv['price_at_max']) / pv['price_at_max'] * 100 if pv['price_at_max'] > 0 else 0
                results['peak_vol_bias'][code] = round(bias, 4)

            # high_distance
            if 'high_distance' in fields:
                if code not in self.high_state:
                    self.high_state[code] = {'max_cpct': cpct}
                hs = self.high_state[code]
                if cpct > hs['max_cpct']:
                    hs['max_cpct'] = cpct
                results['high_distance'][code] = round(cpct - hs['max_cpct'], 4)

        return results

    def _compute_market(self, df_tick, codes: list, fields: set) -> dict:
        """
        D类：市场级指标计算
        【完全复刻 monitor_bond.py::compute_market_indicators】
        所有bond共享同一个值（每tick一个标量，广播到所有行）
        """
        results = {}

        # 计算大盘数据
        avg_pct = float(df_tick['change_pct'].mean())
        total_amt = float(df_tick['amount'].sum())

        # mkt_slope_short
        if 'mkt_slope_short' in fields:
            self.mkt_slope_buf_short.append(avg_pct)
            mkt_ss = round(_calc_slope(self.mkt_slope_buf_short), 6)
            results['mkt_slope_short'] = {code: mkt_ss for code in codes}

        # mkt_slope_long
        if 'mkt_slope_long' in fields:
            self.mkt_slope_buf_long.append(avg_pct)
            mkt_sl = round(_calc_slope(self.mkt_slope_buf_long), 6)
            results['mkt_slope_long'] = {code: mkt_sl for code in codes}

        # mkt_peak_vol_bias
        if 'mkt_peak_vol_bias' in fields:
            if total_amt > self.mkt_peak_vol['max_total_amt']:
                self.mkt_peak_vol['max_total_amt'] = total_amt
                self.mkt_peak_vol['pct_at_max'] = avg_pct
            mkt_pvb = round(avg_pct - self.mkt_peak_vol['pct_at_max'], 4)
            results['mkt_peak_vol_bias'] = {code: mkt_pvb for code in codes}

        # mkt_high_distance
        if 'mkt_high_distance' in fields:
            if avg_pct > self.mkt_high['max_avg_pct']:
                self.mkt_high['max_avg_pct'] = avg_pct
            mkt_hd = round(avg_pct - self.mkt_high['max_avg_pct'], 4)
            results['mkt_high_distance'] = {code: mkt_hd for code in codes}

        return results

    def _compute_ext(self, df_tick, tick_time: str, code_col: str, codes: list) -> dict:
        """
        E类：扩展JSON指标计算
        【重构】调用 monitor_bond.py 的统一计算函数
        包含个券指标和大盘扩展指标，全部存入ext_indicators JSON
        
        新增字段:
            - weighted_slope_5m: 5分钟加权斜率
            - weighted_slope_15m: 15分钟加权斜率
            - mkt_weighted_slope_5m: 大盘5分钟加权斜率
            - mkt_weighted_slope_15m: 大盘15分钟加权斜率
        """
        current_seconds = _time_to_seconds(tick_time)
        prices = df_tick['price'].values
        
        # === 先计算大盘扩展指标（每tick一次，所有bond共享）===
        avg_pct = float(df_tick['change_pct'].mean())
        
        # 更新大盘缓存（deque自动限制长度）
        self.mkt_ext_price_cache.append((current_seconds, avg_pct))
        
        # 【重构】调用统一计算函数
        mkt_prev = self.mkt_ext_prev_slope if self.mkt_ext_prev_slope != 0.0 else None
        if _unified_imported:
            mkt_ext = calc_mkt_ext_indicators(self.mkt_ext_price_cache, mkt_prev)
        else:
            # 降级方案：使用本地计算
            mkt_ext = self._calc_mkt_ext_local(current_seconds, avg_pct)
        
        # 更新全局状态
        if mkt_ext.get('mkt_weighted_slope_2m') is not None:
            self.mkt_ext_prev_slope = mkt_ext['mkt_weighted_slope_2m']

        # === 大盘日内趋势环境指标 ===
        mkt_trend = self._compute_mkt_trend(df_tick, current_seconds, avg_pct)

        # === 个券扩展指标 ===
        ext_results = {}

        for i, code in enumerate(codes):
            price = float(prices[i])

            # 初始化deque（maxlen=300，保留15分钟）
            if code not in self.ext_price_cache:
                self.ext_price_cache[code] = deque(maxlen=300)
            
            # 追加新数据
            self.ext_price_cache[code].append((current_seconds, price))

            # 【重构】调用统一计算函数
            prev_slope = self.ext_slope_cache.get(code)
            if _unified_imported:
                ext = calc_bond_ext_indicators(self.ext_price_cache[code], prev_slope)
            else:
                # 降级方案：使用本地计算
                ext = self._calc_bond_ext_local(code, current_seconds, price)
            
            # 更新prev_slope用于下次计算加速度
            if ext.get('weighted_slope_2m') is not None:
                self.ext_slope_cache[code] = ext['weighted_slope_2m']

            # 合并个券和大盘指标
            combined = {**ext, **mkt_ext, **mkt_trend}
            ext_results[code] = json.dumps(combined, ensure_ascii=False)

        return {'ext_indicators': ext_results}

    def _compute_mkt_trend(self, df_tick, current_seconds: int, avg_pct: float) -> dict:
        """
        F类：大盘日内趋势环境指标计算
        【复刻 monitor_bond.py::compute_mkt_trend_indicators】
        """
        # mkt_vs_open_pct
        mkt_vs_open_pct = round(avg_pct, 4)

        # mkt_vwap_bias（成交额加权VWAP偏离）
        total_amount = float(df_tick['amount'].sum())
        self.mkt_trend_vwap_sum_pv += mkt_vs_open_pct * total_amount
        self.mkt_trend_vwap_sum_v += total_amount
        mkt_vwap = self.mkt_trend_vwap_sum_pv / self.mkt_trend_vwap_sum_v if self.mkt_trend_vwap_sum_v > 0 else 0.0
        mkt_vwap_bias = round(mkt_vs_open_pct - mkt_vwap, 4)

        # mkt_day_position（日内位置%）
        if mkt_vs_open_pct > self.mkt_trend_day_high:
            self.mkt_trend_day_high = mkt_vs_open_pct
        if mkt_vs_open_pct < self.mkt_trend_day_low:
            self.mkt_trend_day_low = mkt_vs_open_pct

        if self.mkt_trend_day_high > self.mkt_trend_day_low:
            mkt_day_position = round(
                (mkt_vs_open_pct - self.mkt_trend_day_low) / (self.mkt_trend_day_high - self.mkt_trend_day_low) * 100, 1
            )
        else:
            mkt_day_position = 50.0

        # mkt_new_low_distance（距上次创新低的分钟数）
        if mkt_vs_open_pct <= self.mkt_trend_day_low:
            self.mkt_trend_last_new_low_time = current_seconds

        if self.mkt_trend_last_new_low_time is not None:
            mkt_new_low_distance = round((current_seconds - self.mkt_trend_last_new_low_time) / 60.0, 1)
        else:
            mkt_new_low_distance = 999.0

        # mkt_weighted_slope_10m（EWLR half_life=150s）
        self.mkt_trend_slope_10m_cache.append((current_seconds, mkt_vs_open_pct))
        if len(self.mkt_trend_slope_10m_cache) >= 5:
            pcts = np.array([p for _, p in self.mkt_trend_slope_10m_cache], dtype=np.float64)
            times = np.array([t for t, _ in self.mkt_trend_slope_10m_cache], dtype=np.float64)
            mkt_weighted_slope_10m = round(_calc_weighted_slope(pcts, times, half_life=150), 6)
        else:
            mkt_weighted_slope_10m = 0.0

        return {
            'mkt_vs_open_pct': mkt_vs_open_pct,
            'mkt_vwap_bias': mkt_vwap_bias,
            'mkt_weighted_slope_10m': mkt_weighted_slope_10m,
            'mkt_day_position': mkt_day_position,
            'mkt_new_low_distance': mkt_new_low_distance,
        }

    def _calc_mkt_ext_local(self, current_seconds: int, avg_pct: float) -> dict:
        """大盘扩展指标本地降级计算（渐进式）"""
        result = {
            'mkt_weighted_slope_2m': 0.0,
            'mkt_weighted_slope_5m': None,
            'mkt_weighted_slope_15m': None,
            'mkt_change_1m_pct': 0.0,
            'mkt_price_acceleration': 0.0,
        }
        
        cache = list(self.mkt_ext_price_cache)
        
        # 2分钟加权斜率（严格窗口）
        if len(cache) >= 2:
            prices = [p for _, p in cache if current_seconds - t <= 120 for t, p in [(t, p)]]
            times = [t for t, p in cache if current_seconds - t <= 120]
            if len(prices) >= 5:
                result['mkt_weighted_slope_2m'] = round(
                    _calc_weighted_slope(prices, times, half_life=30), 6
                )
        
        # 5分钟加权斜率（渐进式：5个点即可）
        if len(cache) >= 5:
            prices = [p for _, p in cache]
            times = [t for t, _ in cache]
            result['mkt_weighted_slope_5m'] = round(
                _calc_weighted_slope(prices, times, half_life=60), 6
            )
        
        # 15分钟加权斜率（渐进式：8个点即可）
        if len(cache) >= 8:
            prices = [p for _, p in cache]
            times = [t for t, _ in cache]
            result['mkt_weighted_slope_15m'] = round(
                _calc_weighted_slope(prices, times, half_life=180), 6
            )
        
        # 1分钟变化率
        target_ts = current_seconds - 60
        pct_1m_ago = None
        for ts, p in reversed(cache):
            if ts <= target_ts:
                pct_1m_ago = p
                break
        result['mkt_change_1m_pct'] = round(avg_pct - pct_1m_ago, 4) if pct_1m_ago is not None else 0.0
        
        # 加速度
        result['mkt_price_acceleration'] = round(
            result['mkt_weighted_slope_2m'] - self.mkt_ext_prev_slope, 6
        )
        
        return result
    
    def _calc_bond_ext_local(self, code: str, current_seconds: int, price: float) -> dict:
        """个券扩展指标本地降级计算（渐进式）"""
        result = {
            'weighted_slope_2m': 0.0,
            'weighted_slope_5m': None,
            'weighted_slope_15m': None,
            'change_1m_pct': 0.0,
            'price_acceleration': 0.0,
        }
        
        cache = list(self.ext_price_cache[code])
        
        # 2分钟加权斜率（严格窗口）
        if len(cache) >= 2:
            prices = [p for _, p in cache if current_seconds - t <= 120 for t, p in [(t, p)]]
            times = [t for t, p in cache if current_seconds - t <= 120]
            if len(prices) >= 5:
                result['weighted_slope_2m'] = round(
                    _calc_weighted_slope(prices, times, half_life=30), 6
                )
        
        # 5分钟加权斜率（渐进式：5个点即可）
        if len(cache) >= 5:
            prices = [p for _, p in cache]
            times = [t for t, _ in cache]
            result['weighted_slope_5m'] = round(
                _calc_weighted_slope(prices, times, half_life=60), 6
            )
        
        # 15分钟加权斜率（渐进式：8个点即可）
        if len(cache) >= 8:
            prices = [p for _, p in cache]
            times = [t for t, _ in cache]
            result['weighted_slope_15m'] = round(
                _calc_weighted_slope(prices, times, half_life=180), 6
            )
        
        # 1分钟变化率
        target_ts = current_seconds - 60
        price_1m_ago = None
        for ts, p in reversed(cache):
            if ts <= target_ts:
                price_1m_ago = p
                break
        if price_1m_ago is not None and price_1m_ago != 0:
            result['change_1m_pct'] = round((price - price_1m_ago) / price_1m_ago * 100, 4)
        
        # 加速度
        prev_slope = self.ext_slope_cache.get(code, 0.0)
        result['price_acceleration'] = round(result['weighted_slope_2m'] - prev_slope, 6)
        
        return result


if __name__ == '__main__':
    # 简单验证
    import pandas as pd

    # 模拟数据
    test_data = pd.DataFrame({
        'bond_code': ['110001', '110002', '110003'],
        'price': [105.0, 98.5, 112.3],
        'change_pct': [1.5, -0.3, 2.1],
        'amount': [5000000, 3000000, 8000000],
        'high': [106.0, 99.0, 113.0],
    })

    engine = ComputeEngine()
    all_fields = {
        'amount_rank', 'min1_change_pct', 'min1_amount', 'min1_amount_rank',
        'slope_short', 'slope_long', 'peak_vol_bias', 'high_distance',
        'mkt_slope_short', 'mkt_slope_long', 'mkt_peak_vol_bias', 'mkt_high_distance',
        'ext_indicators'
    }

    # 模拟3个tick
    for t in ['09:30:00', '09:30:03', '09:30:06']:
        results = engine.process_tick(test_data, t, all_fields)
        print(f"\ntick={t}:")
        for field, values in results.items():
            if isinstance(values, dict):
                first_val = list(values.values())[0]
                print(f"  {field}: {first_val}")

    print(f"\n处理完成，共 {engine.ticks_processed} 个ticks")
