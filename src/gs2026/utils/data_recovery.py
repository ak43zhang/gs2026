"""
数据恢复工具 - 从实时数据恢复所有派生数据

用法：
    from gs2026.utils.data_recovery import recover_data
    recover_data('20260323', asset_type='stock')
    recover_data('20260323', asset_type='bond')
    recover_data('20260323', asset_type='industry')
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text
from tqdm import tqdm

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from gs2026.utils import config_util, redis_util
from gs2026.utils.log_util import setup_logger

# 从 monitor_stock 导入核心函数
from gs2026.monitor.monitor_stock import culculate_gp_apqd_top30
from gs2026.monitor.monitor_bond import culculate_zq_apqd_top30
from gs2026.monitor.monitor_industry import culculate_hy_apqd_top30

# 初始化日志
logger = setup_logger(str(Path(__file__).absolute()))

# 数据库连接配置
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()

# Redis 配置
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)


def get_table_times(table_name: str) -> list:
    """获取表中所有时间点"""
    try:
        query = f"SELECT DISTINCT time FROM {table_name} ORDER BY time"
        df = pd.read_sql(query, con)
        return df['time'].tolist()
    except Exception as e:
        logger.error(f"获取 {table_name} 时间点失败: {e}")
        return []


def load_data_by_time(table_name: str, time_str: str) -> Optional[pd.DataFrame]:
    """按时间点加载数据"""
    try:
        query = f"SELECT * FROM {table_name} WHERE time = '{time_str}'"
        df = pd.read_sql(query, con)
        return df if not df.empty else None
    except Exception as e:
        logger.error(f"加载 {table_name} {time_str} 数据失败: {e}")
        return None


def clean_mysql_data(date_str: str, asset_type: str = 'all') -> None:
    """
    清理 MySQL 中的派生数据
    
    Args:
        date_str: 日期字符串
        asset_type: 'stock' | 'bond' | 'industry' | 'all'
    """
    config = {
        'stock': {
            'tables': [f"monitor_gp_apqd_{date_str}", f"monitor_gp_top30_{date_str}"],
            'rank_tables': ["rank_stock"]
        },
        'bond': {
            'tables': [f"monitor_zq_apqd_{date_str}", f"monitor_zq_top30_{date_str}"],
            'rank_tables': ["rank_bond"]
        },
        'industry': {
            'tables': [f"monitor_hy_apqd_{date_str}", f"monitor_hy_top30_{date_str}"],
            'rank_tables': ["rank_industry"]
        }
    }
    
    if asset_type == 'all':
        tables_to_clean = []
        rank_tables_to_clean = []
        for cfg in config.values():
            tables_to_clean.extend(cfg['tables'])
            rank_tables_to_clean.extend(cfg['rank_tables'])
    elif asset_type in config:
        tables_to_clean = config[asset_type]['tables']
        rank_tables_to_clean = config[asset_type]['rank_tables']
    else:
        logger.error(f"不支持的资产类型: {asset_type}")
        return
    
    # 清理派生表
    for table in tables_to_clean:
        try:
            delete_sql = text(f"DROP TABLE IF EXISTS {table}")
            con.execute(delete_sql)
            con.commit()
            logger.info(f"已清理 MySQL 表: {table}")
        except Exception as e:
            logger.warning(f"清理 {table} 失败: {e}")
    
    # 清理 rank 表（按日期删除）
    for table in set(rank_tables_to_clean):  # 去重
        try:
            delete_sql = text(f"DELETE FROM {table} WHERE date = '{date_str}'")
            con.execute(delete_sql)
            con.commit()
            logger.info(f"已清理 MySQL rank 表: {table}, date={date_str}")
        except Exception as e:
            logger.warning(f"清理 {table} 失败: {e}")


def clean_redis_data(date_str: str, asset_type: str = 'all') -> None:
    """
    清理 Redis 中的相关数据
    
    Args:
        date_str: 日期字符串
        asset_type: 'stock' | 'bond' | 'industry' | 'all'
    """
    config = {
        'stock': {
            'rank_keys': [f"rank:stock:code_{date_str}", f"rank:stock:code_name_{date_str}"],
            'data_keys': [
                f"monitor_gp_sssj_{date_str}:*",
                f"monitor_gp_apqd_{date_str}:*",
                f"monitor_gp_top30_{date_str}:*",
            ]
        },
        'bond': {
            'rank_keys': [f"rank:bond:code_{date_str}", f"rank:bond:code_name_{date_str}"],
            'data_keys': [
                f"monitor_zq_sssj_{date_str}:*",
                f"monitor_zq_apqd_{date_str}:*",
                f"monitor_zq_top30_{date_str}:*",
            ]
        },
        'industry': {
            'rank_keys': [f"rank:industry:code_{date_str}", f"rank:industry:code_name_{date_str}"],
            'data_keys': [
                f"monitor_hy_sssj_{date_str}:*",
                f"monitor_hy_apqd_{date_str}:*",
                f"monitor_hy_top30_{date_str}:*",
            ]
        }
    }
    
    if asset_type == 'all':
        patterns = []
        for cfg in config.values():
            patterns.extend(cfg['rank_keys'])
            patterns.extend(cfg['data_keys'])
    elif asset_type in config:
        cfg = config[asset_type]
        patterns = cfg['rank_keys'] + cfg['data_keys']
    else:
        logger.error(f"不支持的资产类型: {asset_type}")
        return

    for pattern in patterns:
        try:
            deleted = redis_util.delete_redis_keys_by_prefix(pattern, batch_size=1000, use_unlink=True)
            logger.info(f"已清理 Redis 键: {pattern}, 删除 {deleted} 个")
        except Exception as e:
            logger.warning(f"清理 Redis {pattern} 失败: {e}")


def save_dataframe(df: pd.DataFrame, table_name: str, time_str: str, expire_seconds: int = 64800) -> None:
    """保存 DataFrame 到 MySQL 和 Redis"""
    if df is None or df.empty:
        return
    
    try:
        df['time'] = time_str
        df.to_sql(table_name, con=engine, if_exists='append', index=False)
        redis_util.save_dataframe_to_redis(df, table_name, time_str, expire_seconds, use_compression=False)
        logger.debug(f"已保存 {table_name} {time_str} 数据，共 {len(df)} 条")
    except Exception as e:
        logger.error(f"保存 {table_name} {time_str} 失败: {e}")


def process_group_to_redis(time_val, group_df, table_name, time_column, expire_seconds=64800):
    """处理单个时间点分组 - 写入 Redis"""
    if group_df.empty:
        return
    
    if pd.api.types.is_datetime64_any_dtype(group_df[time_column]):
        time_str = group_df[time_column].iloc[0].strftime('%H:%M:%S')
    else:
        time_str = str(time_val)
    
    try:
        redis_util.save_dataframe_to_redis(
            group_df, table_name, time_str, expire_seconds, use_compression=False
        )
    except Exception as e:
        logger.error(f"写入 Redis 失败 {table_name} {time_str}: {e}")


def restore_realtime_to_redis(table_name: str, time_column: str = 'time',
                               max_workers: int = 10, expire_seconds: int = 64800) -> bool:
    """将 MySQL 实时数据并发写入 Redis"""
    logger.info(f"开始将 {table_name} 数据并发写入 Redis...")
    
    try:
        logger.info("正在从 MySQL 加载全量数据...")
        sql = f"SELECT * FROM {table_name}"
        df_all = pd.read_sql(sql, engine)
        
        if df_all.empty:
            logger.warning(f"{table_name} 表无数据")
            return False
        
        logger.info(f"加载完成，总行数: {len(df_all)}")
        
        grouped = df_all.groupby(time_column)
        total_groups = len(grouped)
        logger.info(f"共 {total_groups} 个时间点")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_time = {}
            for time_val, group_df in grouped:
                future = executor.submit(
                    process_group_to_redis,
                    time_val, group_df, table_name, time_column, expire_seconds
                )
                future_to_time[future] = time_val
            
            for future in tqdm(as_completed(future_to_time), total=total_groups,
                              desc="写入 Redis", unit="时间点"):
                try:
                    future.result()
                except Exception as e:
                    t = future_to_time[future]
                    logger.error(f"时间点 {t} 处理失败: {e}")
        
        logger.info(f"Redis 恢复完成！共处理 {total_groups} 个时间点")
        return True
        
    except Exception as e:
        logger.error(f"恢复实时数据到 Redis 失败: {e}")
        return False


def recover_data(date_str: str, asset_type: str = 'stock', clean_first: bool = True,
                 restore_redis_realtime: bool = True) -> bool:
    """
    恢复指定日期的监控数据

    Args:
        date_str: 日期字符串 YYYYMMDD
        asset_type: 资产类型，'stock' | 'bond' | 'industry'
        clean_first: 是否先清理旧数据
        restore_redis_realtime: 是否先将实时数据恢复到 Redis

    Returns:
        是否成功
    """
    logger.info(f"开始恢复 {date_str} {asset_type} 的数据...")

    config = {
        'stock': {
            'source_table': f'monitor_gp_sssj_{date_str}',
            'calculate_func': culculate_gp_apqd_top30,
        },
        'bond': {
            'source_table': f'monitor_zq_sssj_{date_str}',
            'calculate_func': culculate_zq_apqd_top30,
        },
        'industry': {
            'source_table': f'monitor_hy_sssj_{date_str}',
            'calculate_func': culculate_hy_apqd_top30,
        }
    }

    if asset_type not in config:
        logger.error(f"不支持的资产类型: {asset_type}")
        return False

    cfg = config[asset_type]
    source_table = cfg['source_table']
    calculate_func = cfg['calculate_func']

    if clean_first:
        logger.info("清理旧数据...")
        clean_mysql_data(date_str, asset_type=asset_type)
        clean_redis_data(date_str, asset_type=asset_type)

    if restore_redis_realtime:
        logger.info(f"步骤1: 将实时数据恢复到 Redis...")
        success = restore_realtime_to_redis(source_table, max_workers=10)
        if not success:
            logger.warning("实时数据 Redis 恢复失败，继续执行后续步骤")

    logger.info(f"步骤2: 读取源表时间点: {source_table}")

    times = get_table_times(source_table)
    if not times:
        logger.error(f"未找到 {source_table} 的数据")
        return False

    logger.info(f"找到 {len(times)} 个时间点，从 {times[0]} 到 {times[-1]}")

    WINDOW_SECONDS = 15

    for i, time_now in enumerate(times):
        try:
            current_time = datetime.strptime(time_now, "%H:%M:%S")
            prev_time_obj = current_time - timedelta(seconds=WINDOW_SECONDS)
            time_prev = prev_time_obj.strftime("%H:%M:%S")

            if time_prev not in times:
                logger.debug(f"{time_now} 的15秒前时间点 {time_prev} 不在列表中，跳过")
                continue

            df_now = redis_util.load_dataframe_by_key(f"{source_table}:{time_now}", use_compression=False)
            df_prev = redis_util.load_dataframe_by_key(f"{source_table}:{time_prev}", use_compression=False)

            if df_now is None or df_now.empty or df_prev is None or df_prev.empty:
                logger.warning(f"{time_now} 或 {time_prev} Redis 数据缺失，跳过")
                continue

            loop_start = datetime.strptime(f"{date_str} {time_now}", "%Y%m%d %H:%M:%S")
            calculate_func(df_now, df_prev, date_str, time_now, loop_start)

            if (i + 1) % 10 == 0:
                logger.info(f"已处理 {i + 1}/{len(times)} 个时间点")

        except Exception as e:
            logger.error(f"处理 {time_now} 时出错: {e}")
            continue

    logger.info(f"数据恢复完成！共处理 {len(times)} 个时间点")
    return True


def recover_stock_data(date_str: str, clean_first: bool = True,
                       restore_redis_realtime: bool = True) -> bool:
    """恢复股票数据（兼容旧接口）"""
    return recover_data(date_str, asset_type='stock', clean_first=clean_first,
                       restore_redis_realtime=restore_redis_realtime)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='恢复监控数据')
    parser.add_argument('date', help='日期，格式 YYYYMMDD')
    parser.add_argument('--type', choices=['stock', 'bond', 'industry'],
                       default='stock', help='资产类型')
    parser.add_argument('--no-clean', action='store_true', help='不清理旧数据')
    parser.add_argument('--no-redis', action='store_true', help='不恢复实时数据到Redis')

    args = parser.parse_args()

    success = recover_data(args.date, asset_type=args.type,
                          clean_first=not args.no_clean,
                          restore_redis_realtime=not args.no_redis)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    # main()
    clean_redis_data('20260323', 'all')
    # 恢复 20260323 的股票数据
    # recover_data('20260320', asset_type='stock', clean_first=True, restore_redis_realtime=True)
    #
    # # 恢复 20260323 的债券数据（需要时取消注释）
    # recover_data('20260320', asset_type='bond', clean_first=True, restore_redis_realtime=True)
    #
    # # 恢复 20260323 的行业数据（需要时取消注释）
    # recover_data('20260320', asset_type='industry', clean_first=True, restore_redis_realtime=True)
