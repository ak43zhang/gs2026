"""历史数据迁移脚本：将 analysis_news2026 中的合并 JSON 拆分迁移到 analysis_news_detail_2026。

使用方法:
    python -m gs2026.analysis.worker.message.deepseek.migrate_analysis_news [--batch-size 100] [--dry-run]

说明:
    - 从 analysis_news2026 读取所有记录（22,300 条合并 JSON）
    - 逐批拆分为单条记录写入 analysis_news_detail_2026
    - 同步写入 Redis 缓存
    - 支持断点续传（通过 content_hash 唯一索引去重）
"""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, mysql_util as mu

logger = log_util.setup_logger(str(Path(__file__).absolute()))

url: str = config_util.get_config('common.url')
mysql_tool = mu.MysqlTool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def migrate(batch_size: int = 100, dry_run: bool = False, skip_redis: bool = False):
    """执行历史数据迁移

    Args:
        batch_size: 每批处理的合并记录数
        dry_run: 仅分析不写入
        skip_redis: 跳过 Redis 写入（加速迁移）
    """
    from gs2026.analysis.worker.message.deepseek.news_result_processor import (
        extract_record, save_to_mysql, save_to_redis, _ensure_redis
    )

    if not skip_redis:
        try:
            _ensure_redis()
        except Exception as e:
            logger.warning(f"Redis 初始化失败，将跳过 Redis 写入: {e}")
            skip_redis = True

    # 统计
    total_batches = 0
    total_messages = 0
    mysql_ok = 0
    redis_ok = 0
    failed_batches = 0
    failed_messages = 0
    skipped = 0

    # 获取总记录数
    with engine.connect() as conn:
        count_df = pd.read_sql("SELECT COUNT(*) as cnt FROM analysis_news2026", conn)
    total_records = int(count_df.iloc[0]['cnt']) if not count_df.empty else 0
    logger.info(f"待迁移记录数: {total_records}")

    if dry_run:
        logger.info("== DRY RUN MODE ==")

    # 分批读取
    offset = 0
    start_time = time.time()

    while offset < total_records:
        batch_sql = f"""SELECT table_name, json_value, update_time, version 
                        FROM analysis_news2026 
                        ORDER BY update_time 
                        LIMIT {batch_size} OFFSET {offset}"""
        with engine.connect() as conn:
            batch_df = pd.read_sql(batch_sql, conn)

        if batch_df.empty:
            break

        for _, row in batch_df.iterrows():
            total_batches += 1
            source_table = str(row['table_name']) if row['table_name'] else ''
            json_value = str(row['json_value']) if row['json_value'] else ''
            version = str(row['version']) if row.get('version') else ''

            if not json_value or json_value.strip() in ('', '{}'):
                failed_batches += 1
                continue

            try:
                analysis = json.loads(json_value)
            except json.JSONDecodeError:
                failed_batches += 1
                logger.warning(f"Batch {total_batches}: JSON 解析失败")
                continue

            messages = analysis.get('消息集合', [])
            if not messages:
                failed_batches += 1
                continue

            for msg in messages:
                total_messages += 1
                try:
                    record = extract_record(msg, source_table, version)
                    if not record or not record.get('content_hash'):
                        failed_messages += 1
                        continue

                    if dry_run:
                        mysql_ok += 1
                        continue

                    if save_to_mysql(record):
                        mysql_ok += 1
                    else:
                        failed_messages += 1
                        continue

                    if not skip_redis and save_to_redis(record):
                        redis_ok += 1

                except Exception as e:
                    failed_messages += 1

        offset += batch_size

        # 进度报告
        elapsed = time.time() - start_time
        pct = min(100.0, offset / total_records * 100) if total_records > 0 else 100
        logger.info(
            f"进度: {pct:.1f}% ({offset}/{total_records} batches) | "
            f"消息: {total_messages} | MySQL: {mysql_ok} | Redis: {redis_ok} | "
            f"失败: {failed_messages} | 耗时: {elapsed:.0f}s"
        )

    # 最终报告
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"迁移{'模拟' if dry_run else ''}完成")
    logger.info(f"  合并记录: {total_batches} 批 (失败: {failed_batches})")
    logger.info(f"  拆分消息: {total_messages} 条")
    logger.info(f"  MySQL 写入: {mysql_ok}")
    logger.info(f"  Redis 写入: {redis_ok}")
    logger.info(f"  失败: {failed_messages}")
    logger.info(f"  总耗时: {elapsed:.1f}s")
    logger.info("=" * 60)


def verify():
    """验证迁移结果"""
    with engine.connect() as conn:
        new_df = pd.read_sql("SELECT COUNT(*) as cnt FROM analysis_news_detail_2026", conn)
        analyzed_df = pd.read_sql("SELECT COUNT(*) as cnt FROM news_cls2026 WHERE analysis = '1'", conn)
        old_df = pd.read_sql("SELECT COUNT(*) as cnt FROM analysis_news2026", conn)

    new_count = int(new_df.iloc[0]['cnt']) if not new_df.empty else 0
    analyzed_count = int(analyzed_df.iloc[0]['cnt']) if not analyzed_df.empty else 0
    old_count = int(old_df.iloc[0]['cnt']) if not old_df.empty else 0

    logger.info("=" * 60)
    logger.info("迁移验证")
    logger.info(f"  旧表批次数 (analysis_news2026): {old_count}")
    logger.info(f"  新表记录数 (analysis_news_detail_2026): {new_count}")
    logger.info(f"  原始已分析新闻数 (news_cls2026 analysis='1'): {analyzed_count}")
    logger.info(f"  覆盖率: {new_count / analyzed_count * 100:.1f}%" if analyzed_count > 0 else "  无法计算覆盖率")
    logger.info("=" * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='历史分析数据迁移')
    parser.add_argument('--batch-size', type=int, default=100, help='每批处理记录数')
    parser.add_argument('--dry-run', action='store_true', help='仅分析不写入')
    parser.add_argument('--skip-redis', action='store_true', help='跳过Redis写入')
    parser.add_argument('--verify', action='store_true', help='验证迁移结果')
    args = parser.parse_args()

    if args.verify:
        verify()
    else:
        migrate(batch_size=args.batch_size, dry_run=args.dry_run, skip_redis=args.skip_redis)
        verify()
