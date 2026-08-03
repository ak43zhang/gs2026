"""
统一过滤管道
"""
from typing import List, Dict, Any, Optional
import time
from .config import FilterConfig
from .filters import (
    Filter,
    PredicateFilter,
    RankingFilter,
    IndustryFilter,
    BondExistsFilter,
    GreenListFilter,
    TopNSectorsFilter,
    TopNSectorsPctFilter,
    TopNWindowFilter,
    TopNCountFilter,
    TopNAmountFilter,
)


class PerformanceMonitor:
    """性能监控"""
    
    @staticmethod
    def measure(name: str, func, *args, **kwargs):
        """测量函数执行时间"""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        
        if elapsed > 100:  # 超过100ms告警
            print(f"⚠️ {name} 耗时 {elapsed:.1f}ms")
        
        return result, elapsed


class UnifiedPipeline:
    """
    统一过滤管道
    
    支持股票和债券的过滤，采用两阶段执行模型：
    1. 谓词型过滤器串行执行 → 候选池S
    2. 排名型过滤器基于S计算，取交集
    """
    
    def __init__(self, config: FilterConfig):
        self.config = config
        self.stock_pipeline = self._build_stock_pipeline()
        self.bond_pipeline = self._build_bond_pipeline()
        self._performance_stats = []
    
    def _build_stock_pipeline(self) -> List[Filter]:
        """构建股票过滤管道"""
        filters = []
        
        # 谓词型过滤器
        if self.config.stock_industry:
            filters.append(IndustryFilter(self.config.stock_industry))
        
        if self.config.stock_bond_filter:
            filters.append(BondExistsFilter(True))
        
        # 排名型过滤器
        if self.config.stock_topn_sectors > 0:
            filters.append(TopNSectorsFilter(self.config.stock_topn_sectors))
        
        if self.config.stock_topn_sectors_pct > 0:
            filters.append(TopNSectorsPctFilter(self.config.stock_topn_sectors_pct))
        
        if self.config.stock_topn_window > 0:
            filters.append(TopNWindowFilter(self.config.stock_topn_window))
        
        if self.config.stock_topn_count > 0:
            filters.append(TopNCountFilter(self.config.stock_topn_count))
        
        return filters
    
    def _build_bond_pipeline(self) -> List[Filter]:
        """构建债券过滤管道"""
        filters = []
        
        # 谓词型过滤器
        if self.config.bond_industry:
            filters.append(IndustryFilter(self.config.bond_industry))
        
        if self.config.bond_green_list:
            filters.append(GreenListFilter(True))
        
        # 注意：债券的topn_sectors是predicate（与前端一致）
        if self.config.bond_topn_sectors > 0:
            # 这里使用TopNSectorsFilter作为predicate
            # 实际行为：筛选出前N行业的所有债券
            filters.append(TopNSectorsFilter(self.config.bond_topn_sectors))
        
        # 排名型过滤器
        if self.config.bond_topn_sectors_pct > 0:
            filters.append(TopNSectorsPctFilter(self.config.bond_topn_sectors_pct))
        
        if self.config.bond_topn_amount > 0:
            filters.append(TopNAmountFilter(self.config.bond_topn_amount))
        
        if self.config.bond_topn_window > 0:
            filters.append(TopNWindowFilter(self.config.bond_topn_window))
        
        if self.config.bond_topn_count > 0:
            filters.append(TopNCountFilter(self.config.bond_topn_count))
        
        return filters
    
    def _execute_pipeline(self, data: List[Dict[str, Any]], 
                          filters: List[Filter]) -> List[Dict[str, Any]]:
        """
        执行过滤管道
        
        两阶段模型：
        1. 谓词型串行 → 候选池S
        2. 排名型基于S计算，取交集
        """
        if not data:
            return []
        
        # Phase 1: 谓词型串行
        S = data
        predicate_filters = [f for f in filters if f.kind == 'predicate' and f.is_active()]
        
        for f in predicate_filters:
            S = f.apply(S)
            # 延迟加载：数据量小提前返回
            if len(S) < 50:
                break
        
        # Phase 2: 排名型取交集
        ranking_filters = [f for f in filters if f.kind == 'ranking' and f.is_active()]
        
        if not ranking_filters:
            return S
        
        # 每个排名型过滤器基于S计算
        ranking_sets = []
        for f in ranking_filters:
            subset = f.apply(S)
            codes = {item['code'] for item in subset}
            ranking_sets.append(codes)
        
        # 取交集
        intersection = ranking_sets[0]
        for s in ranking_sets[1:]:
            intersection &= s
        
        # 返回原始数据中匹配的项
        return [item for item in S if item['code'] in intersection]
    
    def filter_stocks(self, stocks: List[Dict[str, Any]], 
                      monitor_performance: bool = True) -> List[Dict[str, Any]]:
        """
        过滤股票
        
        Args:
            stocks: 股票原始数据
            monitor_performance: 是否监控性能
        
        Returns:
            过滤后的股票列表
        """
        if not self.config.is_stock_filter_active():
            return stocks
        
        if monitor_performance:
            result, elapsed = PerformanceMonitor.measure(
                'stock_filter',
                self._execute_pipeline,
                stocks,
                self.stock_pipeline
            )
            self._performance_stats.append({
                'type': 'stock',
                'input_count': len(stocks),
                'output_count': len(result),
                'elapsed_ms': elapsed
            })
            return result
        else:
            return self._execute_pipeline(stocks, self.stock_pipeline)
    
    def filter_bonds(self, bonds: List[Dict[str, Any]],
                     monitor_performance: bool = True) -> List[Dict[str, Any]]:
        """
        过滤债券
        
        Args:
            bonds: 债券原始数据
            monitor_performance: 是否监控性能
        
        Returns:
            过滤后的债券列表
        """
        if not self.config.is_bond_filter_active():
            return bonds
        
        if monitor_performance:
            result, elapsed = PerformanceMonitor.measure(
                'bond_filter',
                self._execute_pipeline,
                bonds,
                self.bond_pipeline
            )
            self._performance_stats.append({
                'type': 'bond',
                'input_count': len(bonds),
                'output_count': len(result),
                'elapsed_ms': elapsed
            })
            return result
        else:
            return self._execute_pipeline(bonds, self.bond_pipeline)
    
    def get_performance_stats(self) -> List[Dict[str, Any]]:
        """获取性能统计"""
        return self._performance_stats
    
    def clear_performance_stats(self):
        """清除性能统计"""
        self._performance_stats = []


class IntersectionCalculator:
    """
    股债交集计算器
    
    计算股票和债券的交集（股票.bond_code == 债券.code）
    """
    
    @staticmethod
    def calculate(stocks: List[Dict[str, Any]], 
                  bonds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        计算股债交集
        
        Args:
            stocks: 过滤后的股票列表
            bonds: 过滤后的债券列表
        
        Returns:
            股债交集列表（包含股票和债券的完整信息）
        """
        if not stocks or not bonds:
            return []
        
        # 构建债券code映射
        bond_map = {b['code']: b for b in bonds}
        
        # 计算交集
        intersections = []
        for stock in stocks:
            bond_code = stock.get('bond_code')
            if bond_code and bond_code in bond_map:
                bond = bond_map[bond_code]
                intersections.append({
                    'stock_code': stock['code'],
                    'stock_name': stock.get('name', ''),
                    'stock_change_pct': stock.get('change_pct', 0),
                    'stock_count': stock.get('count', 0),
                    'stock_window_count': stock.get('window_count', 0),
                    'stock_industry': stock.get('industry', ''),
                    'stock_main_net': stock.get('main_net_amount', 0),
                    'bond_code': bond['code'],
                    'bond_name': bond.get('name', ''),
                    'bond_change_pct': bond.get('change_pct', 0),
                    'bond_price': bond.get('price', 0),
                    'bond_count': bond.get('count', 0),
                    'bond_window_count': bond.get('window_count', 0),
                    'bond_amount': bond.get('amount', 0),
                    'bond_industry': bond.get('industry', ''),
                    'bond_main_net': bond.get('main_net_amount', 0),
                })
        
        return intersections
