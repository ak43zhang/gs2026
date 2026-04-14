"""
股票-债券-行业 映射关系生成（优化版）

功能：
1. 从 data_industry_code_component_ths 表获取股票和行业信息
2. 从 data_bond_ths 表获取债券和正股信息
3. 从 data_bond_daily 表获取债券最新价格
4. 以股票为主，关联生成映射关系
5. 债券筛选条件：
   - 上市状态（有上市日期）
   - 债券收盘价在 120-250 之间（从 data_bond_daily 获取）
   - 过滤临近赎回日期的债券（风险控制）

输出字段：
- stock_code: 股票代码
- short_name: 股票简称
- bond_code: 债券代码（可为空）
- bond_name: 债券简称（可为空）
- industry_name: 行业名称
- bond_price: 债券收盘价
"""

import pandas as pd
from sqlalchemy import create_engine, text
from typing import Optional
from datetime import datetime, timedelta

from gs2026.utils import config_util, log_util
from pathlib import Path

logger = log_util.setup_logger(str(Path(__file__).absolute()))


def get_stock_bond_industry_mapping(
    url: Optional[str] = None,
    industry_table: str = "data_industry_code_component_ths",
    bond_table: str = "data_bond_ths",
    bond_daily_table: str = "data_bond_daily",
    min_bond_price: float = 120.0,
    max_bond_price: float = 250.0,
    redemption_days_threshold: int = 2,
    validate_1to1: bool = True
) -> pd.DataFrame:
    """
    生成股票-债券-行业映射关系 DataFrame（以股票为主）
    
    表结构说明：
    - data_industry_code_component_ths: stock_code, short_name, code(行业代码), name(行业名称)
    - data_bond_ths: 债券代码, 债券简称, 正股代码, 正股简称, 上市日期, 申购日期
    - data_bond_daily: bond_code, close(收盘价), date(日期)
    
    关联方式：
    - data_industry_code_component_ths.stock_code = data_bond_ths.正股代码 (LEFT JOIN)
    
    债券筛选条件：
    1. 已上市（上市日期 <= 今天）
    2. 债券收盘价在 [min_bond_price, max_bond_price] 范围内（从 data_bond_daily 获取最新价格）
    3. 不临近赎回日期（距离申购日期 > redemption_days_threshold 天）
    
    Args:
        url: 数据库连接URL，默认从配置文件读取
        industry_table: 行业成分股表名
        bond_table: 债券基础信息表名
        bond_daily_table: 债券日行情表名
        min_bond_price: 最小债券价格（默认120）
        max_bond_price: 最大债券价格（默认250）
        redemption_days_threshold: 赎回日期临近阈值（默认30天）
        validate_1to1: 是否验证并确保 1:1:1 关系
    
    Returns:
        包含 stock_code, short_name, bond_code, bond_name, industry_name, bond_price 的 DataFrame
        没有关联债券的股票，bond_code 和 bond_name 为 None
    """
    if url is None:
        url = config_util.get_config("common.url")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        with engine.connect() as conn:
            # 查询行业成分股表（以股票为主）
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
            
            # 获取每只债券的最新价格（使用各自最新有数据的日期）
            # 而不是使用全局最新日期，避免某些债券在最新日期无数据
            latest_price_query = f"""
                SELECT 
                    bond_code,
                    close as bond_price,
                    date as price_date
                FROM {bond_daily_table} t1
                WHERE close >= {min_bond_price}
                AND close <= {max_bond_price}
            """
            
            logger.info(f"查询债券最新价格: {bond_daily_table}, 范围 [{min_bond_price}, {max_bond_price}]")
            price_df = pd.read_sql(text(latest_price_query), conn)
            logger.info(f"符合价格条件的债券: {len(price_df)}")
            
            # 查询债券基础信息（带筛选条件）
            bond_query = f"""
                SELECT 
                    `债券代码` AS bond_code,
                    `债券简称` AS bond_name,
                    `正股代码` AS stock_code,
                    `正股简称` AS stock_name,
                    `上市日期` AS list_date,
                    `申购日期` AS apply_date
                FROM {bond_table}
                WHERE `正股代码` IS NOT NULL 
                  AND `正股代码` != ''
                  AND `上市日期` IS NOT NULL
                  AND `上市日期` <= '{today}'
                  AND (`申购日期` IS NULL OR `申购日期` < DATE_SUB('{today}', INTERVAL {redemption_days_threshold} DAY))
            """
            
            logger.info(f"查询债券基础信息: {bond_table}")
            bond_df = pd.read_sql(text(bond_query), conn)
            
            # 关联债券信息和价格
            bond_with_price = pd.merge(
                bond_df,
                price_df[['bond_code', 'bond_price']],
                on='bond_code',
                how='inner'
            )
            
            logger.info(f"有价格信息的债券: {len(bond_with_price)}")
        
        logger.info(f"行业成分股表记录数: {len(industry_df)}, 筛选后债券记录数: {len(bond_with_price)}")
        
        # 关联数据：以股票为主（LEFT JOIN）
        # 没有关联债券的股票也会保留，bond_code 和 bond_name 为 None
        merged_df = pd.merge(
            industry_df,
            bond_with_price,
            on="stock_code",
            how="left",
            suffixes=("", "_bond")
        )
        
        logger.info(f"合并后记录数: {len(merged_df)}")
        
        # 统计有债券和无债券的股票数量
        has_bond = merged_df['bond_code'].notna()
        logger.info(f"有债券关联的股票: {has_bond.sum()}, 无债券关联的股票: {(~has_bond).sum()}")
        
        # 验证并确保 1:1:1 关系（如果启用）
        if validate_1to1:
            # 1. 每个债券只对应一个行业（取第一个）- 但保留无债券的股票
            # 先分离有债券和无债券的数据
            has_bond_df = merged_df[merged_df['bond_code'].notna()].copy()
            no_bond_df = merged_df[merged_df['bond_code'].isna()].copy()
            
            # 有债券的数据去重（每个债券只对应一个股票）
            has_bond_df = has_bond_df.drop_duplicates(subset=["bond_code"], keep="first")
            
            # 2. 检查是否有股票关联了多个债券
            stock_counts = has_bond_df.groupby("stock_code").size()
            multi_stock = stock_counts[stock_counts > 1]
            if len(multi_stock) > 0:
                logger.warning(f"发现 {len(multi_stock)} 只股票关联了多个债券，保留第一个")
                # 每个股票保留第一个债券
                has_bond_df = has_bond_df.drop_duplicates(subset=["stock_code"], keep="first")
            
            # 合并有债券和无债券的数据
            merged_df = pd.concat([has_bond_df, no_bond_df], ignore_index=True)
        
        # 选择并重命名字段
        result_df = merged_df[["stock_code", "short_name", "bond_code", "bond_name", 
                              "industry_name", "bond_price"]].copy()
        
        # 清理空值（只清理股票代码，债券可以为空）
        result_df = result_df.dropna(subset=["stock_code"])
        result_df = result_df[result_df["stock_code"].str.strip() != ""]
        
        # 保留所有股票（包括没有债券的），bond_code 为空的显示为 None
        # 不再过滤掉没有债券的股票
        
        # 重置索引
        result_df = result_df.reset_index(drop=True)
        
        logger.info(f"最终映射记录数: {len(result_df)} (有债券: {result_df['bond_code'].notna().sum()}, "
                   f"无债券: {result_df['bond_code'].isna().sum()})")
        
        return result_df
        
    except Exception as e:
        logger.error(f"生成股票-债券-行业映射失败: {e}")
        raise
    finally:
        engine.dispose()


def get_mapping_with_sql(
    url: Optional[str] = None,
    industry_table: str = "data_industry_code_component_ths",
    bond_table: str = "data_bond_ths",
    bond_daily_table: str = "data_bond_daily",
    min_bond_price: float = 120.0,
    max_bond_price: float = 250.0,
    redemption_days_threshold: int = 30
) -> pd.DataFrame:
    """
    使用 SQL 直接关联查询生成映射关系（更高效，以股票为主）
    
    债券筛选条件：
    1. 已上市（上市日期 <= 今天）
    2. 债券收盘价在 [min_bond_price, max_bond_price] 范围内
    3. 不临近赎回日期
    
    Args:
        url: 数据库连接URL
        industry_table: 行业成分股表名
        bond_table: 债券基础信息表名
        bond_daily_table: 债券日行情表名
        min_bond_price: 最小债券价格
        max_bond_price: 最大债券价格
        redemption_days_threshold: 赎回日期临近阈值
    
    Returns:
        映射 DataFrame（以股票为主，bond_code 可为空）
    """
    if url is None:
        url = config_util.get_config("common.url")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        with engine.connect() as conn:
            # 获取最新日期
            latest_date_query = f"SELECT MAX(date) as max_date FROM {bond_daily_table}"
            latest_date_result = conn.execute(text(latest_date_query)).fetchone()
            latest_date = latest_date_result[0] if latest_date_result else today
            
            # SQL LEFT JOIN 查询（以股票为主）
            sql = f"""
                SELECT 
                    i.stock_code,
                    i.short_name,
                    b.`债券代码` AS bond_code,
                    b.`债券简称` AS bond_name,
                    i.name AS industry_name,
                    p.close AS bond_price
                FROM {industry_table} i
                LEFT JOIN {bond_table} b 
                    ON i.stock_code = b.`正股代码`
                    AND b.`上市日期` IS NOT NULL
                    AND b.`上市日期` <= '{today}'
                    AND (b.`申购日期` IS NULL OR b.`申购日期` < DATE_SUB('{today}', INTERVAL {redemption_days_threshold} DAY))
                LEFT JOIN {bond_daily_table} p 
                    ON b.`债券代码` = p.bond_code
                    AND p.date = '{latest_date}'
                    AND p.close >= {min_bond_price}
                    AND p.close <= {max_bond_price}
                WHERE i.stock_code IS NOT NULL 
                  AND i.stock_code != ''
                ORDER BY i.stock_code
            """
            
            logger.info("执行 SQL LEFT JOIN 查询（以股票为主）...")
            logger.info(f"债券价格筛选: [{min_bond_price}, {max_bond_price}]")
            result_df = pd.read_sql(text(sql), conn)
            
            # 清理空值（只清理股票代码）
            result_df = result_df.dropna(subset=["stock_code"])
            result_df = result_df[result_df["stock_code"].str.strip() != ""]
            
            # 保留所有股票（包括没有债券的），不再过滤
            # 去重确保每个债券只对应一个股票（但保留无债券的股票）
            result_df = result_df.drop_duplicates(
                subset=["stock_code"], 
                keep="first"
            ).reset_index(drop=True)
            
            # 统计
            has_bond = result_df['bond_code'].notna().sum()
            no_bond = result_df['bond_code'].isna().sum()
            logger.info(f"映射记录数: {len(result_df)} (有债券: {has_bond}, 无债券: {no_bond})")
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
        # 使用新版本的映射函数（以股票为主，带债券价格筛选）
        mapping_df = get_stock_bond_industry_mapping(
            min_bond_price=120.0,
            max_bond_price=250.0,
            redemption_days_threshold=2
        )
        
        print("\n映射结果预览:")
        print(mapping_df.head(10).to_string())
        print(f"\n总记录数: {len(mapping_df)}")
        print(f"有债券: {mapping_df['bond_code'].notna().sum()}")
        print(f"无债券: {mapping_df['bond_code'].isna().sum()}")
        
        # 债券价格分布
        if "bond_price" in mapping_df.columns:
            valid_prices = mapping_df[mapping_df['bond_price'].notna()]['bond_price']
            if len(valid_prices) > 0:
                print(f"\n债券价格统计:")
                print(f"  平均: {valid_prices.mean():.2f}")
                print(f"  最小: {valid_prices.min():.2f}")
                print(f"  最大: {valid_prices.max():.2f}")
        
        # 行业分布
        if "industry_name" in mapping_df.columns:
            print(f"\n行业分布:")
            print(mapping_df["industry_name"].value_counts().head(10).to_string())
        
        # 可选：保存到数据库
        # update_mapping_to_mysql(mapping_df, "data_stock_bond_industry_mapping")
        
        logger.info("生成完成!")
        
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
