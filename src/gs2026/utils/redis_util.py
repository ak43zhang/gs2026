"""
Redis 数据存取工具模块，支持 DataFrame 的压缩存储、时间戳列表维护及历史数据读取。
使用前需调用 init_redis() 初始化全局连接。
"""
import io
import json
import time
import zlib
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
import redis
from loguru import logger
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, mysql_util

redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
url = config_util.get_config('common.url')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)

# 模块常量：每个表最多保留的时间戳个数
MAX_SAVE_TIMESTAMPS = 60000

# 全局 Redis 客户端和连接池（由 init_redis 初始化）
_redis_client: Optional[redis.Redis] = None
_redis_pool: Optional[redis.ConnectionPool] = None

# ==================== 上攻排行配置 ====================
# Redis Key 前缀
KEY_PREFIX_ATTACK = "attack_rank"
KEY_STOCK_NAMES = "stock:code_name_map"

# 上攻判定阈值（根据 total_score 范围 0~1 设定）
THRESHOLD_TOTAL = 0.7
THRESHOLD_STRONG = 0.3
THRESHOLD_WEAK = 0.7

# 批量处理大小
BATCH_SIZE = 100

# 排行榜过期时间（秒）- 7天
RANK_EXPIRE_SECONDS = 7 * 24 * 3600


def init_redis(
    host: str = 'localhost',
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    decode_responses: bool = False,
    max_connections: int = 100  # 增加默认连接数
) -> None:
    """
    初始化全局 Redis 连接（使用连接池支持多线程）

    Args:
        host: Redis 服务器地址
        port: Redis 端口
        db: 数据库编号
        password: 访问密码
        decode_responses: 是否自动解码响应
        max_connections: 连接池最大连接数（默认100，支持多线程并发）
    """
    global _redis_client, _redis_pool

    # 如果已有连接池，先关闭
    if _redis_pool is not None:
        _redis_pool.disconnect()

    # 创建线程安全的连接池，稳定级配置
    _redis_pool = redis.ConnectionPool(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=decode_responses,
        max_connections=max_connections,
        # 超时配置（稳定级）
        socket_connect_timeout=10,     # 连接超时10秒（网络波动容忍）
        socket_timeout=30,             # 操作超时30秒（大数据写入容忍）
        # 重试配置
        retry_on_timeout=True,         # 超时自动重试
        retry_on_error=[ConnectionError, TimeoutError],  # 这些错误也重试
        # 健康检查
        health_check_interval=30,      # 健康检查间隔30秒
        # 连接保持
        socket_keepalive=True,         # TCP保持连接
        socket_keepalive_options={     # 精细的TCP保活配置
            1: 1,   # TCP_KEEPIDLE: 1秒后开始探测
            2: 3,   # TCP_KEEPINTVL: 探测间隔3秒
            3: 3,   # TCP_KEEPCNT: 探测3次无响应则断开
        },
    )

    # 使用连接池创建客户端
    _redis_client = redis.Redis(connection_pool=_redis_pool)

    # 验证连接
    try:
        _redis_client.ping()
        logger.info(f"Redis 连接池已初始化: {host}:{port}, 最大连接数: {max_connections}")
    except Exception as e:
        logger.error(f"Redis 初始化后连接验证失败: {e}")
        _redis_client = None
        _redis_pool = None
        raise
    
    logger.info(f"Redis 连接池已初始化: {host}:{port}, 最大连接数: {max_connections}")


def _get_redis_client(check_health: bool = False) -> Optional[redis.Redis]:
    """
    获取全局 Redis 客户端，带健康检查

    Args:
        check_health: 是否检查连接健康

    Returns:
        Redis 客户端或 None（未初始化或不可用）
    """
    global _redis_client, _redis_pool

    if _redis_client is None:
        logger.warning("Redis 客户端未初始化")
        return None

    if check_health:
        try:
            # 快速健康检查（1秒超时）
            _redis_client.ping()
        except Exception as e:
            logger.error(f"Redis 健康检查失败: {e}")
            return None

    return _redis_client


def close_redis() -> None:
    """关闭 Redis 连接池"""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        _redis_pool.disconnect()
        _redis_pool = None
    logger.info("Redis 连接池已关闭")


def save_dataframe_to_redis(
    df: pd.DataFrame,
    table_name: str,
    time_full: str,
    expire_seconds: int,
    use_compression: bool = False
) -> None:
    """
    将 DataFrame 存入 Redis，并维护该表的时间戳列表

    Args:
        df: 要存储的 DataFrame
        table_name: 表名
        time_full: 时间点字符串
        expire_seconds: 过期时间（秒）
        use_compression: 是否启用压缩
    """
    client = _get_redis_client()
    data_json = df.to_json(orient='records', force_ascii=False)

    key = f"{table_name}:{time_full}"
    if use_compression:
        compressed = zlib.compress(data_json.encode('utf-8'))
        client.setex(key, expire_seconds, compressed)
    else:
        client.setex(key, expire_seconds, data_json)

    pipe = client.pipeline()
    pipe.lpush(f"{table_name}:timestamps", time_full)
    pipe.ltrim(f"{table_name}:timestamps", 0, MAX_SAVE_TIMESTAMPS - 1)
    pipe.expire(f"{table_name}:timestamps", expire_seconds)
    pipe.execute()

    logger.info(f"已存储时间点 {time_full} 的数据，共 {len(df)} 条记录（压缩={use_compression}）")
    
    # 【新增】自动添加数据库索引
    try:
        from gs2026.monitor.table_index_manager import auto_add_index
        auto_add_index(table_name)
    except Exception as e:
        logger.debug(f"自动添加索引失败（非关键）: {e}")


def save_dataframe_to_redis_dict(df: pd.DataFrame, table_name: str) -> None:
    """
    将 DataFrame 以 JSON 格式永久保存到 Redis

    Args:
        df: 要存储的 DataFrame
        table_name: Redis 键名
    """
    client = _get_redis_client()
    data_json = df.to_json(orient='records', force_ascii=False)
    client.set(table_name, data_json)

    logger.info(f"已存储表 {table_name} 的数据，共 {len(df)} 条记录")


def load_dataframe_by_key(key: str, use_compression: bool = False) -> Optional[pd.DataFrame]:
    """
    根据完整的 Redis 键名获取数据

    Args:
        key: Redis 键名
        use_compression: 是否使用了压缩

    Returns:
        DataFrame 或 None
    """
    client = _get_redis_client()
    data = client.get(key)
    if data is None:
        logger.warning(f"键 {key} 不存在或已过期")
        return None

    if use_compression:
        if isinstance(data, str):
            logger.error("错误：连接设置为 decode_responses=True，无法处理压缩数据")
            return None
        try:
            json_str = zlib.decompress(data).decode('utf-8')
        except zlib.error:
            logger.error("解压失败，请检查 use_compression 参数")
            return None
    else:
        json_str = data.decode('utf-8') if isinstance(data, bytes) else data

    try:
        return pd.read_json(io.StringIO(json_str), orient='records')
    except Exception as e:
        logger.error(f"解析 JSON 失败: {e}")
        return None


def load_latest_dataframe(table_name: str, use_compression: bool = False) -> Optional[pd.DataFrame]:
    """
    获取最新时间点的 DataFrame

    Args:
        table_name: 表名
        use_compression: 是否使用了压缩

    Returns:
        DataFrame 或 None
    """
    return load_dataframe_by_offset(table_name, 0, use_compression)


def get_earliest_timestamp(table_name: str) -> Optional[str]:
    """
    获取表中最早的时间戳
    
    Args:
        table_name: 表名如 monitor_gp_sssj_20260427
        
    Returns:
        最早时间戳如 "09:27:42"，无数据返回None
    """
    try:
        client = _get_redis_client()
        # 获取所有时间戳key
        pattern = f"{table_name}:*"
        keys = client.keys(pattern)
        if not keys:
            return None
        
        # 提取时间戳并排序
        times = []
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            # 格式: monitor_gp_sssj_20260427:09:30:00
            if ':' in key_str:
                time_part = key_str.split(':', 1)[1]
                if time_part:
                    times.append(time_part)
        
        if not times:
            return None
            
        # 返回最早时间
        times.sort()
        return times[0]
    except Exception as e:
        logger.error(f"获取最早时间戳失败: {e}")
        return None


def load_dataframe_by_offset(
    table_name: str,
    offset: int = 0,
    use_compression: bool = False
) -> Optional[pd.DataFrame]:
    """
    按偏移量获取历史数据

    Args:
        table_name: 表名
        offset: 0 表示最新
        use_compression: 是否使用了压缩

    Returns:
        DataFrame 或 None
    """
    client = _get_redis_client()
    ts_data = client.lindex(f"{table_name}:timestamps", offset)
    if ts_data is None:
        logger.warning(f"偏移量 {offset} 无数据")
        return None

    timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    key = f"{table_name}:{timestamp}"
    return load_dataframe_by_key(key, use_compression)


def load_last_n_dataframes(
    table_name: str,
    n: int = 10,
    use_compression: bool = False
) -> Optional[pd.DataFrame]:
    """
    获取最近 n 条历史数据

    Args:
        table_name: 表名
        n: 获取的条数
        use_compression: 是否使用了压缩

    Returns:
        合并后的 DataFrame 或 None
    """
    client = _get_redis_client()
    list_key = f"{table_name}:timestamps"
    total = client.llen(list_key)

    if total == 0:
        logger.warning(f"表 {table_name} 无历史数据")
        return None

    n = min(n, total)
    dfs = []
    for offset in range(n):
        ts_data = client.lindex(list_key, offset)
        if ts_data is None:
            continue
        timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
        key = f"{table_name}:{timestamp}"
        df = load_dataframe_by_key(key, use_compression)
        if df is not None:
            df['snapshot_time'] = timestamp
            dfs.append(df)

    if not dfs:
        logger.warning("未获取到任何有效数据")
        return None

    result = pd.concat(dfs, ignore_index=True)
    logger.info(f"获取到 {len(dfs)} 个时间点的数据，合并后共 {len(result)} 条记录")
    return result


def update_ranking(stock_codes: List[str], base_rank_key: str, date_str: str) -> None:
    """
    为当日排行榜中的每只股票增加1次计数

    Args:
        stock_codes: 股票代码列表
        base_rank_key: 排行榜基础键名
        date_str: 日期字符串
    """
    client = _get_redis_client()
    if not stock_codes:
        return

    redis_key = f"rank:{base_rank_key}:{date_str}"
    for code in stock_codes:
        client.zincrby(redis_key, 1, code)
    client.expire(redis_key, 7 * 24 * 3600)


def get_top_ranking(base_rank_key: str, date_str: str, top_n: int = 10) -> List[Tuple[str, float]]:
    """
    获取当日排行榜累计次数前 N 的股票

    Args:
        base_rank_key: 排行榜基础键名
        date_str: 日期字符串
        top_n: 返回前 N 名

    Returns:
        列表，每项为 (stock_code, count)
    """
    client = _get_redis_client()
    redis_key = f"rank:{base_rank_key}:{date_str}"
    return client.zrevrange(redis_key, 0, top_n - 1, withscores=True)


def mysql2redis_generate_dict(table_name: str, columns: str) -> None:
    """
    将 MySQL 表数据转换为字典并存储到 Redis

    Args:
        table_name: MySQL 表名
        columns: 列名
    """
    sql = f"SELECT {columns} FROM {table_name}"
    df = pd.read_sql(sql, con=con)
    save_dataframe_to_redis_dict(df, "dict:" + table_name)


def get_dict(table_name: str) -> Optional[pd.DataFrame]:
    """
    从 Redis 中加载指定键的 DataFrame 数据

    增强容错：Redis 连接超时或异常时返回 None，不抛出异常

    Args:
        table_name: Redis 键名

    Returns:
        DataFrame 或 None（键不存在或 Redis 异常）
    """
    # 获取 Redis 客户端，带健康检查
    client = _get_redis_client(check_health=True)
    if client is None:
        logger.warning(f"Redis 不可用，无法加载字典 {table_name}")
        return None

    try:
        data = client.get("dict:" + table_name)
    except (redis.exceptions.TimeoutError, redis.exceptions.ConnectionError) as e:
        logger.error(f"Redis 连接超时/错误，无法加载字典 {table_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Redis 读取异常，无法加载字典 {table_name}: {e}")
        return None

    if data is None:
        logger.warning(f"键 dict:{table_name} 不存在")
        return None

    try:
        json_str = data.decode('utf-8') if isinstance(data, bytes) else data
        df = pd.read_json(io.StringIO(json_str), orient='records')
        logger.info(f"已从键 {table_name} 加载数据，共 {len(df)} 条记录")
        return df
    except Exception as e:
        logger.error(f"解析 JSON 数据失败: {e}")
        return None


def data_clear_redis(date_str: str) -> None:
    """
    清理指定日期的 Redis 数据

    Args:
        date_str: 日期字符串
    """
    prefix_bases = [
        f'rank:bond_count_rank_{date_str}:code',
        f'monitor_combine_{date_str}',
        f'monitor_gp_apqd_{date_str}',
        f'monitor_gp_top30_{date_str}',
        f'monitor_zq_apqd_{date_str}',
        f'monitor_zq_top30_{date_str}',
        f'monitor_hy_apqd_{date_str}',
        f'monitor_hy_top30_{date_str}',
    ]
    for base in prefix_bases:
        delete_redis_keys_by_prefix(base + '*', batch_size=1000, use_unlink=True)


def delete_redis_keys_by_prefix(
    prefix: str,
    batch_size: int = 1000,
    use_unlink: bool = True
) -> int:
    """
    批量删除 Redis 中匹配指定前缀的所有键

    Args:
        prefix: 键的前缀匹配模式
        batch_size: 每批删除的键数量
        use_unlink: 是否使用 UNLINK 命令

    Returns:
        实际删除的键总数
    """
    client = _get_redis_client()

    if use_unlink:
        try:
            client.unlink('__test_unlink_key__')
        except redis.exceptions.ResponseError:
            use_unlink = False
            logger.warning("当前 Redis 版本不支持 UNLINK，将使用 DELETE 命令")

    deleted_count = 0
    batch_keys = []

    for key in client.scan_iter(match=prefix, count=batch_size):
        batch_keys.append(key)
        if len(batch_keys) >= batch_size:
            if use_unlink:
                client.unlink(*batch_keys)
            else:
                client.delete(*batch_keys)
            deleted_count += len(batch_keys)
            logger.info(f"已删除 {len(batch_keys)} 个键")
            batch_keys.clear()

    if batch_keys:
        if use_unlink:
            client.unlink(*batch_keys)
        else:
            client.delete(*batch_keys)
        deleted_count += len(batch_keys)
        logger.info(f"已删除 {len(batch_keys)} 个键")

    logger.info(f"总计删除 {deleted_count} 个键")
    return deleted_count


def _decode_if_bytes(value: Any) -> Any:
    """将 bytes 解码为字符串"""
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return value


def update_rank_redis(
    result_df: pd.DataFrame,
    rank_name: str = 'default',
    code_col: str = 'code',
    name_col: str = 'name',
    date_str: str = None
) -> pd.DataFrame:
    """
    使用 Redis 更新累积排行榜

    Args:
        result_df: 当前周期的 DataFrame
        rank_name: 排行榜名称
        code_col: 股票代码列名
        name_col: 股票名称列名
        date_str: 日期字符串（YYYYMMDD），用于区分不同日期的排行榜

    Returns:
        当前排行榜 DataFrame
    """
    client = _get_redis_client()

    # key 增加日期后缀
    date_suffix = f"_{date_str}" if date_str else ""
    code_key = f'rank:{rank_name}:code{date_suffix}'
    name_key = f'rank:{rank_name}:code_name{date_suffix}'

    code_counts = result_df[code_col].value_counts()

    pipe = client.pipeline()
    for code, count in code_counts.items():
        pipe.zincrby(code_key, count, code)
        name = result_df.loc[result_df[code_col] == code, name_col].iloc[0]
        pipe.hset(name_key, code, name)
    pipe.execute()

    rank_data = client.zrevrange(code_key, 0, -1, withscores=True)

    records = []
    for code, score in rank_data:
        count = int(score)
        name = client.hget(name_key, code)
        name = _decode_if_bytes(name) or ''
        code = _decode_if_bytes(code)
        records.append({'code': code, 'name': name, 'count': count, 'date': date_str})

    return pd.DataFrame(records)


def get_rank_by_time(
    rank_name: str = 'stock',
    date_str: str = None,
    before_time: str = None,
    code_col: str = 'code',
    name_col: str = 'name',
    top_n: int = 30,
    use_compression: bool = False
) -> pd.DataFrame:
    """
    获取截止到指定时间的上攻排行榜
    
    从 Redis 中读取 top30 表的所有时间点数据，
    筛选 <= before_time 的时间点，统计 code 出现次数生成排行榜。
    
    Args:
        rank_name: 排行榜名称，用于确定表名前缀
                   'stock' -> monitor_gp_top30_{date}
                   'bond'  -> monitor_zq_top30_{date}
                   'industry' -> monitor_hy_top30_{date}
        date_str: 日期字符串 YYYYMMDD，默认今天
        before_time: 截止时间 HH:MM:SS，如 '10:30:00'
                     None 表示不限制（等同于全天数据）
        code_col: 代码列名
        name_col: 名称列名
        top_n: 返回前N名
        use_compression: Redis 数据是否压缩
    
    Returns:
        排行榜 DataFrame，列: code, name, count, date
        按 count 降序排列
    
    Example:
        # 获取 2026-03-24 上午 10:30 前的股票上攻排行 TOP15
        df = get_rank_by_time('stock', '20260324', '10:30:00', top_n=15)
    """
    if date_str is None:
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
    
    # 根据 rank_name 确定 top30 表名
    table_prefix_map = {
        'stock': 'monitor_gp_top30',
        'bond': 'monitor_zq_top30',
        'industry': 'monitor_hy_top30',
    }
    prefix = table_prefix_map.get(rank_name)
    if prefix is None:
        logger.error(f"不支持的 rank_name: {rank_name}")
        return pd.DataFrame(columns=['code', 'name', 'count', 'date'])
    
    table_name = f"{prefix}_{date_str}"
    client = _get_redis_client()
    
    # 1. 获取所有时间戳
    ts_key = f"{table_name}:timestamps"
    all_ts_raw = client.lrange(ts_key, 0, -1)
    
    if not all_ts_raw:
        logger.info(f"表 {table_name} 无时间戳数据")
        return pd.DataFrame(columns=['code', 'name', 'count', 'date'])
    
    # 解码并筛选 <= before_time 的时间点
    all_ts = [_decode_if_bytes(t) for t in all_ts_raw]
    if before_time:
        all_ts = [t for t in all_ts if t <= before_time]
    
    if not all_ts:
        logger.info(f"表 {table_name} 在 {before_time} 之前无数据")
        return pd.DataFrame(columns=['code', 'name', 'count', 'date'])
    
    logger.info(f"统计 {table_name} 截止 {before_time or '全天'}: {len(all_ts)} 个时间点")
    
    # 2. 遍历每个时间点，统计 code 出现次数
    code_counts = {}   # code -> 累计次数
    code_names = {}    # code -> name
    
    for ts in all_ts:
        key = f"{table_name}:{ts}"
        df = load_dataframe_by_key(key, use_compression=use_compression)
        
        if df is None or df.empty:
            continue
        
        if code_col not in df.columns:
            continue
        
        for code in df[code_col].astype(str):
            code_counts[code] = code_counts.get(code, 0) + 1
        
        # 记录名称（取最新的）
        if name_col in df.columns:
            for _, row in df[[code_col, name_col]].drop_duplicates().iterrows():
                code_names[str(row[code_col])] = str(row[name_col])
    
    if not code_counts:
        return pd.DataFrame(columns=['code', 'name', 'count', 'date'])
    
    # 3. 排序取 TOP N
    sorted_items = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    
    records = []
    for code, count in sorted_items:
        records.append({
            'code': code,
            'name': code_names.get(code, ''),
            'count': count,
            'date': date_str
        })
    
    logger.info(f"{rank_name} 截止 {before_time or '全天'} 排行: {len(records)} 条")
    return pd.DataFrame(records)


def _save_rank_to_mysql(rank_df: pd.DataFrame, rank_name: str, date_str: str) -> None:
    """
    将排行榜数据保存到 MySQL（供 monitor 模块调用）
    
    Args:
        rank_df: 排行榜 DataFrame（包含 code, name, count, date 列）
        rank_name: 排行榜名称（stock/bond/industry）
        date_str: 日期字符串 YYYYMMDD
    """
    try:
        table_name = f"rank_{rank_name}"
        # 先删除该日期的旧数据，避免重复
        delete_sql = text(f"DELETE FROM {table_name} WHERE date = '{date_str}'")
        con.execute(delete_sql)
        con.commit()
        # 插入新数据
        rank_df.to_sql(table_name, con=engine, if_exists='append', index=False)
        logger.info(f"已保存 {rank_name} 排行榜到 MySQL 表 {table_name}，日期: {date_str}，共 {len(rank_df)} 条")
    except Exception as e:
        logger.error(f"保存排行榜到 MySQL 失败: {e}")


def init_stock_industry_mapping_to_redis() -> bool:
    """
    初始化股票-行业映射到 Redis
    从 MySQL data_industry_code_component_ths 表读取
    """
    try:
        sql = """
            SELECT 
                stock_code,
                short_name as stock_name,
                code as industry_code,
                name as industry_name
            FROM data_industry_code_component_ths
            WHERE stock_code IS NOT NULL 
              AND stock_code != ''
        """

        mapping_df = pd.read_sql(sql, con=con)

        if mapping_df.empty:
            logger.warning("股票-行业映射为空")
            return False

        # 保存到 Redis
        pipe = _redis_client.pipeline()
        for _, row in mapping_df.iterrows():
            mapping_data = {
                'stock_code': str(row['stock_code']).zfill(6),
                'stock_name': row['stock_name'],
                'industry_code': row['industry_code'],
                'industry_name': row['industry_name']
            }
            pipe.hset(
                'stock_industry_mapping',
                str(row['stock_code']).zfill(6),
                json.dumps(mapping_data, ensure_ascii=False)
            )
        pipe.execute()

        logger.info(f"股票-行业映射初始化完成，共 {len(mapping_df)} 条")
        return True

    except Exception as e:
        logger.error(f"初始化股票-行业映射失败: {e}")
        return False



def init_industry_stock_count_to_redis() -> bool:
    """
    预计算各行业股票数量，存入 Redis
    从 data_industry_code_component_ths 表统计
    建议每天开盘前执行一次
    """
    try:
        sql = """
            SELECT 
                code as industry_code,
                name as industry_name,
                COUNT(*) as total_stocks
            FROM data_industry_code_component_ths
            WHERE code IS NOT NULL AND code != ''
            GROUP BY code, name
        """

        df = pd.read_sql(sql, con)

        if df.empty:
            logger.warning("行业成分股统计为空")
            return False

        # 保存到 Redis
        client = _get_redis_client()
        pipe = client.pipeline()

        for _, row in df.iterrows():
            data = {
                'industry_code': row['industry_code'],
                'industry_name': row['industry_name'],
                'total_stocks': int(row['total_stocks'])
            }
            pipe.hset(
                'industry_stock_count',
                str(row['industry_code']),
                json.dumps(data, ensure_ascii=False)
            )

        pipe.execute()

        logger.info(f"行业成分股数量预计算完成，共 {len(df)} 个行业")
        return True

    except Exception as e:
        logger.error(f"预计算行业成分股数量失败: {e}")
        return False


# ==================== 涨停行概选股Redis查询函数 ====================

def get_zt_stocks_from_redis(date: str, table_type: str = 'stock') -> Optional[List[str]]:
    """
    从Redis获取涨停股票代码列表

    Args:
        date: 日期 YYYYMMDD
        table_type: 'stock' 或 'bond'

    Returns:
        涨停股票代码列表 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"

    # 1. 获取最新时间戳
    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if not ts_data:
        logger.warning(f"Redis无数据: {table_name}")
        return None

    timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data

    # 2. 获取该时间点的数据
    key = f"{table_name}:{timestamp}"
    df = load_dataframe_by_key(key)

    if df is None or df.empty:
        return None

    # 3. 筛选涨停股票
    if 'is_zt' not in df.columns:
        logger.warning(f"数据缺少is_zt字段: {table_name}")
        return None

    # 确保stock_code是字符串并补零到6位
    df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
    zt_stocks = df[df['is_zt'] == 1]['stock_code'].tolist()
    logger.info(f"从Redis获取涨停股票: {len(zt_stocks)} 只")
    return zt_stocks


def get_realtime_prices_from_redis(date: str, stock_codes: List[str],
                                   table_type: str = 'stock') -> Optional[Dict[str, dict]]:
    """
    从Redis获取实时价格

    Args:
        date: 日期 YYYYMMDD
        stock_codes: 股票代码列表
        table_type: 'stock' 或 'bond'

    Returns:
        {stock_code: {'price': x, 'change_pct': y, ...}} 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"

    # 获取最新时间戳
    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if not ts_data:
        return None

    timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data

    # 获取数据
    key = f"{table_name}:{timestamp}"
    df = load_dataframe_by_key(key)

    if df is None or df.empty:
        return None

    # 确保stock_code是字符串并补零到6位
    df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)

    # 筛选指定股票
    df_filtered = df[df['stock_code'].isin(stock_codes)]

    # 转换为字典
    result = {}
    for _, row in df_filtered.iterrows():
        code = row['stock_code']
        result[code] = {
            'price': row.get('price', 0),
            'change_pct': float(row.get('change_pct', 0)) if pd.notna(row.get('change_pct')) else 0,
            'short_name': row.get('short_name', row.get('name', '')),
        }

    return result


def get_max_time_from_redis(date: str, table_type: str = 'stock') -> Optional[str]:
    """
    从Redis获取最新时间戳

    Args:
        date: 日期 YYYYMMDD
        table_type: 'stock' 或 'bond'

    Returns:
        时间字符串 HH:MM:SS 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"

    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if ts_data:
        return ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    return None


if __name__ == '__main__':
    start = time.time()
    init_redis(host=redis_host, port=redis_port, decode_responses=False)

    mysql2redis_generate_dict("data_industry_code_ths", 'code,name')
    mysql2redis_generate_dict("data_bond_ths",
                              '债券代码 as code,债券简称 as name,正股代码 as stock_code')

    init_stock_industry_mapping_to_redis()
    init_industry_stock_count_to_redis()

    con.close()
    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")
