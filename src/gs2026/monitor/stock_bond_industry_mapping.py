"""
股票-债券-行业 映射关系生成

功能：
1. 从 data_industry_code_component_ths 表获取股票和行业信息
2. 从 data_bond_ths 表获取债券和正股信息
3. 关联生成 1:1:1 的映射关系

输出字段：
- stock_code: 股票代码
- short_name: 股票简称
- bond_code: 债券代码
- bond_name: 债券简称
- industry_name: 行业名称
"""

import pandas as pd
from sqlalchemy import create_engine, text
from typing import Optional

from gs2026.utils import config_util, log_util
from pathlib import Path

logger = log_util.setup_logger(str(Path(__file__).absolute()))


def get_stock_bond_industry_mapping(
    url: Optional[str] = None,
    industry_table: str = "data_industry_code_component_ths",
    bond_table: str = "data_bond_ths",
    validate_1to1: bool = True
) -> pd.DataFrame:
    """
    生成股票-债券-行业 1:1:1 映射关系 DataFrame
    
    表结构说明：
    - data_industry_code_component_ths: stock_code, short_name, code(行业代码), name(行业名称)
    - data_bond_ths: 债券代码, 债券简称, 正股代码, 正股简称
    
    关联方式：
    - data_industry_code_component_ths.stock_code = data_bond_ths.正股代码
    
    Args:
        url: 数据库连接URL，默认从配置文件读取
        industry_table: 行业成分股表名
        bond_table: 债券表名
        validate_1to1: 是否验证并确保 1:1:1 关系
    
    Returns:
        包含 stock_code, short_name, bond_code, bond_name, industry_name 的 DataFrame
    

    """
    if url is None:
        url = config_util.get_config("common.url")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    try:
        with engine.connect() as conn:
            # 查询行业成分股表
            # 字段: stock_code, short_name, code(行业代码), name(行业名称)
            industry_query = f"""
                SELECT 
                    stock_code,
                    short_name,
                    code AS industry_code,
                    name AS industry_name
                FROM {industry_table}
                WHERE stock_code IS NOT NULL AND stock_code != ''
            """
            
            logger.info(f"查询行业成分股表: {industry_table}")
            industry_df = pd.read_sql(text(industry_query), conn)
            
            # 查询债券表
            # 字段: 债券代码, 债券简称, 正股代码, 正股简称
            bond_query = f"""
                SELECT 
                    `债券代码` AS bond_code,
                    `债券简称` AS bond_name,
                    `正股代码` AS stock_code,
                    `正股简称` AS stock_name
                FROM {bond_table}
                WHERE `正股代码` IS NOT NULL AND `正股代码` != ''
            """
            
            logger.info(f"查询债券表: {bond_table}")
            bond_df = pd.read_sql(text(bond_query), conn)
        
        logger.info(f"行业成分股表记录数: {len(industry_df)}, 债券表记录数: {len(bond_df)}")
        
        # 关联数据：债券 -> 行业成分股 (通过 stock_code / 正股代码 关联)
        merged_df = pd.merge(
            bond_df,
            industry_df,
            on="stock_code",
            how="inner",
            suffixes=("", "_industry")
        )
        
        logger.info(f"合并后记录数: {len(merged_df)}")
        
        # 去除股票简称重复字段（如果有）
        if "short_name_industry" in merged_df.columns:
            merged_df = merged_df.drop(columns=["short_name_industry"])
        
        # 验证并确保 1:1:1 关系
        if validate_1to1:
            # 1. 每个债券只对应一个行业（取第一个）
            merged_df = merged_df.drop_duplicates(subset=["bond_code"], keep="first")
            
            # 2. 检查是否有重复
            stock_counts = merged_df.groupby("stock_code").size()
            bond_counts = merged_df.groupby("bond_code").size()
            
            multi_stock = stock_counts[stock_counts > 1]
            if len(multi_stock) > 0:
                logger.warning(f"发现 {len(multi_stock)} 只股票关联了多个债券: {multi_stock.index[:5].tolist()}...")
                # 每个股票保留第一个债券
                merged_df = merged_df.drop_duplicates(subset=["stock_code"], keep="first")
        
        # 选择并重命名字段
        result_df = merged_df[["stock_code", "short_name", "bond_code", "bond_name", "industry_name"]].copy()
        
        # 清理空值
        result_df = result_df.dropna(subset=["stock_code", "bond_code"])
        result_df = result_df[result_df["stock_code"].str.strip() != ""]
        result_df = result_df[result_df["bond_code"].str.strip() != ""]
        
        # 重置索引
        result_df = result_df.reset_index(drop=True)
        
        logger.info(f"最终映射记录数: {len(result_df)}")
        
        return result_df
        
    except Exception as e:
        logger.error(f"生成股票-债券-行业映射失败: {e}")
        raise
    finally:
        engine.dispose()


def get_mapping_with_sql(
    url: Optional[str] = None,
    industry_table: str = "data_industry_code_component_ths",
    bond_table: str = "data_bond_ths"
) -> pd.DataFrame:
    """
    使用 SQL 直接关联查询生成映射关系（更高效）
    
    适用于表结构已确认的情况
    
    Args:
        url: 数据库连接URL
        industry_table: 行业成分股表名
        bond_table: 债券表名
    
    Returns:
        映射 DataFrame
    """
    if url is None:
        url = config_util.get_config("common.url")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    # SQL 关联查询
    sql = f"""
        SELECT 
            b.`正股代码` AS stock_code,
            b.`正股简称` AS short_name,
            b.`债券代码` AS bond_code,
            b.`债券简称` AS bond_name,
            i.name AS industry_name
        FROM {bond_table} b
        INNER JOIN {industry_table} i 
            ON b.`正股代码` = i.stock_code
        WHERE b.`正股代码` IS NOT NULL 
          AND b.`正股代码` != ''
        ORDER BY b.`债券代码`
    """
    
    try:
        with engine.connect() as conn:
            logger.info("执行 SQL 关联查询...")
            result_df = pd.read_sql(text(sql), conn)
            
            # 清理空值
            result_df = result_df.dropna(subset=["stock_code", "bond_code"])
            result_df = result_df[result_df["stock_code"].str.strip() != ""]
            result_df = result_df[result_df["bond_code"].str.strip() != ""]
            
            # 去重确保 1:1:1
            result_df = result_df.drop_duplicates(
                subset=["bond_code"], 
                keep="first"
            ).reset_index(drop=True)
            
            logger.info(f"映射记录数: {len(result_df)}")
            return result_df
            
    except Exception as e:
        logger.error(f"SQL 查询失败: {e}")
        raise
    finally:
        engine.dispose()


def update_mapping_to_mysql(
    df: pd.DataFrame,
    target_table: str = "data_stock_bond_industry_mapping",
    url: Optional[str] = None,
    if_exists: str = "replace"
) -> bool:
    """
    将映射关系保存到 MySQL 表
    
    Args:
        df: 映射 DataFrame
        target_table: 目标表名
        url: 数据库连接URL
        if_exists: 'replace'(覆盖) | 'append'(追加) | 'fail'(存在则失败)
    
    Returns:
        是否成功
    """
    if url is None:
        url = config_util.get_config("common.url")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    try:
        with engine.begin() as conn:
            df.to_sql(
                name=target_table,
                con=conn,
                if_exists=if_exists,
                index=False
            )
            logger.info(f"映射已保存到表: {target_table}, 记录数: {len(df)}")
            return True
    except Exception as e:
        logger.error(f"保存映射失败: {e}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    import sys
    
    logger.info("=" * 50)
    logger.info("开始生成股票-债券-行业映射关系")
    logger.info("=" * 50)
    
    try:

        df = get_stock_bond_industry_mapping()
        print(df)
        # 使用 SQL 高效版本
        mapping_df = get_mapping_with_sql()
        
        print("\n映射结果预览:")
        print(mapping_df.head(10).to_string())
        print(f"\n总记录数: {len(mapping_df)}")
        
        # 行业分布
        if "industry_name" in mapping_df.columns:
            print(f"\n行业分布:")
            print(mapping_df["industry_name"].value_counts().head(10).to_string())
        
        # 可选：保存到数据库
        # update_mapping_to_mysql(mapping_df, "data_stock_bond_industry_mapping")
        
        logger.info("生成完成!")
        
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        sys.exit(1)
