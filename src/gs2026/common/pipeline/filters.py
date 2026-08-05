"""
过滤器实现
"""
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod


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
    """排名型过滤器
    
    支持两种模式（与前端 applyToggleableFilter 语义一致）：
    - ranking（默认）: 基于输入数据（候选池S）按field降序取前N
    - predicate: 从全部原始数据(full_data)按field降序取前N
      （由 UnifiedPipeline 在执行时注入 full_data）
    """
    kind = 'ranking'
    
    def __init__(self, n: int, field: str, mode: str = 'ranking'):
        self.n = n
        self.field = field
        self.mode = mode  # 'ranking' | 'predicate'
        self._full_data = None  # predicate 模式下由 Pipeline 注入的全部原始数据
    
    def is_active(self) -> bool:
        return self.n > 0
    
    def set_full_data(self, full_data: List[Dict[str, Any]]):
        """predicate 模式使用：注入全部原始数据"""
        self._full_data = full_data
    
    def _rank(self, source: List[Dict[str, Any]]) -> set:
        """从 source 中按 field 降序取前N，返回 code 集合"""
        filtered = [d for d in source if _to_float(d.get(self.field, 0)) > 0]
        if not filtered:
            return set()
        sorted_data = sorted(
            filtered,
            key=lambda x: _to_float(x.get(self.field, 0)),
            reverse=True
        )
        return {item['code'] for item in sorted_data[:self.n]}
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        - ranking: 基于 data（候选池S）取前N
        - predicate: 基于 full_data（全部原始数据）取前N，再从 data 中筛选
        """
        if not data or self.n <= 0:
            return data
        
        if self.mode == 'predicate' and self._full_data is not None:
            # 谓词模式：从全部原始数据取前N
            codes = self._rank(self._full_data)
        else:
            # 排行模式：基于候选池S取前N
            codes = self._rank(data)
        
        return [item for item in data if item['code'] in codes]


def _to_float(v) -> float:
    """安全转float"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# ==================== 谓词型过滤器 ====================

class IndustryFilter(PredicateFilter):
    """行业筛选过滤器（按 industry_name 精确匹配）"""
    
    def __init__(self, industry: str):
        self.industry = industry
    
    def is_active(self) -> bool:
        return bool(self.industry)
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.industry:
            return data
        return [d for d in data if d.get('industry_name') == self.industry]


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
    """排除绿名单过滤器
    
    股票侧字段为 is_green_bond，债券侧字段为 is_green，兼容两者。
    """
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
    
    def is_active(self) -> bool:
        return self.enabled
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return data
        return [
            d for d in data
            if not (d.get('is_green', False) or d.get('is_green_bond', False))
        ]


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
            industry = item.get('industry_name')
            if industry and industry != '-':
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
        return [d for d in data if d.get('industry_name') in top_industries]


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
            industry = item.get('industry_name')
            if industry and industry != '-':
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
        return [d for d in data if d.get('industry_name') in top_industries]


class TopNWindowFilter(RankingFilter):
    """仅前N区间次数过滤器"""
    
    def __init__(self, n: int, mode: str = 'ranking'):
        super().__init__(n, 'window_count', mode)


class TopNCountFilter(RankingFilter):
    """仅前N次数过滤器"""
    
    def __init__(self, n: int, mode: str = 'ranking'):
        super().__init__(n, 'count', mode)


class TopNAmountFilter(RankingFilter):
    """仅前N金额过滤器（债券用）"""
    
    def __init__(self, n: int, mode: str = 'ranking'):
        super().__init__(n, 'amount', mode)


class TopNMin1AmountFilter(RankingFilter):
    """仅1分钟金额前N过滤器（债券用）
    
    按 min1_amount（1分钟成交金额增量）降序取前N。
    支持 ranking（基于候选池S）/ predicate（基于全部原始数据）双模式。
    """
    
    def __init__(self, n: int, mode: str = 'ranking'):
        super().__init__(n, 'min1_amount', mode)


class Min1ChangeGtFilter(PredicateFilter):
    """1分钟涨幅大于阈值过滤器（债券用）
    
    保留 min1_change_pct > threshold 的项。
    threshold<=0 时不激活（返回全部）。
    """
    
    def __init__(self, threshold: float = 0.0):
        self.threshold = threshold
    
    def is_active(self) -> bool:
        return self.threshold > 0
    
    def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.threshold <= 0:
            return data
        return [
            d for d in data
            if _to_float(d.get('min1_change_pct', 0)) > self.threshold
        ]
