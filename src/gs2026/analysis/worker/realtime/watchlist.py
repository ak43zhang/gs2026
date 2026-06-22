"""盘前 watchlist 生成

从领域分析、新闻分析、公告分析三张结果表中提取关注标的，
时间区间与智能报告一致（get_start_end），三表融合后写入 Redis。

用法:
    python -m gs2026.analysis.worker.realtime.watchlist [--date 2026-06-23]
"""
import json
import argparse
from datetime import date
from typing import Dict, List

import pandas as pd
import redis
from loguru import logger
from sqlalchemy import create_engine, text

from gs2026.utils import config_util
from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_start_end


def _get_engine():
    url = config_util.get_config('common.url')
    return create_engine(url)


def _get_redis():
    return redis.Redis(host='localhost', port=6379, decode_responses=True)


def _query_domain(engine, start: str, end: str) -> List[Dict]:
    """领域分析：利好+重大，event_time 范围"""
    sql = f"""
        SELECT key_event, sectors, concepts, stock_codes
        FROM analysis_domain_detail_2026
        WHERE news_type='利好' AND news_size='重大'
          AND event_time >= '{start} 15:00:00' AND event_time < '{end} 09:30:00'
        ORDER BY composite_score DESC
    """
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df.to_dict('records')


def _query_news(engine, start: str, end: str) -> List[Dict]:
    """新闻分析：利好+分数>=50"""
    sql = f"""
        SELECT title, sectors, concepts, leading_stocks
        FROM analysis_news_detail_2026
        WHERE news_type='利好' AND composite_score >= 50
          AND publish_time >= '{start}' AND publish_time <= '{end}'
        ORDER BY composite_score DESC
    """
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df.to_dict('records')


def _query_notice(engine, start: str, end: str) -> List[Dict]:
    """公告分析：overnight_score>=70+利好"""
    sql = f"""
        SELECT stock_code, stock_name, notice_title
        FROM analysis_notice_detail_2026
        WHERE overnight_score >= 70 AND notice_type='利好'
          AND notice_date >= '{start}' AND notice_date <= '{end}'
        ORDER BY overnight_score DESC
    """
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df.to_dict('records')


def _get_stock_name_map(engine, stock_codes: set) -> Dict[str, str]:
    """批量获取股票名称"""
    if not stock_codes:
        return {}
    codes_str = ','.join(f"'{c}'" for c in stock_codes)
    sql = f"SELECT stock_code, stock_name FROM cache_stock_industry_concept_bond WHERE stock_code IN ({codes_str})"
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return dict(zip(df['stock_code'], df['stock_name']))


def _get_stock_sectors(engine, stock_codes: set) -> Dict[str, Dict]:
    """批量获取行业/概念"""
    if not stock_codes:
        return {}
    codes_str = ','.join(f"'{c}'" for c in stock_codes)
    sql = f"SELECT stock_code, industry_names, concept_names FROM cache_stock_industry_concept_bond WHERE stock_code IN ({codes_str})"
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    result = {}
    for _, row in df.iterrows():
        industries = json.loads(row['industry_names']) if row['industry_names'] else []
        concepts = json.loads(row['concept_names']) if row['concept_names'] else []
        result[row['stock_code']] = {'industries': industries, 'concepts': concepts}
    return result


def _parse_json_field(val) -> list:
    """解析 JSON 字段（兼容 str / list / None）"""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def generate_watchlist(target_date: str = None):
    """生成次日关注清单（三表融合）"""
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')

    start_date, end_date = get_start_end(target_date)
    logger.info(f"生成 watchlist: target={target_date}, range=[{start_date}, {end_date}]")

    engine = _get_engine()
    watchlist: Dict[str, dict] = {}  # {stock_code: {...}}

    # 1. 领域分析
    domain_data = _query_domain(engine, start_date, end_date)
    logger.info(f"领域分析记录: {len(domain_data)} 条")
    for row in domain_data:
        stock_codes = _parse_json_field(row.get('stock_codes'))
        sectors = _parse_json_field(row.get('sectors'))
        concepts = _parse_json_field(row.get('concepts'))
        key_event = row.get('key_event', '')
        for code in stock_codes:
            if not code:
                continue
            if code not in watchlist:
                watchlist[code] = {'messages': [], 'sectors': sectors, 'concepts': concepts}
            watchlist[code]['messages'].append({'text': key_event, 'source': 'domain'})

    # 2. 新闻分析
    news_data = _query_news(engine, start_date, end_date)
    logger.info(f"新闻分析记录: {len(news_data)} 条")
    for row in news_data:
        stock_codes = _parse_json_field(row.get('leading_stocks'))
        sectors = _parse_json_field(row.get('sectors'))
        concepts = _parse_json_field(row.get('concepts'))
        title = row.get('title', '')
        for code in stock_codes:
            if not code:
                continue
            if code not in watchlist:
                watchlist[code] = {'messages': [], 'sectors': sectors, 'concepts': concepts}
            watchlist[code]['messages'].append({'text': title, 'source': 'news'})

    # 3. 公告分析
    notice_data = _query_notice(engine, start_date, end_date)
    logger.info(f"公告分析记录: {len(notice_data)} 条")
    for row in notice_data:
        code = row.get('stock_code', '')
        if not code:
            continue
        notice_title = row.get('notice_title', '')
        stock_name = row.get('stock_name', '')
        if code not in watchlist:
            watchlist[code] = {'messages': [], 'sectors': [], 'concepts': []}
        watchlist[code]['messages'].append({'text': notice_title, 'source': 'notice'})
        # 公告直接有 stock_name
        if stock_name:
            watchlist[code]['stock_name'] = stock_name

    # 4. 批量获取 stock_name 和行业/概念（补充没有的）
    all_codes = set(watchlist.keys())
    name_map = _get_stock_name_map(engine, all_codes)
    sector_map = _get_stock_sectors(engine, all_codes)

    for code, info in watchlist.items():
        if 'stock_name' not in info:
            info['stock_name'] = name_map.get(code, code)
        # 补充行业/概念（如果该 code 还没有行业信息）
        if not info.get('sectors') and code in sector_map:
            info['sectors'] = sector_map[code]['industries']
            info['concepts'] = sector_map[code]['concepts']
        info['direction'] = '利好'

    # 5. 写入 Redis
    redis_client = _get_redis()
    redis_key = f"anomaly:watchlist:{target_date}"
    # 清除旧数据
    redis_client.delete(redis_key)
    if watchlist:
        pipeline = redis_client.pipeline()
        for code, info in watchlist.items():
            pipeline.hset(redis_key, code, json.dumps(info, ensure_ascii=False))
        pipeline.expire(redis_key, 86400)
        pipeline.execute()

    logger.info(f"watchlist 生成完成: {len(watchlist)} 只标的写入 Redis ({redis_key})")
    return watchlist


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='生成盘中异动 watchlist')
    parser.add_argument('--date', type=str, default=None, help='目标日期 YYYY-MM-DD，默认今天')
    args = parser.parse_args()
    generate_watchlist(args.date)
