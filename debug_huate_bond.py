#!/usr/bin/env python3
"""排查华特转债股债联动标记问题"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import redis_util
from loguru import logger

def debug_huate_bond():
    redis_util.init_redis()
    
    date_str = "20260427"
    time_str = "09:56:57"
    
    logger.info("=" * 60)
    logger.info(f"排查时间: {date_str} {time_str}")
    logger.info("=" * 60)
    
    # 1. 获取股票上攻排行
    logger.info("\n【1】股票上攻排行:")
    gp_table = f"monitor_gp_top30_{date_str}"
    gp_df = redis_util.load_dataframe_by_key(f"{gp_table}:{time_str}", use_compression=False)
    
    if gp_df is not None and not gp_df.empty:
        logger.info(f"  股票排行数量: {len(gp_df)}")
        # 查找华特科技（正股）
        huate_stock = gp_df[gp_df['name'].str.contains('华特', na=False)]
        if not huate_stock.empty:
            logger.info(f"  华特科技在排行中:")
            logger.info(f"    {huate_stock[['code', 'name', 'total_score']].to_string()}")
        else:
            logger.info("  华特科技不在股票上攻排行中")
        
        # 显示前10
        logger.info("  前10名:")
        for idx, row in gp_df.head(10).iterrows():
            logger.info(f"    {idx+1}. {row.get('code', 'N/A')} {row.get('name', 'N/A')}")
    else:
        logger.error("  无法获取股票上攻排行")
    
    # 2. 获取债券上攻排行
    logger.info("\n【2】债券上攻排行:")
    zq_table = f"monitor_zq_top30_{date_str}"
    zq_df = redis_util.load_dataframe_by_key(f"{zq_table}:{time_str}", use_compression=False)
    
    if zq_df is not None and not zq_df.empty:
        logger.info(f"  债券排行数量: {len(zq_df)}")
        
        # 查找华特转债
        huate_bond = zq_df[zq_df['name'].str.contains('华特', na=False)]
        if not huate_bond.empty:
            logger.info(f"  华特转债在排行中:")
            cols = ['code', 'name', 'is_stock_ranked', 'stock_rank_pos', 'bond_code_display']
            available_cols = [c for c in cols if c in huate_bond.columns]
            logger.info(f"    {huate_bond[available_cols].to_string()}")
            
            # 检查正股代码
            if 'stock_code' in huate_bond.columns:
                logger.info(f"    正股代码: {huate_bond['stock_code'].values[0]}")
        else:
            logger.info("  华特转债不在债券上攻排行中")
        
        # 检查是否有标记字段
        if 'is_stock_ranked' in zq_df.columns:
            marked = zq_df[zq_df['is_stock_ranked'] == True]
            logger.info(f"  已标记债券数量: {len(marked)}")
            if len(marked) > 0:
                logger.info("  已标记债券:")
                for idx, row in marked.head(5).iterrows():
                    logger.info(f"    {row.get('bond_code_display', row.get('code', 'N/A'))} - 正股排名:{row.get('stock_rank_pos', 'N/A')}")
        else:
            logger.warning("  无is_stock_ranked字段，标记可能未生效")
    else:
        logger.error("  无法获取债券上攻排行")
    
    # 3. 获取债券实时数据（检查正股代码）
    logger.info("\n【3】债券实时数据:")
    sssj_table = f"monitor_zq_sssj_{date_str}"
    sssj_df = redis_util.load_dataframe_by_key(f"{sssj_table}:{time_str}", use_compression=False)
    
    if sssj_df is not None and not sssj_df.empty:
        huate_sssj = sssj_df[sssj_df['bond_name'].str.contains('华特', na=False)]
        if not huate_sssj.empty:
            logger.info(f"  华特转债实时数据:")
            # 检查正股代码字段
            if 'stock_code' in huate_sssj.columns:
                logger.info(f"    正股代码: {huate_sssj['stock_code'].values[0]}")
            else:
                logger.warning("    无stock_code字段")
            
            # 检查所有字段
            logger.info(f"    可用字段: {huate_sssj.columns.tolist()}")
        else:
            logger.info("  华特转债不在实时数据中")
    else:
        logger.error("  无法获取债券实时数据")
    
    logger.info("\n" + "=" * 60)

if __name__ == "__main__":
    debug_huate_bond()
