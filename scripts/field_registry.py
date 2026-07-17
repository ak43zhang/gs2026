"""
统一字段回填引擎 - 字段注册表
声明式配置所有可回填字段的元数据。

字段分类：
  A类 (rank)     : 同tick排名，无状态
  B类 (min1)     : 1分钟差值，有状态（每分钟基准）
  C类 (slope)    : 趋势斜率，有状态（滑动窗口）
  D类 (market)   : 市场级指标，有状态（全市场聚合）
  E类 (ext_json) : 扩展JSON字段，有状态（per-bond缓存）
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FieldDef:
    """字段定义"""
    name: str                          # 数据库列名
    db_type: str                       # MySQL列类型
    category: str                      # 分类: rank / min1 / slope / market / ext_json
    depends: List[str] = field(default_factory=list)  # 依赖的源字段
    window: Optional[int] = None       # 滑动窗口大小（若适用）
    description: str = ''              # 字段说明


# ========== 窗口常量（与 monitor_bond.py 完全一致）==========
WINDOW_SHORT = 60    # 短期窗口（3分钟，每3秒1tick → 60点）
WINDOW_LONG = 300    # 长期窗口（15分钟，每3秒1tick → 300点）

# 【重构】扩展指标窗口扩展为15分钟
EXT_WINDOW_SECONDS = 900  # 扩展指标时间窗口（15分钟 = 900秒）【修改】150→900
EXT_HALF_LIFE = 30        # 指数加权半衰期（秒）
EXT_CACHE_MAXLEN = 300    # 【新增】deque maxlen（15分钟@3秒间隔）


# ========== 字段注册表 ==========
FIELD_REGISTRY: List[FieldDef] = [
    # === A类：同tick排名（无状态）===
    FieldDef(
        name='amount_rank',
        db_type='INT',
        category='rank',
        depends=['amount'],
        description='成交额排名（降序，method=min）'
    ),
    FieldDef(
        name='min1_amount_rank',
        db_type='INT',
        category='rank',
        depends=['min1_amount'],
        description='1分钟增量成交额排名（降序，method=min）'
    ),

    # === B类：1分钟差值（有状态：每分钟基准）===
    FieldDef(
        name='min1_change_pct',
        db_type='FLOAT',
        category='min1',
        depends=['change_pct'],
        description='1分钟内涨跌幅变化 = change_pct - base_change_pct'
    ),
    FieldDef(
        name='min1_amount',
        db_type='FLOAT',
        category='min1',
        depends=['amount'],
        description='1分钟内成交额增量 = amount - base_amount'
    ),

    # === C类：趋势斜率（有状态：per-bond滑动窗口）===
    FieldDef(
        name='slope_short',
        db_type='FLOAT',
        category='slope',
        depends=['change_pct'],
        window=WINDOW_SHORT,
        description=f'短期斜率（{WINDOW_SHORT}点窗口线性回归）'
    ),
    FieldDef(
        name='slope_long',
        db_type='FLOAT',
        category='slope',
        depends=['change_pct'],
        window=WINDOW_LONG,
        description=f'长期斜率（{WINDOW_LONG}点窗口线性回归）'
    ),
    FieldDef(
        name='peak_vol_bias',
        db_type='FLOAT',
        category='slope',
        depends=['amount', 'price'],
        description='放量高点偏离度 = (price - price_at_max_amount) / price_at_max_amount * 100'
    ),
    FieldDef(
        name='high_distance',
        db_type='FLOAT',
        category='slope',
        depends=['change_pct'],
        description='日内高点距离 = change_pct - max_change_pct'
    ),

    # === D类：市场级指标（有状态：全市场聚合）===
    FieldDef(
        name='mkt_slope_short',
        db_type='FLOAT',
        category='market',
        depends=['change_pct'],
        window=WINDOW_SHORT,
        description=f'大盘短期斜率（全市场平均change_pct的{WINDOW_SHORT}点窗口）'
    ),
    FieldDef(
        name='mkt_slope_long',
        db_type='FLOAT',
        category='market',
        depends=['change_pct'],
        window=WINDOW_LONG,
        description=f'大盘长期斜率（全市场平均change_pct的{WINDOW_LONG}点窗口）'
    ),
    FieldDef(
        name='mkt_peak_vol_bias',
        db_type='FLOAT',
        category='market',
        depends=['change_pct', 'amount'],
        description='大盘放量高点偏离 = avg_pct - pct_at_max_total_amount'
    ),
    FieldDef(
        name='mkt_high_distance',
        db_type='FLOAT',
        category='market',
        depends=['change_pct'],
        description='大盘高点距离 = avg_pct - max_avg_pct'
    ),
    # 大盘扩展指标(mkt_weighted_slope_2m, mkt_change_1m_pct, mkt_price_acceleration)
    # 已合并到 ext_indicators JSON 字段中，不再作为独立列

    # === E类：扩展JSON字段（有状态：per-bond时间缓存）===
    # 【重构】扩展为15分钟窗口，新增5m/15m斜率
    FieldDef(
        name='ext_indicators',
        db_type='JSON',
        category='ext_json',
        depends=['price', 'change_pct'],
        description='扩展指标JSON: weighted_slope_2m/5m/15m, change_1m_pct, price_acceleration, mkt_weighted_slope_2m/5m/15m, mkt_change_1m_pct, mkt_price_acceleration'
    ),
]


def get_field_names(category: Optional[str] = None) -> List[str]:
    """获取字段名列表，可按类别过滤"""
    if category is None:
        return [f.name for f in FIELD_REGISTRY]
    return [f.name for f in FIELD_REGISTRY if f.category == category]


def get_field_def(name: str) -> Optional[FieldDef]:
    """根据名称获取字段定义"""
    for f in FIELD_REGISTRY:
        if f.name == name:
            return f
    return None


def get_all_depends() -> set:
    """获取所有依赖的源字段集合"""
    deps = set()
    for f in FIELD_REGISTRY:
        deps.update(f.depends)
    return deps


def get_categories() -> List[str]:
    """获取所有类别（按计算顺序）"""
    # 顺序很重要：min1 → rank(依赖min1_amount) → slope → market → ext_json
    return ['min1', 'rank', 'slope', 'market', 'ext_json']


if __name__ == '__main__':
    print("=" * 60)
    print("统一字段回填引擎 - 字段注册表")
    print("=" * 60)
    for cat in get_categories():
        fields = [f for f in FIELD_REGISTRY if f.category == cat]
        print(f"\n【{cat}类】共 {len(fields)} 个字段:")
        for f in fields:
            print(f"  {f.name:20s} {f.db_type:6s} | {f.description}")
    print(f"\n总计: {len(FIELD_REGISTRY)} 个字段")
    print(f"依赖源字段: {sorted(get_all_depends())}")
