#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理 Redis 孤立缓存工具 (Redis Orphan Cache Cleaner)

功能说明:
    扫描 Redis 中的新闻缓存，删除 MySQL 中已不存在的孤立数据。
    用于保持 Redis 和 MySQL 数据一致性，释放无效缓存占用的内存。

检查范围:
    - news:detail:{hash}      - 新闻详情 Hash
    - news:timeline:{date}    - 时间线 Sorted Set
    - news:type:{date}:{type} - 类型索引 Sorted Set
    - news:top:{date}         - 评分排行 Sorted Set

使用方法:
    1. 直接运行:
       python tools/cleanup_redis_orphan.py

    2. 作为模块调用:
       from tools.cleanup_redis_orphan import main
       main()

    3. 定时任务 (crontab 示例，每天凌晨 3 点执行):
       0 3 * * * cd /path/to/gs2026 && python tools/cleanup_redis_orphan.py >> logs/cleanup.log 2>&1

依赖配置:
    自动读取 configs/settings.yaml 中的以下配置:
    - common.url              - MySQL 连接 URL
    - common.redis.host       - Redis 主机地址
    - common.redis.port       - Redis 端口

输出示例:
    ============================================================
    开始清理 Redis 孤立缓存
    ============================================================
    扫描 Redis 中的 news:detail:* keys...
    Redis 中共有 98 条 detail 缓存
    查询 MySQL 确认哪些 hash 存在...
    MySQL 中存在 80 条
    Redis 有但 MySQL 没有的数据: 18 条
    开始删除 18 条孤立缓存...
    成功删除 18 条孤立缓存
    示例 (前5条): ['abc123...', 'def456...', ...]
    ============================================================
    清理完成
    ============================================================

作者: GS2026
版本: 1.0.0
日期: 2026-04-13
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util, log_util

logger = log_util.setup_logger('cleanup_redis')

# 配置
url: str = config_util.get_config('common.url')
if not url:
    mysql_host = config_util.get_config('mysql.host', '192.168.0.101')
    mysql_port = config_util.get_config('mysql.port', 3306)
    mysql_user = config_util.get_config('mysql.user', 'root')
    mysql_password = config_util.get_config('mysql.password', '123456')
    mysql_database = config_util.get_config('mysql.database', 'gs')
    url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}?charset=utf8"

redis_host: str = config_util.get_config('common.redis.host', 'localhost')
redis_port: int = int(config_util.get_config('common.redis.port', 6379))

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def _get_redis_client():
    """获取 Redis 客户端"""
    try:
        import redis as redis_lib
        return redis_lib.Redis(
            host=redis_host,
            port=redis_port,
            db=0,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Redis 连接失败: {e}")
        return None


def get_all_detail_hashes():
    """获取 Redis 中所有 news:detail:* 的 content_hash"""
    client = _get_redis_client()
    if not client:
        return []
    
    try:
        hashes = []
        cursor = 0
        pattern = 'news:detail:*'
        
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=1000)
            for key in keys:
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str.startswith('news:detail:'):
                        hash_val = key_str[len('news:detail:'):]
                        if hash_val:
                            hashes.append(hash_val)
                except Exception as e:
                    logger.warning(f"解析 key 失败: {key}, error: {e}")
            
            if cursor == 0:
                break
        
        return hashes
    except Exception as e:
        logger.error(f"扫描 Redis 失败: {e}")
        return []


def check_mysql_exists(hashes):
    """批量检查 MySQL 中是否存在这些 hash"""
    if not hashes:
        return set()
    
    batch_size = 500
    existing = set()
    
    for i in range(0, len(hashes), batch_size):
        batch = hashes[i:i + batch_size]
        escaped = [h.replace("'", "\\'") for h in batch]
        in_clause = "','".join(escaped)
        sql = f"SELECT content_hash FROM analysis_news_detail_2026 WHERE content_hash IN ('{in_clause}')"
        
        try:
            with engine.connect() as conn:
                df = pd.read_sql(sql, conn)
                for _, row in df.iterrows():
                    existing.add(row['content_hash'])
        except Exception as e:
            logger.error(f"查询 MySQL 失败: {e}")
    
    return existing


def delete_redis_keys(hashes):
    """从 Redis 删除指定 hash 的所有相关 key"""
    client = _get_redis_client()
    if not client or not hashes:
        return 0
    
    deleted = 0
    try:
        pipe = client.pipeline()
        
        for hash_val in hashes:
            pipe.delete(f'news:detail:{hash_val}')
            deleted += 1
        
        pipe.execute()
        
        # 删除时间线、类型索引、评分排行中的成员
        all_index_keys = []
        for pattern in ['news:timeline:*', 'news:type:*', 'news:top:*']:
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=1000)
                all_index_keys.extend(keys)
                if cursor == 0:
                    break
        
        if all_index_keys and hashes:
            pipe = client.pipeline()
            for key in all_index_keys:
                for hash_val in hashes:
                    try:
                        pipe.zrem(key, hash_val)
                    except:
                        pass
            pipe.execute()
        
        return deleted
    except Exception as e:
        logger.error(f"删除 Redis key 失败: {e}")
        return deleted


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始清理 Redis 孤立缓存")
    logger.info("=" * 60)
    
    # 1. 获取 Redis 中所有 detail hash
    logger.info("扫描 Redis 中的 news:detail:* keys...")
    redis_hashes = get_all_detail_hashes()
    logger.info(f"Redis 中共有 {len(redis_hashes)} 条 detail 缓存")
    
    if not redis_hashes:
        logger.info("Redis 中没有 detail 缓存，无需清理")
        return
    
    # 2. 检查 MySQL 中存在哪些
    logger.info("查询 MySQL 确认哪些 hash 存在...")
    mysql_hashes = check_mysql_exists(redis_hashes)
    logger.info(f"MySQL 中存在 {len(mysql_hashes)} 条")
    
    # 3. 找出 Redis 有但 MySQL 没有的
    orphan_hashes = set(redis_hashes) - mysql_hashes
    logger.info(f"Redis 有但 MySQL 没有的数据: {len(orphan_hashes)} 条")
    
    if not orphan_hashes:
        logger.info("没有孤立缓存，数据一致")
        return
    
    # 4. 删除孤立的 Redis 缓存
    logger.info(f"开始删除 {len(orphan_hashes)} 条孤立缓存...")
    deleted = delete_redis_keys(list(orphan_hashes))
    logger.info(f"成功删除 {deleted} 条孤立缓存")
    
    # 5. 输出部分示例
    sample = list(orphan_hashes)[:5]
    logger.info(f"示例 (前5条): {sample}")
    
    logger.info("=" * 60)
    logger.info("清理完成")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
