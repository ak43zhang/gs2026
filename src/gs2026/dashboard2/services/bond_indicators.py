"""
债券量化指标计算模块 - 优化版斜率指标

包含:
- 加权斜率 (Weighted Slope)
- 1分钟变化率 (1-Minute Change Rate)
- 价格加速度 (Price Acceleration)
"""

import numpy as np
from collections import deque
from typing import List, Tuple, Optional


class BondIndicatorCalculator:
    """债券指标计算器 - 支持增量计算"""
    
    def __init__(self, max_window=300):
        """
        初始化计算器
        
        Args:
            max_window: 最大缓存窗口（秒），默认5分钟
        """
        self.max_window = max_window
        # 价格缓存: bond_code -> deque of (timestamp, price)
        self._price_cache = {}
        # 斜率缓存: bond_code -> deque of (timestamp, slope)
        self._slope_cache = {}
        
    def update_price(self, bond_code: str, timestamp: int, price: float):
        """
        更新价格缓存
        
        Args:
            bond_code: 债券代码
            timestamp: 时间戳（秒）
            price: 价格
        """
        if bond_code not in self._price_cache:
            self._price_cache[bond_code] = deque(maxlen=self.max_window)
        self._price_cache[bond_code].append((timestamp, price))
        
    def calc_weighted_slope(self, bond_code: str, window_seconds: int = 120, 
                           half_life: int = 30) -> Optional[float]:
        """
        计算指数加权斜率
        
        参数:
            bond_code: 债券代码
            window_seconds: 计算窗口（秒），默认2分钟
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
            
        # 计算指数权重
        lambda_param = np.log(2) / half_life
        weights = []
        for t in times:
            # 越新的数据权重越高
            age = current_time - t
            w = np.exp(-lambda_param * age)
            weights.append(w)
            
        weights = np.array(weights)
        weights /= weights.sum()  # 归一化
        
        # 加权线性回归
        x = np.array(times, dtype=float)
        y = np.array(prices, dtype=float)
        
        x_mean = np.average(x, weights=weights)
        y_mean = np.average(y, weights=weights)
        
        # 加权协方差 / 加权方差
        cov = np.sum(weights * (x - x_mean) * (y - y_mean))
        var = np.sum(weights * (x - x_mean) ** 2)
        
        if var == 0:
            return 0.0
            
        slope = cov / var
        return slope
        
    def calc_change_rate(self, bond_code: str, period_seconds: int = 60) -> Optional[float]:
        """
        计算N秒变化率
        
        参数:
            bond_code: 债券代码
            period_seconds: 周期（秒），默认60秒
            
        返回:
            变化率（%），如0.5表示上涨0.5%
        """
        if bond_code not in self._price_cache:
            return None
            
        cache = self._price_cache[bond_code]
        if len(cache) < 2:
            return None
            
        current_price = cache[-1][1]
        current_time = cache[-1][0]
        
        # 查找N秒前的价格
        cutoff_time = current_time - period_seconds
        prev_price = None
        for ts, price in reversed(cache):
            if ts <= cutoff_time:
                prev_price = price
                break
                
        if prev_price is None or prev_price == 0:
            return 0.0
            
        return (current_price - prev_price) / prev_price * 100
        
    def calc_acceleration(self, bond_code: str, window_seconds: int = 120) -> Optional[float]:
        """
        计算价格加速度（斜率的变化率）
        
        参数:
            bond_code: 债券代码
            window_seconds: 斜率计算窗口（秒）
            
        返回:
            加速度值，正数表示斜率在变陡
        """
        # 计算当前斜率
        current_slope = self.calc_weighted_slope(bond_code, window_seconds)
        if current_slope is None:
            return None
            
        # 计算上一周期的斜率（30秒前）
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
            
        # 计算上一周期斜率（简化版，使用简单斜率）
        x = np.array(times, dtype=float)
        y = np.array(prices, dtype=float)
        prev_slope = np.polyfit(x, y, 1)[0] if len(x) >= 2 else 0
        
        # 加速度 = 当前斜率 - 上一周期斜率
        acceleration = current_slope - prev_slope
        return acceleration
        
    def calc_all_indicators(self, bond_code: str) -> dict:
        """
        计算所有指标
        
        返回:
            {
                'weighted_slope_2m': float,  # 2分钟加权斜率
                'change_1m_pct': float,       # 1分钟变化率%
                'price_acceleration': float,  # 价格加速度
            }
        """
        return {
            'weighted_slope_2m': self.calc_weighted_slope(bond_code, 120),
            'change_1m_pct': self.calc_change_rate(bond_code, 60),
            'price_acceleration': self.calc_acceleration(bond_code, 120),
        }
        
    def clear_cache(self, bond_code: str = None):
        """清除缓存"""
        if bond_code:
            self._price_cache.pop(bond_code, None)
        else:
            self._price_cache.clear()


# 全局计算器实例
_indicator_calculator = BondIndicatorCalculator()


def calc_weighted_slope(prices: List[float], times: List[int], 
                       half_life: int = 30) -> float:
    """
    静态函数：计算指数加权斜率（用于批量处理历史数据）
    
    参数:
        prices: 价格列表
        times: 时间戳列表（秒）
        half_life: 半衰期（秒）
        
    返回:
        加权斜率
    """
    if len(prices) < 2 or len(times) < 2:
        return 0.0
        
    prices = np.array(prices)
    times = np.array(times, dtype=float)
    
    # 计算指数权重
    lambda_param = np.log(2) / half_life
    current_time = times[-1]
    weights = np.exp(-lambda_param * (current_time - times))
    weights /= weights.sum()
    
    # 加权线性回归
    x_mean = np.average(times, weights=weights)
    y_mean = np.average(prices, weights=weights)
    
    cov = np.sum(weights * (times - x_mean) * (prices - y_mean))
    var = np.sum(weights * (times - x_mean) ** 2)
    
    if var == 0:
        return 0.0
        
    return cov / var


def calc_change_rate(current_price: float, price_n_seconds_ago: float) -> float:
    """
    静态函数：计算变化率
    
    返回:
        变化率（%）
    """
    if price_n_seconds_ago == 0:
        return 0.0
    return (current_price - price_n_seconds_ago) / price_n_seconds_ago * 100


def calc_acceleration(current_slope: float, previous_slope: float) -> float:
    """
    静态函数：计算加速度
    
    返回:
        加速度值
    """
    return current_slope - previous_slope
