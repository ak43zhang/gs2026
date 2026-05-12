"""
派生字段引擎 - 可扩展的实时计算字段框架

新增一个字段只需：
1. 在 DERIVED_FIELDS 中注册
2. routes/monitor.py DERIVED_DISPLAY_FIELDS 添加字段名
3. 前端 STOCK_COLUMNS + renderStockCell 追加

数据流：
  每3秒tick -> calculate_all_derived(df_now, df_prev_main, top30_codes)
  -> 更新df_now中所有派生字段 -> 随sssj表一起保存
"""

import pandas as pd
from typing import Set, Optional, Dict
from gs2026.utils import log_util

logger = log_util.setup_logger("derived_fields")


# ============ 派生字段注册表 ============
DERIVED_FIELDS = [
    {
        'name': 'consecutive_attacks',
        'default': 0,
        'dtype': 'int',
        'calc': lambda prev, in_top30: (prev + 1) if in_top30 else 0,
    },
    # ===== 后续新增字段在此追加 =====
    # {
    #     'name': 'top30_total_count',
    #     'default': 0,
    #     'dtype': 'int',
    #     'calc': lambda prev, in_top30: (prev + 1) if in_top30 else prev,
    # },
]


def calculate_all_derived(
    df_now: pd.DataFrame,
    df_prev_main: Optional[pd.DataFrame],
    top30_codes: Set[str],
    code_col: str = 'stock_code'
) -> pd.DataFrame:
    """
    统一计算所有派生字段
    
    Args:
        df_now: 当前tick全市场数据
        df_prev_main: 上一tick全市场数据（含前一时刻的派生字段）
        top30_codes: 当前tick进入top30的股票代码集合
        code_col: 股票代码列名
    
    Returns:
        更新了所有派生字段的 df_now
    """
    if not DERIVED_FIELDS:
        return df_now
    
    # 确定code列
    if code_col not in df_now.columns:
        if 'stock_code' in df_now.columns:
            code_col = 'stock_code'
        elif 'code' in df_now.columns:
            code_col = 'code'
        else:
            logger.warning("df_now中找不到code列，跳过派生字段计算")
            for field in DERIVED_FIELDS:
                df_now[field['name']] = field['default']
            return df_now
    
    # 1. 构建上一tick的字段值映射
    prev_maps: Dict[str, dict] = {}
    if df_prev_main is not None and not df_prev_main.empty:
        prev_code_col = code_col
        if prev_code_col not in df_prev_main.columns:
            for candidate in ['stock_code', 'code']:
                if candidate in df_prev_main.columns:
                    prev_code_col = candidate
                    break
        
        for field in DERIVED_FIELDS:
            fname = field['name']
            if fname in df_prev_main.columns:
                try:
                    prev_maps[fname] = dict(zip(
                        df_prev_main[prev_code_col].astype(str),
                        pd.to_numeric(df_prev_main[fname], errors='coerce').fillna(field['default'])
                    ))
                except Exception:
                    prev_maps[fname] = {}
            else:
                prev_maps[fname] = {}
    else:
        for field in DERIVED_FIELDS:
            prev_maps[field['name']] = {}
    
    # 2. 计算所有派生字段（向量化）
    codes = df_now[code_col].astype(str)
    in_top30_series = codes.isin(top30_codes)
    
    for field in DERIVED_FIELDS:
        fname = field['name']
        default = field['default']
        calc_fn = field['calc']
        pmap = prev_maps[fname]
        
        # 获取上一tick的值
        prev_values = codes.map(lambda c: pmap.get(c, default))
        
        # 应用计算函数
        df_now[fname] = [
            calc_fn(int(pv), it)
            for pv, it in zip(prev_values, in_top30_series)
        ]
        
        # 类型转换
        if field['dtype'] == 'int':
            df_now[fname] = df_now[fname].astype(int)
        elif field['dtype'] == 'float':
            df_now[fname] = df_now[fname].astype(float)
    
    non_zero = (df_now['consecutive_attacks'] > 0).sum() if 'consecutive_attacks' in df_now.columns else 0
    if non_zero > 0:
        logger.info(f"派生字段计算完成: {non_zero}只股票有连续上攻记录")
    
    return df_now
