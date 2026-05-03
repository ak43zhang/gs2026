# -*- coding: utf-8 -*-
"""公告原文抓取工具 — 从东方财富API获取公告全文（优化版）

优化点：
    1. requests.Session 复用TCP连接
    2. ThreadPoolExecutor 并发HTTP请求（默认8线程）
    3. 批量DB更新（每50条一批）
    4. 降低单线程延迟，通过并发控制总速率

调用方式：
    1. 集成调用：notice_collect() 中每日采集后自动调用
    2. 独立补跑：python -m gs2026.collection.risk.notice_content_fetcher --start 2026-04-01 --end 2026-04-30
"""
import re
import time
import random
import argparse
import threading
import requests
from pathlib import Path
from typing import Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, mysql_util

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# ── 数据库连接 ────────────────────────────────────────────────────────
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, pool_size=10, max_overflow=5)
mysql_tool = mysql_util.get_mysql_tool(url)

# ── 从 configs/settings.yaml 读取配置 ─────────────────────────────────
API_URL = config_util.get_config(
    'notice_content_fetcher.api_url',
    'https://np-cnotice-stock.eastmoney.com/api/content/ann')
DELAY_MIN = float(config_util.get_config('notice_content_fetcher.delay_min', 0.05))
DELAY_MAX = float(config_util.get_config('notice_content_fetcher.delay_max', 0.15))
REQUEST_TIMEOUT = int(config_util.get_config('notice_content_fetcher.request_timeout', 10))
MAX_CONSECUTIVE_FAIL = int(config_util.get_config('notice_content_fetcher.max_consecutive_fail', 10))
PAUSE_SECONDS = int(config_util.get_config('notice_content_fetcher.pause_seconds', 60))
BATCH_SIZE = int(config_util.get_config('notice_content_fetcher.batch_size', 2000))
MAX_RETRIES = int(config_util.get_config('notice_content_fetcher.max_retries', 3))
WORKERS = int(config_util.get_config('notice_content_fetcher.workers', 8))
DB_BATCH_SIZE = int(config_util.get_config('notice_content_fetcher.db_batch_size', 50))

_art_code_pattern = config_util.get_config('notice_content_fetcher.art_code_pattern', r'(AN\d+)\.html')
ART_CODE_RE = re.compile(_art_code_pattern)

# 请求头
_headers_cfg = config_util.get_config('notice_content_fetcher.headers', {})
HEADERS = {
    'User-Agent': _headers_cfg.get('User-Agent',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
    'Referer': _headers_cfg.get('Referer', 'https://data.eastmoney.com/')
}

# 线程本地 HTTP Session（每个线程独立连接池）
_thread_local = threading.local()


def _get_session() -> requests.Session:
    """获取线程本地的 Session（线程安全）"""
    if not hasattr(_thread_local, 'session'):
        s = requests.Session()
        s.headers.update(HEADERS)
        _thread_local.session = s
    return _thread_local.session


logger.info(f"NoticeContentFetcher 初始化: api={API_URL}, workers={WORKERS}, "
            f"delay={DELAY_MIN}-{DELAY_MAX}s, batch={BATCH_SIZE}, db_batch={DB_BATCH_SIZE}")


def extract_art_code(url: str) -> str:
    """从东方财富公告URL提取art_code"""
    m = ART_CODE_RE.search(url or '')
    return m.group(1) if m else ''


def fetch_single_content(art_code: str) -> Tuple[int, str]:
    """单条公告内容抓取（使用连接池Session）

    Returns:
        (status, content)
        status: 1=有内容, 2=无内容(仅PDF), 3=请求失败
    """
    for attempt in range(MAX_RETRIES):
        try:
            session = _get_session()
            resp = session.get(API_URL, params={
                'art_code': art_code,
                'client_source': 'web',
                'page_index': 1
            }, timeout=REQUEST_TIMEOUT)

            if resp.status_code != 200:
                logger.debug(f"HTTP {resp.status_code} for {art_code}, attempt {attempt+1}")
                if resp.status_code == 567:
                    # CDN/WAF 反爬拦截，长暂停
                    logger.warning(f"HTTP 567 (WAF拦截) for {art_code}, 暂停{PAUSE_SECONDS}秒后重试")
                    time.sleep(PAUSE_SECONDS)
                else:
                    time.sleep(0.5)
                continue

            data = resp.json().get('data', {})
            content = (data.get('notice_content') or '').strip()

            if content:
                return 1, content
            else:
                return 2, ''
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout for {art_code}, attempt {attempt+1}")
            time.sleep(1)
        except Exception as e:
            logger.debug(f"Error for {art_code}: {e}, attempt {attempt+1}")
            time.sleep(0.5)

    return 3, ''


def _fetch_one_record(row: Dict) -> Dict:
    """单条记录的抓取任务（线程安全）"""
    content_hash = row['内容hash']
    art_code = extract_art_code(row['网址'])

    if not art_code:
        return {'hash': content_hash, 'status': 3, 'content': ''}

    # 线程间错峰
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    status, content = fetch_single_content(art_code)
    return {'hash': content_hash, 'status': status, 'content': content}


def _batch_update_db(table_name: str, results: List[Dict]):
    """批量更新数据库"""
    if not results:
        return

    has_content = [r for r in results if r['status'] == 1 and r['content']]
    no_content = [r for r in results if r['status'] != 1 or not r['content']]

    try:
        with engine.begin() as conn:
            # 有内容的批量更新
            if has_content:
                for r in has_content:
                    conn.execute(
                        text(f"UPDATE {table_name} SET `公告原文`=:content, `content_status`=1 "
                             f"WHERE `内容hash`=:hash"),
                        {'content': r['content'], 'hash': r['hash']}
                    )
            # 无内容/失败的批量更新
            if no_content:
                for r in no_content:
                    conn.execute(
                        text(f"UPDATE {table_name} SET `content_status`=:status "
                             f"WHERE `内容hash`=:hash"),
                        {'status': r['status'], 'hash': r['hash']}
                    )
    except Exception as e:
        logger.warning(f"批量更新失败({len(results)}条): {e}")


def fetch_batch_content(table_name: str, date: str, limit: int = None):
    """批量抓取指定日期的公告原文（并发版）"""
    if limit is None:
        limit = BATCH_SIZE

    sql = (f"SELECT `内容hash`, `网址` FROM {table_name} "
           f"WHERE `公告日期`='{date}' AND (`content_status`=0 OR `content_status` IS NULL) "
           f"AND `网址` IS NOT NULL AND `网址` != '' "
           f"LIMIT {limit}")

    try:
        df = pd.read_sql(sql, engine)
    except Exception as e:
        logger.warning(f"查询待抓取记录失败: {e}")
        return

    if df.empty:
        logger.info(f"公告原文抓取: {table_name} {date} 无待处理记录")
        return

    total = len(df)
    ok_count = 0
    pdf_count = 0
    fail_count = 0
    fail_streak = 0
    batch_buffer = []  # DB批量更新缓冲
    start_time = time.time()

    logger.info(f"开始抓取公告原文: {table_name} {date}, 共{total}条, {WORKERS}线程并发")

    rows = df.to_dict('records')

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_fetch_one_record, row): i for i, row in enumerate(rows)}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
            except Exception as e:
                logger.debug(f"线程异常: {e}")
                fail_count += 1
                continue

            batch_buffer.append(result)

            if result['status'] == 1:
                ok_count += 1
                fail_streak = 0
            elif result['status'] == 2:
                pdf_count += 1
                fail_streak = 0
            else:
                fail_count += 1
                fail_streak += 1
                if fail_streak >= MAX_CONSECUTIVE_FAIL:
                    logger.warning(f"连续失败{fail_streak}次，暂停{PAUSE_SECONDS}秒")
                    time.sleep(PAUSE_SECONDS)
                    fail_streak = 0

            # 达到DB批次大小时写入
            if len(batch_buffer) >= DB_BATCH_SIZE:
                _batch_update_db(table_name, batch_buffer)
                batch_buffer = []

            # 进度日志（每200条）
            if i % 200 == 0:
                elapsed = time.time() - start_time
                speed = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / speed if speed > 0 else 0
                logger.info(f"进度: {i}/{total} ({i*100//total}%), "
                           f"速度: {speed:.1f}条/秒, ETA: {eta:.0f}秒, "
                           f"有内容:{ok_count} 仅PDF:{pdf_count} 失败:{fail_count}")

    # 刷新剩余缓冲
    if batch_buffer:
        _batch_update_db(table_name, batch_buffer)

    elapsed = time.time() - start_time
    speed = total / elapsed if elapsed > 0 else 0
    logger.info(f"公告原文抓取完成: {date} 总{total}条, "
               f"有内容{ok_count}, 仅PDF{pdf_count}, 失败{fail_count}, "
               f"耗时{elapsed:.0f}秒, 速度{speed:.1f}条/秒")


def _update_status(table_name: str, content_hash: str, status: int, content: str):
    """更新单条记录的抓取状态和内容（兼容旧接口）"""
    _batch_update_db(table_name, [{'hash': content_hash, 'status': status, 'content': content}])


def backfill_content(table_prefix: str, start_date: str, end_date: str):
    """独立补跑历史数据（自动按年份分表）"""
    start_year = int(start_date[:4])
    end_year = int(end_date[:4])

    for year in range(end_year, start_year - 1, -1):
        table_name = f'{table_prefix}{year}'
        year_start = max(start_date, f'{year}-01-01')
        year_end = min(end_date, f'{year}-12-31')

        sql = (f"SELECT DISTINCT `公告日期` FROM {table_name} "
               f"WHERE `公告日期`>='{year_start}' AND `公告日期`<='{year_end}' "
               f"AND (`content_status`=0 OR `content_status` IS NULL) "
               f"ORDER BY `公告日期` DESC")

        try:
            df = pd.read_sql(sql, engine)
        except Exception as e:
            logger.warning(f"查询{table_name}日期列表失败（表可能不存在）: {e}")
            continue

        dates = df['公告日期'].astype(str).tolist()
        if not dates:
            logger.info(f"补跑: {table_name} {year_start}~{year_end} 无待处理数据")
            continue

        logger.info(f"补跑公告原文: {table_name} {year_start}~{year_end}, 共{len(dates)}天有待处理数据")

        for date in dates:
            fetch_batch_content(table_name, date)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='公告原文抓取工具')
    parser.add_argument('--start', type=str, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--date', type=str, help='单日抓取 YYYY-MM-DD')
    parser.add_argument('--prefix', type=str, default=None, help='表名前缀，如 jhsaggg')
    parser.add_argument('--limit', type=int, default=None, help='单批限制')
    parser.add_argument('--workers', type=int, default=None, help='并发线程数')
    args = parser.parse_args()

    if args.workers:
        WORKERS = args.workers

    cfg_prefix = args.prefix or config_util.get_config('notice_content_fetcher.table_prefix', 'jhsaggg')

    if args.date:
        year = args.date[:4]
        fetch_batch_content(f'{cfg_prefix}{year}', args.date, args.limit)
    elif args.start and args.end:
        backfill_content(cfg_prefix, args.start, args.end)
    else:
        cfg_start = config_util.get_config('notice_content_fetcher.backfill_start', '')
        cfg_end = config_util.get_config('notice_content_fetcher.backfill_end', '')
        if cfg_start and cfg_end:
            logger.info(f"从 settings.yaml 读取补录配置: 前缀={cfg_prefix}, 时间={cfg_start} ~ {cfg_end}")
            backfill_content(cfg_prefix, cfg_start, cfg_end)
        else:
            print("未配置补录时间。请在 configs/settings.yaml 中设置:")
            print("  notice_content_fetcher:")
            print("    table_prefix: jhsaggg")
            print("    backfill_start: '2026-04-01'")
            print("    backfill_end: '2026-05-02'")
            print("")
            print("或使用命令行参数:")
            print("  --date 2026-05-01                         单日抓取")
            print("  --start 2026-04-01 --end 2026-04-30       批量补跑")
