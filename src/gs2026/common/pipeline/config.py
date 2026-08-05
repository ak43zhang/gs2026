"""
过滤配置类

字段命名与前端 backtrace.js / monitor.html 过滤器保持一致语义。
每个"前N"过滤器支持 mode（'ranking' | 'predicate'）：
  - ranking: 基于候选池S取前N
  - predicate: 基于全部原始数据取前N
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class FilterConfig:
    """过滤配置"""

    # ===== 股票过滤配置 =====
    stock_industry: Optional[str] = None       # 行业联动（industry_name精确匹配）
    stock_bond_filter: bool = False            # 转债模式：仅显示有转债的股票
    stock_green_list: bool = False             # 隐藏绿名单
    stock_topn_sectors: int = 0                # 仅行业次数前N
    stock_topn_sectors_pct: int = 0            # 仅行业涨幅前N
    stock_topn_window: int = 0                 # 仅前N区间次数
    stock_topn_count: int = 0                  # 仅前N次数
    # 模式（'ranking' | 'predicate'）
    stock_topn_sectors_mode: str = 'ranking'
    stock_topn_sectors_pct_mode: str = 'ranking'
    stock_topn_window_mode: str = 'ranking'
    stock_topn_count_mode: str = 'ranking'

    # ===== 债券过滤配置 =====
    bond_industry: Optional[str] = None        # 行业联动
    bond_green_list: bool = False              # 隐藏绿名单
    bond_topn_sectors: int = 0                 # 仅行业次数前N
    bond_topn_sectors_pct: int = 0             # 仅行业涨幅前N
    bond_topn_amount: int = 0                  # 仅前N金额
    bond_topn_window: int = 0                  # 仅前N区间次数
    bond_topn_count: int = 0                   # 仅前N次数
    bond_min1_amount_topn: int = 0             # 仅1分钟金额前N
    bond_min1_change_min: float = 0.0          # 1分钟涨幅 > N（%）
    # 模式
    bond_topn_sectors_mode: str = 'ranking'
    bond_topn_sectors_pct_mode: str = 'ranking'
    bond_topn_amount_mode: str = 'ranking'
    bond_topn_window_mode: str = 'ranking'
    bond_topn_count_mode: str = 'ranking'

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterConfig':
        """从字典创建配置（兼容前端多种字段命名）"""
        def _int(*keys):
            for k in keys:
                if k in data and data[k] is not None:
                    try:
                        return int(data[k])
                    except (ValueError, TypeError):
                        return 0
            return 0

        def _float(*keys):
            for k in keys:
                if k in data and data[k] is not None:
                    try:
                        return float(data[k])
                    except (ValueError, TypeError):
                        return 0.0
            return 0.0

        def _bool(*keys):
            for k in keys:
                if k in data and data[k] is not None:
                    return bool(data[k])
            return False

        def _str(*keys):
            for k in keys:
                if k in data and data[k]:
                    return str(data[k])
            return None

        def _mode(*keys):
            for k in keys:
                if k in data and data[k] in ('ranking', 'predicate'):
                    return data[k]
            return 'ranking'

        return cls(
            # 股票：兼容 stock_industry / industry
            stock_industry=_str('stock_industry', 'industry'),
            stock_bond_filter=_bool('stock_bond_filter', 'bond_mode', 'bond'),
            stock_green_list=_bool('stock_green_list', 'green_list_stock'),
            stock_topn_sectors=_int('stock_topn_sectors', 'topn_industry', 'topn_sectors'),
            stock_topn_sectors_pct=_int('stock_topn_sectors_pct', 'topn_industry_pct', 'topn_sectors_pct'),
            stock_topn_window=_int('stock_topn_window', 'topn_window'),
            stock_topn_count=_int('stock_topn_count', 'topn_count'),
            stock_topn_sectors_mode=_mode('stock_topn_sectors_mode', 'topn_sectors_mode'),
            stock_topn_sectors_pct_mode=_mode('stock_topn_sectors_pct_mode', 'topn_sectors_pct_mode'),
            stock_topn_window_mode=_mode('stock_topn_window_mode', 'topn_window_mode'),
            stock_topn_count_mode=_mode('stock_topn_count_mode', 'topn_count_mode'),
            # 债券
            bond_industry=_str('bond_industry'),
            bond_green_list=_bool('bond_green_list', 'green_list'),
            bond_topn_sectors=_int('bond_topn_sectors', 'bond_topn_industry'),
            bond_topn_sectors_pct=_int('bond_topn_sectors_pct', 'bond_topn_industry_pct'),
            bond_topn_amount=_int('bond_topn_amount', 'topn_amount'),
            bond_topn_window=_int('bond_topn_window'),
            bond_topn_count=_int('bond_topn_count'),
            bond_min1_amount_topn=_int('bond_min1_amount_topn', 'min1_amount_topn'),
            bond_min1_change_min=_float('bond_min1_change_min', 'min1_change_min'),
            bond_topn_sectors_mode=_mode('bond_topn_sectors_mode'),
            bond_topn_sectors_pct_mode=_mode('bond_topn_sectors_pct_mode'),
            bond_topn_amount_mode=_mode('bond_topn_amount_mode'),
            bond_topn_window_mode=_mode('bond_topn_window_mode'),
            bond_topn_count_mode=_mode('bond_topn_count_mode'),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'stock_industry': self.stock_industry,
            'stock_bond_filter': self.stock_bond_filter,
            'stock_green_list': self.stock_green_list,
            'stock_topn_sectors': self.stock_topn_sectors,
            'stock_topn_sectors_pct': self.stock_topn_sectors_pct,
            'stock_topn_window': self.stock_topn_window,
            'stock_topn_count': self.stock_topn_count,
            'stock_topn_sectors_mode': self.stock_topn_sectors_mode,
            'stock_topn_sectors_pct_mode': self.stock_topn_sectors_pct_mode,
            'stock_topn_window_mode': self.stock_topn_window_mode,
            'stock_topn_count_mode': self.stock_topn_count_mode,
            'bond_industry': self.bond_industry,
            'bond_green_list': self.bond_green_list,
            'bond_topn_sectors': self.bond_topn_sectors,
            'bond_topn_sectors_pct': self.bond_topn_sectors_pct,
            'bond_topn_amount': self.bond_topn_amount,
            'bond_topn_window': self.bond_topn_window,
            'bond_topn_count': self.bond_topn_count,
            'bond_min1_amount_topn': self.bond_min1_amount_topn,
            'bond_min1_change_min': self.bond_min1_change_min,
            'bond_topn_sectors_mode': self.bond_topn_sectors_mode,
            'bond_topn_sectors_pct_mode': self.bond_topn_sectors_pct_mode,
            'bond_topn_amount_mode': self.bond_topn_amount_mode,
            'bond_topn_window_mode': self.bond_topn_window_mode,
            'bond_topn_count_mode': self.bond_topn_count_mode,
        }

    def is_stock_filter_active(self) -> bool:
        """股票过滤是否激活"""
        return any([
            self.stock_industry is not None,
            self.stock_bond_filter,
            self.stock_green_list,
            self.stock_topn_sectors > 0,
            self.stock_topn_sectors_pct > 0,
            self.stock_topn_window > 0,
            self.stock_topn_count > 0,
        ])

    def is_bond_filter_active(self) -> bool:
        """债券过滤是否激活"""
        return any([
            self.bond_industry is not None,
            self.bond_green_list,
            self.bond_topn_sectors > 0,
            self.bond_topn_sectors_pct > 0,
            self.bond_topn_amount > 0,
            self.bond_topn_window > 0,
            self.bond_topn_count > 0,
            self.bond_min1_amount_topn > 0,
            self.bond_min1_change_min > 0,
        ])
