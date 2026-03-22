"""
Redis 数据存取工具模块，支持 DataFrame 的压缩存储、时间戳列表维护及历史数据读取。
使用前需调用 init_redis() 初始化全局连接。
"""
import io
import time
import zlib
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
import redis
from loguru import logger
from sqlalchemy import create_engine

from gs2026.utils import config_util, mysql_util

redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
url = config_util.get_config('common.url')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)

# 模块常量：每个表最多保留的时间戳个数
MAX_SAVE_TIMESTAMPS = 60000

# 全局 Redis 客户端（由 init_redis 初始化）
_redis_client: Optional[redis.Redis] = None

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
    decode_responses: bool = False
) -> None:
    """
    初始化全局 Redis 连接

    Args:
        host: Redis 服务器地址
        port: Redis 端口
        db: 数据库编号
        password: 访问密码
        decode_responses: 是否自动解码响应
    """
    global _redis_client
    _redis_client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=decode_responses
    )


def _get_redis_client() -> redis.Redis:
    """
    获取全局 Redis 客户端

    Returns:
        Redis 客户端实例

    Raises:
        RuntimeError: 客户端未初始化时抛出
    """
    if _redis_client is None:
        raise RuntimeError("Redis 客户端未初始化，请先调用 init_redis()")
    return _redis_client


def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


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

    Args:
        table_name: Redis 键名

    Returns:
        DataFrame 或 None
    """
    client = _get_redis_client()
    data = client.get("dict:" + table_name)

    if data is None:
        logger.warning(f"键 dict:{table_name} 不存在")
        return None

    try:
        json_str = data.decode('utf-8')
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
    name_col: str = 'name'
) -> pd.DataFrame:
    """
    使用 Redis 更新累积排行榜

    Args:
        result_df: 当前周期的 DataFrame
        rank_name: 排行榜名称
        code_col: 股票代码列名
        name_col: 股票名称列名

    Returns:
        当前排行榜 DataFrame
    """
    client = _get_redis_client()

    code_key = f'rank:{rank_name}:code'
    name_key = f'rank:{rank_name}:code_name'

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
        records.append({'code': code, 'name': name, 'count': count})

    return pd.DataFrame(records)


if __name__ == '__main__':
    start = time.time()
    init_redis(host=redis_host, port=redis_port, decode_responses=False)

    mysql2redis_generate_dict("data_industry_code_ths", 'code,name')
    mysql2redis_generate_dict("data_bond_ths",
                              '债券代码 as code,债券简称 as name,正股代码 as stock_code')

    con.close()
    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")
