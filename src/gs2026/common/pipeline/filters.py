"""
过滤器实现
"""
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import numpy as np


class Filter(ABC):
    """过滤器基类"""
    
    kind: str = 'predicate'  # 'predicate' 或 'ranking'
    
    @abstractmethod
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """应用过滤"""
        pass
    
    def is_active(self) -> bool:
        """是否激活"""
        return True


class PredicateFilter(Filter):
    """谓词型过滤器"""
    kind = 'predicate'


class RankingFilter(Filter):
    """排名型过滤器"""
    kind = 'ranking'
    
    def __init__(self, n: int, field: str):
        self.n = n
        self.field = field
    
    def is_active(self) -> bool:
        return self.n > 0
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        排名型过滤实现：
        1. 排除 field <= 0 的记录
        2. 按 field 降序排序
        3. 取前N
        4. 返回原始数据中匹配的项（保持原始顺序）
        """
        if not data or self.n <= 0:
            return data
        
        # 1. 排除 <= 0
        filtered = [d for d in data if d.get(self.field, 0) > 0]
        
        if not filtered:
            return []
        
        # 2. 降序排序
        sorted_data = sorted(
            filtered,
            key=lambda x: x.get(self.field, 0),
            reverse=True
        )
        
        # 3. 取前N
        top_n = sorted_data[:self.n]
        
        # 4. 获取code集合
        codes = {item['code'] for item in top_n}
        
        # 5. 返回原始数据中匹配的项（保持原始顺序）
        return [item for item in data if item['code'] in codes]


# ==================== 谓词型过滤器 ====================

class IndustryFilter(PredicateFilter):
    """行业筛选过滤器"""
    
    def __init__(self, industry: str):
        self.industry = industry
    
    def is_active(self) -> bool:
        return bool(self.industry)
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.industry:
            return data
        return [d for d in data if d.get('industry') == self.industry]


class BondExistsFilter(PredicateFilter):
    """仅显示有债券的过滤器（股票用）"""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
    
    def is_active(self) -> bool:
        return self.enabled
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return data
        return [
            d for d in data
            if d.get('bond_code') and d.get('bond_code') != '-'
        ]


class GreenListFilter(PredicateFilter):
    """排除绿名单过滤器（债券用）"""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
    
    def is_active(self) -> bool:
        return self.enabled
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return data
        return [d for d in data if not d.get('is_green', False)]


# ==================== 排名型过滤器 ====================

class TopNSectorsFilter(RankingFilter):
    """仅行业前N过滤器（按次数）"""
    
    def __init__(self, n: int):
        super().__init__(n, 'count')  # 按次数排序
        self.n = n
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        行业前N过滤：
        1. 按行业分组
        2. 计算每个行业的总次数
        3. 取次数前N的行业
        4. 返回这些行业的所有股票/债券
        """
        if not data or self.n <= 0:
            return data
        
        # 按行业分组计算总次数
        industry_counts = {}
        for item in data:
            industry = item.get('industry')
            if industry:
                industry_counts[industry] = industry_counts.get(industry, 0) + item.get('count', 0)
        
        if not industry_counts:
            return data
        
        # 按次数降序排序，取前N
        sorted_industries = sorted(
            industry_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:self.n]
        
        top_industries = {ind for ind, _ in sorted_industries}
        
        # 返回这些行业的所有项目
        return [d for d in data if d.get('industry') in top_industries]


class TopNSectorsPctFilter(RankingFilter):
    """仅行业前N过滤器（按涨幅）"""
    
    def __init__(self, n: int):
        super().__init__(n, 'avg_change_pct')  # 按涨幅排序
        self.n = n
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        行业涨幅前N过滤：
        1. 按行业分组
        2. 计算每个行业的平均涨幅
        3. 取涨幅前N的行业
        4. 返回这些行业的所有股票/债券
        """
        if not data or self.n <= 0:
            return data
        
        # 按行业分组计算平均涨幅
        industry_pcts = {}
        industry_counts = {}
        
        for item in data:
            industry = item.get('industry')
            if industry:
                pct = item.get('avg_change_pct', 0) or item.get('change_pct', 0)
                if industry not in industry_pcts:
                    industry_pcts[industry] = 0
                    industry_counts[industry] = 0
                industry_pcts[industry] += pct
                industry_counts[industry] += 1
        
        if not industry_pcts:
            return data
        
        # 计算平均涨幅
        for industry in industry_pcts:
            if industry_counts[industry] > 0:
                industry_pcts[industry] /= industry_counts[industry]
        
        # 按涨幅降序排序，取前N
        sorted_industries = sorted(
            industry_pcts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:self.n]
        
        top_industries = {ind for ind, _ in sorted_industries}
        
        # 返回这些行业的所有项目
        return [d for d in data if d.get('industry') in top_industries]


class TopNWindowFilter(RankingFilter):
    """仅前N区间次数过滤器"""
    
    def __init__(self, n: int):
        super().__init__(n, 'window_count')


class TopNCountFilter(RankingFilter):
    """仅前N次数过滤器"""
    
    def __init__(self, n: int):
        super().__init__(n, 'count')


class TopNAmountFilter(RankingFilter):
    """仅前N金额过滤器（债券用）"""
    
    def __init__(self, n: int):
        super().__init__(n, 'amount')
