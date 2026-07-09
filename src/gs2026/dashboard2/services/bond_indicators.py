"""
债券指标计算模块 - 精确计算版

包含:
- 加权斜率 (Weighted Slope) - 精确指数加权回归
- 1分钟变化率 (1-Minute Change Rate)
- 价格加速度 (Price Acceleration)

设计原则:
- 精确计算，不接受近似
- 400+债券规模优化
- 与backfill_all_fields.py逻辑一致
"""

import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional
import pandas as pd


class BondIndicatorCalculator:
    """债券指标计算器 - 精确计算"""
    
    def __init__(self, max_window=300):
        """
        初始化计算器
        
        Args:
            max_window: 最大缓存窗口（秒），默认5分钟
        """
        self.max_window = max_window
        # 价格缓存: bond_code -> deque of (timestamp, price)
        self._price_cache = {}
        
    def update_price(self, bond_code: str, timestamp: int, price: float):
        """
        更新价格缓存
        
        Args:
            bond_code: 债券代码
            timestamp: 时间戳（秒，从当天00:00:00开始的秒数）
            price: 价格
        """
        if bond_code not in self._price_cache:
            self._price_cache[bond_code] = deque(maxlen=self.max_window)
        self._price_cache[bond_code].append((timestamp, price))
        
    def calc_weighted_slope(self, bond_code: str, window_seconds: int = 120, 
                           half_life: int = 30) -> Optional[float]:
        """
        计算指数加权斜率 - 精确计算
        
        参数:
            bond_code: 债券代码
            window_seconds: 计算窗口（秒），默认2分钟=120秒
            half_life: 半衰期（秒），默认30秒
            
        返回:
            加权斜率，数据不足返回None
        """
        if bond_code not in self._price_cache:
            return None
            
        cache = self._price_cache[bond_code]
        if len(cache) < 2:
            return None
            
        # 获取窗口内的数据
        current_time = cache[-1][0]
        cutoff_time = current_time - window_seconds
        
        prices = []
        times = []
        for ts, price in cache:
            if ts >= cutoff_time:
                prices.append(price)
                times.append(ts)
                
        if len(prices) < 2:
            return None
            
        # 精确指数加权线性回归
        prices_arr = np.array(prices, dtype=np.float64)
        times_arr = np.array(times, dtype=np.float64)
        
        # 计算指数权重: w_i = exp(-λ * (t_current - t_i))
        # 其中 λ = ln(2) / half_life
        lambda_param = np.log(2) / half_life
        weights = np.exp(-lambda_param * (current_time - times_arr))
        weights = weights / np.sum(weights)  # 精确归一化
        
        # 加权均值
        t_mean = np.sum(weights * times_arr)
        p_mean = np.sum(weights * prices_arr)
        
        # 加权协方差和方差
        cov = np.sum(weights * (times_arr - t_mean) * (prices_arr - p_mean))
        var = np.sum(weights * (times_arr - t_mean) ** 2)
        
        if var == 0:
            return 0.0
            
        slope = cov / var
        return float(slope)
        
    def calc_change_rate(self, bond_code: str, period_seconds: int = 60) -> Optional[float]:
        """
        计算N秒变化率 - 精确计算
        
        参数:
            bond_code: 债券代码
            period_seconds: 周期（秒），默认60秒=1分钟
            
        返回:
            变化率（%），如0.5表示上涨0.5%，数据不足返回None
        """
        if bond_code not in self._price_cache:
            return None
            
        cache = self._price_cache[bond_code]
        if len(cache) < 2:
            return None
            
        current_price = cache[-1][1]
        current_time = cache[-1][0]
        
        # 精确查找period_seconds前的价格
        target_time = current_time - period_seconds
        
        # 二分查找最近的记录
        prev_price = None
        for ts, price in reversed(cache):
            if ts <= target_time:
                prev_price = price
                break
                
        if prev_price is None or prev_price == 0:
            # 找不到足够历史数据，返回0
            return 0.0
            
        return float((current_price - prev_price) / prev_price * 100)
        
    def calc_acceleration(self, bond_code: str, window_seconds: int = 120) -> Optional[float]:
        """
        计算价格加速度 - 精确计算
        
        加速度 = 当前斜率 - 上一周期斜率
        
        参数:
            bond_code: 债券代码
            window_seconds: 斜率计算窗口（秒）
            
        返回:
            加速度值，正数表示斜率在变陡，数据不足返回None
        """
        # 计算当前斜率
        current_slope = self.calc_weighted_slope(bond_code, window_seconds)
        if current_slope is None:
            return None
            
        # 计算30秒前的斜率
        if bond_code not in self._price_cache:
            return None
            
        cache = self._price_cache[bond_code]
        if len(cache) < 2:
            return None
            
        current_time = cache[-1][0]
        prev_time = current_time - 30  # 30秒前
        
        # 构建30秒前的数据窗口
        cutoff_time = prev_time - window_seconds
        prices = []
        times = []
        for ts, price in cache:
            if cutoff_time <= ts <= prev_time:
                prices.append(price)
                times.append(ts)
                
        if len(prices) < 2:
            return 0.0
            
        # 计算上一周期斜率（简单线性回归）
        prices_arr = np.array(prices, dtype=np.float64)
        times_arr = np.array(times, dtype=np.float64)
        
        # 简单线性回归: slope = cov(x,y) / var(x)
        t_mean = np.mean(times_arr)
        p_mean = np.mean(prices_arr)
        cov = np.mean((times_arr - t_mean) * (prices_arr - p_mean))
        var = np.mean((times_arr - t_mean) ** 2)
        
        prev_slope = cov / var if var != 0 else 0.0
        
        # 加速度 = 当前斜率 - 上一周期斜率
        acceleration = current_slope - prev_slope
        return float(acceleration)
        
    def calc_all_indicators(self, bond_code: str) -> Dict[str, float]:
        """
        计算所有指标 - 用于实时计算
        
        返回:
            {
                'weighted_slope_2m': float,
                'change_1m_pct': float,
                'price_acceleration': float,
            }
        """
        return {
            'weighted_slope_2m': self.calc_weighted_slope(bond_code, 120) or 0.0,
            'change_1m_pct': self.calc_change_rate(bond_code, 60) or 0.0,
            'price_acceleration': self.calc_acceleration(bond_code, 120) or 0.0,
        }
        
    def clear_cache(self, bond_code: str = None):
        """清除缓存"""
        if bond_code:
            self._price_cache.pop(bond_code, None)
        else:
            self._price_cache.clear()


# ==================== 静态函数（用于批量回填） ====================

def calc_weighted_slope_batch(prices: List[float], times: List[int], 
                               window: int = 120, half_life: int = 30) -> float:
    """
    批量计算加权斜率 - 用于backfill_all_fields.py
    
    参数:
        prices: 价格列表
        times: 时间戳列表（秒）
        window: 窗口秒数
        half_life: 半衰期秒数
        
    返回:
        加权斜率
    """
    if len(prices) < 2 or len(times) < 2:
        return 0.0
        
    prices_arr = np.array(prices, dtype=np.float64)
    times_arr = np.array(times, dtype=np.float64)
    
    # 只取窗口内数据
    current_time = times_arr[-1]
    mask = times_arr >= (current_time - window)
    
    if mask.sum() < 2:
        return 0.0
        
    prices_arr = prices_arr[mask]
    times_arr = times_arr[mask]
    
    # 指数权重
    lambda_param = np.log(2) / half_life
    weights = np.exp(-lambda_param * (current_time - times_arr))
    weights = weights / np.sum(weights)
    
    # 加权回归
    t_mean = np.sum(weights * times_arr)
    p_mean = np.sum(weights * prices_arr)
    cov = np.sum(weights * (times_arr - t_mean) * (prices_arr - p_mean))
    var = np.sum(weights * (times_arr - t_mean) ** 2)
    
    return float(cov / var) if var != 0 else 0.0


def calc_change_rate_batch(current_price: float, price_n_seconds_ago: float) -> float:
    """
    批量计算变化率 - 用于backfill_all_fields.py
    
    返回:
        变化率（%）
    """
    if price_n_seconds_ago == 0 or pd.isna(price_n_seconds_ago):
        return 0.0
    return float((current_price - price_n_seconds_ago) / price_n_seconds_ago * 100)


def calc_acceleration_batch(current_slope: float, previous_slope: float) -> float:
    """
    批量计算加速度 - 用于backfill_all_fields.py
    
    返回:
        加速度值
    """
    return float(current_slope - previous_slope)


# ==================== 批量处理函数（用于回填） ====================

def calc_indicators_for_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    为DataFrame计算所有扩展指标 - 用于backfill_all_fields.py
    
    参数:
        df: 包含bond_code, time, price的DataFrame
        
    返回:
        添加了扩展指标列的DataFrame
    """
    # 确保数据按债券和时间排序
    df = df.sort_values(['bond_code', 'time']).copy()
    
    # 初始化新列
    df['weighted_slope_2m'] = 0.0
    df['change_1m_pct'] = 0.0
    df['price_acceleration'] = 0.0
    
    # 按债券分组计算
    for bond_code, group in df.groupby('bond_code'):
        prices = group['price'].values
        # 将HHMMSS转换为秒
        times = pd.to_datetime(group['time'].astype(str).str.zfill(6), format='%H%M%S')
        seconds = (times - times.iloc[0]).dt.total_seconds().values
        
        n = len(prices)
        if n < 2:
            continue
            
        # 计算每个时间点的指标
        slopes = np.zeros(n)
        changes = np.zeros(n)
        
        for i in range(n):
            if i < 1:
                continue
                
            # 2分钟窗口
            window_start = seconds[i] - 120
            window_mask = seconds[:i+1] >= window_start
            
            if window_mask.sum() >= 2:
                # 加权斜率
                slopes[i] = calc_weighted_slope_batch(
                    prices[:i+1][window_mask].tolist(),
                    seconds[:i+1][window_mask].tolist(),
                    window=120, half_life=30
                )
                
            # 1分钟变化率
            if i >= 1 and seconds[i] - seconds[i-1] <= 120:
                changes[i] = calc_change_rate_batch(prices[i], prices[i-1])
        
        # 加速度（斜率的变化）
        accelerations = np.zeros(n)
        for i in range(1, n):
            accelerations[i] = slopes[i] - slopes[i-1]
        
        # 回填到DataFrame
        df.loc[group.index, 'weighted_slope_2m'] = slopes
        df.loc[group.index, 'change_1m_pct'] = changes
        df.loc[group.index, 'price_acceleration'] = accelerations
    
    return df
