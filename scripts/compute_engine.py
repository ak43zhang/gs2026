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
        self.ext_price_cache: Dict[str, list] = {}    # { bond_code: [(timestamp_seconds, price), ...] }
        self.ext_slope_cache: Dict[str, float] = {}   # { bond_code: last_weighted_slope }

        # === E类：大盘扩展指标缓存（存入ext_indicators JSON）===
        self.mkt_ext_price_cache: list = []           # [(timestamp_seconds, avg_pct), ...]
        self.mkt_ext_prev_slope: float = 0.0          # 上一tick大盘加权斜率

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
        【完全复刻 monitor_bond.py::compute_ext_indicators + compute_mkt_ext_indicators】
        包含个券指标和大盘扩展指标，全部存入ext_indicators JSON
        """
        current_seconds = _time_to_seconds(tick_time)
        cutoff = current_seconds - EXT_WINDOW_SECONDS

        prices = df_tick['price'].values
        
        # === 先计算大盘扩展指标（每tick一次，所有bond共享）===
        avg_pct = float(df_tick['change_pct'].mean())
        
        # 更新大盘缓存
        self.mkt_ext_price_cache.append((current_seconds, avg_pct))
        self.mkt_ext_price_cache = [(ts, p) for ts, p in self.mkt_ext_price_cache if ts >= cutoff]
        
        # 大盘加权斜率
        if len(self.mkt_ext_price_cache) >= 2:
            mkt_prices = [p for _, p in self.mkt_ext_price_cache]
            mkt_times = [t for t, _ in self.mkt_ext_price_cache]
            mkt_ws = round(_calc_weighted_slope(mkt_prices, mkt_times, half_life=EXT_HALF_LIFE), 6)
        else:
            mkt_ws = 0.0
        
        # 大盘1分钟变化率
        target_ts = current_seconds - 60
        pct_1m_ago = None
        for ts, p in reversed(self.mkt_ext_price_cache):
            if ts <= target_ts:
                pct_1m_ago = p
                break
        mkt_c1p = round(avg_pct - pct_1m_ago, 4) if pct_1m_ago is not None else 0.0
        
        # 大盘加速度
        mkt_pa = round(mkt_ws - self.mkt_ext_prev_slope, 6)
        self.mkt_ext_prev_slope = mkt_ws

        # === 个券扩展指标 ===
        ext_results = {}

        for i, code in enumerate(codes):
            price = float(prices[i])

            # 更新价格缓存
            if code not in self.ext_price_cache:
                self.ext_price_cache[code] = []
            self.ext_price_cache[code].append((current_seconds, price))

            # 清理过期数据（保留150秒）
            self.ext_price_cache[code] = [
                (ts, p) for ts, p in self.ext_price_cache[code] if ts >= cutoff
            ]

            cache = self.ext_price_cache[code]

            # 计算加权斜率（2分钟窗口）
            if len(cache) >= 2:
                cache_prices = [p for _, p in cache]
                cache_times = [t for t, _ in cache]
                ws = round(_calc_weighted_slope(cache_prices, cache_times, half_life=EXT_HALF_LIFE), 6)
            else:
                ws = 0.0

            # 计算1分钟变化率
            if len(cache) >= 2:
                bond_target_ts = current_seconds - 60
                price_1m_ago = None
                for ts, p in reversed(cache):
                    if ts <= bond_target_ts:
                        price_1m_ago = p
                        break
                if price_1m_ago is not None and price_1m_ago != 0:
                    c1p = round((price - price_1m_ago) / price_1m_ago * 100, 4)
                else:
                    c1p = 0.0
            else:
                c1p = 0.0

            # 计算加速度（当前斜率 - 上一周期斜率）
            prev_slope = self.ext_slope_cache.get(code, 0.0)
            pa = round(ws - prev_slope, 6)

            # 保存当前斜率用于下次
            self.ext_slope_cache[code] = ws

            # 构建JSON（包含个券+大盘扩展指标）
            ext_results[code] = json.dumps({
                'weighted_slope_2m': ws,
                'change_1m_pct': c1p,
                'price_acceleration': pa,
                'mkt_weighted_slope_2m': mkt_ws,
                'mkt_change_1m_pct': mkt_c1p,
                'mkt_price_acceleration': mkt_pa,
            }, ensure_ascii=False)

        return {'ext_indicators': ext_results}


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
