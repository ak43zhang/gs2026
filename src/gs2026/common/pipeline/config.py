"""
过滤配置类
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class FilterConfig:
    """过滤配置"""
    
    # 股票过滤配置
    stock_industry: Optional[str] = None  # 行业筛选
    stock_topn_sectors: int = 0  # 仅行业次数前N
    stock_topn_sectors_pct: int = 0  # 仅行业涨幅前N
    stock_topn_window: int = 0  # 仅前N区间次数
    stock_topn_count: int = 0  # 仅前N次数
    stock_bond_filter: bool = False  # 仅显示有债券的
    
    # 债券过滤配置
    bond_industry: Optional[str] = None  # 行业筛选
    bond_topn_sectors: int = 0  # 仅行业次数前N
    bond_topn_sectors_pct: int = 0  # 仅行业涨幅前N
    bond_topn_amount: int = 0  # 仅前N金额
    bond_topn_window: int = 0  # 仅前N区间次数
    bond_topn_count: int = 0  # 仅前N次数
    bond_green_list: bool = False  # 排除绿名单
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterConfig':
        """从字典创建配置"""
        return cls(
            stock_industry=data.get('stock_industry'),
            stock_topn_sectors=data.get('stock_topn_sectors', 0),
            stock_topn_sectors_pct=data.get('stock_topn_sectors_pct', 0),
            stock_topn_window=data.get('stock_topn_window', 0),
            stock_topn_count=data.get('stock_topn_count', 0),
            stock_bond_filter=data.get('stock_bond_filter', False),
            bond_industry=data.get('bond_industry'),
            bond_topn_sectors=data.get('bond_topn_sectors', 0),
            bond_topn_sectors_pct=data.get('bond_topn_sectors_pct', 0),
            bond_topn_amount=data.get('bond_topn_amount', 0),
            bond_topn_window=data.get('bond_topn_window', 0),
            bond_topn_count=data.get('bond_topn_count', 0),
            bond_green_list=data.get('bond_green_list', False),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'stock_industry': self.stock_industry,
            'stock_topn_sectors': self.stock_topn_sectors,
            'stock_topn_sectors_pct': self.stock_topn_sectors_pct,
            'stock_topn_window': self.stock_topn_window,
            'stock_topn_count': self.stock_topn_count,
            'stock_bond_filter': self.stock_bond_filter,
            'bond_industry': self.bond_industry,
            'bond_topn_sectors': self.bond_topn_sectors,
            'bond_topn_sectors_pct': self.bond_topn_sectors_pct,
            'bond_topn_amount': self.bond_topn_amount,
            'bond_topn_window': self.bond_topn_window,
            'bond_topn_count': self.bond_topn_count,
            'bond_green_list': self.bond_green_list,
        }
    
    def is_stock_filter_active(self) -> bool:
        """股票过滤是否激活"""
        return any([
            self.stock_industry is not None,
            self.stock_topn_sectors > 0,
            self.stock_topn_sectors_pct > 0,
            self.stock_topn_window > 0,
            self.stock_topn_count > 0,
            self.stock_bond_filter,
        ])
    
    def is_bond_filter_active(self) -> bool:
        """债券过滤是否激活"""
        return any([
            self.bond_industry is not None,
            self.bond_topn_sectors > 0,
            self.bond_topn_sectors_pct > 0,
            self.bond_topn_amount > 0,
            self.bond_topn_window > 0,
            self.bond_topn_count > 0,
            self.bond_green_list,
        ])
