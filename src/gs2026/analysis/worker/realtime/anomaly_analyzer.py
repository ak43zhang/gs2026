"""盘中异动 AI 分析进程

独立运行，每3秒轮询 stock_anomaly 表中 ai_status='pending' 的记录，
使用 DeepSeek 逐条分析，更新分析结果。

用法:
    python -m gs2026.analysis.worker.realtime.anomaly_analyzer
"""
import json
import signal
import time
import re
from datetime import datetime, date, time as dt_time
from typing import Optional

import pandas as pd
import redis
from loguru import logger
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, string_util
from gs2026.utils.account_pool_util import DistributedAccountPool
from gs2026.analysis.worker.message.deepseek.proxy import ensure_proxy_daemon
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import (
    deepseek_analysis  # 复用领域分析的 DeepSeek 调用
)
from gs2026.analysis.worker.message.prompts import build_anomaly_prompt

# 全局变量
_should_exit = False
MAX_RETRY_COUNT = 3  # 最大重试次数


def _signal_handler(signum, frame):
    """信号处理：收到SIGINT/SIGTERM时标记退出"""
    global _should_exit
    _should_exit = True
    logger.info("[异动分析] 收到退出信号，准备停止...")


def _get_engine():
    url = config_util.get_config('common.url')
    return create_engine(url)


def _get_redis():
    return redis.Redis(host='localhost', port=6379, decode_responses=True)


def _get_bk_gn_dicts(engine) -> tuple:
    """获取板块和概念字典字符串"""
    with engine.connect() as conn:
        bk_df = pd.read_sql("SELECT name FROM data_industry_code_ths", conn)
        gn_df = pd.read_sql("SELECT name FROM ths_gn_names_rq WHERE flag='1'", conn)
    bk_dic_str = ','.join(bk_df['name'].astype(str))
    gn_dic_str = ','.join(gn_df['name'].astype(str))
    return bk_dic_str, gn_dic_str


def _query_pending(engine, limit: int = 10) -> list:
    """查询待分析的异动记录（包括pending和failed但可重试的）"""
    sql = text("""
        SELECT id, trading_date, stock_code, stock_name, anomaly_type, 
               anomaly_time, price, change_pct, continuous_zt,
               related_industries, related_concepts, pre_forecast_messages,
               retry_count
        FROM stock_anomaly 
        WHERE (ai_status = 'pending' 
               OR (ai_status = 'failed' AND IFNULL(retry_count, 0) < :max_retry))
        ORDER BY created_at ASC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'limit': limit, 'max_retry': MAX_RETRY_COUNT})
        columns = list(result.keys())
        rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _update_result(engine, anomaly_id: int, analysis: dict):
    """更新分析结果"""
    forecast_match = analysis.get('预判吻合度', 'none')
    forecast_note = analysis.get('预判吻合说明', '')
    
    sql = text("""
        UPDATE stock_anomaly 
        SET ai_analysis = :analysis,
            ai_status = 'done',
            ai_completed_at = :completed_at,
            forecast_match = :match,
            forecast_note = :note
        WHERE id = :id
    """)
    with engine.connect() as conn:
        conn.execute(sql, {
            'analysis': json.dumps(analysis, ensure_ascii=False),
            'completed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'match': forecast_match if forecast_match in ('exact', 'partial', 'none') else 'none',
            'note': forecast_note,
            'id': anomaly_id
        })
        conn.commit()


def _mark_processing(engine, anomaly_id: int):
    """标记为处理中"""
    sql = text("UPDATE stock_anomaly SET ai_status='processing', ai_started_at=:t WHERE id=:id AND ai_status='pending'")
    with engine.connect() as conn:
        result = conn.execute(sql, {'t': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'id': anomaly_id})
        conn.commit()
        return result.rowcount > 0


MAX_RETRY_COUNT = 3  # 最大重试次数


def _mark_retry(engine, anomaly_id: int, error_msg: str, retry_count: int = 0):
    """标记为待重试（失败后可重试）"""
    new_retry_count = retry_count + 1
    if new_retry_count >= MAX_RETRY_COUNT:
        # 超过最大重试次数，标记为最终失败
        sql = text("""
            UPDATE stock_anomaly 
            SET ai_status='failed', 
                forecast_note=:note,
                retry_count=:retry_count
            WHERE id=:id
        """)
        with engine.connect() as conn:
            conn.execute(sql, {
                'note': f'分析失败(重试{new_retry_count}次): {error_msg[:200]}',
                'retry_count': new_retry_count,
                'id': anomaly_id
            })
            conn.commit()
        logger.warning(f"[异动分析] 最终失败(重试{new_retry_count}次): id={anomaly_id}")
    else:
        # 重置为pending，等待下次重试
        sql = text("""
            UPDATE stock_anomaly 
            SET ai_status='pending', 
                forecast_note=:note,
                retry_count=:retry_count
            WHERE id=:id
        """)
        with engine.connect() as conn:
            conn.execute(sql, {
                'note': f'分析失败，等待重试({new_retry_count}/{MAX_RETRY_COUNT}): {error_msg[:100]}',
                'retry_count': new_retry_count,
                'id': anomaly_id
            })
            conn.commit()
        logger.info(f"[异动分析] 标记重试({new_retry_count}/{MAX_RETRY_COUNT}): id={anomaly_id}")


def _mark_failed(engine, anomaly_id: int, error_msg: str):
    """标记为失败"""
    sql = text("UPDATE stock_anomaly SET ai_status='failed', forecast_note=:note WHERE id=:id")
    with engine.connect() as conn:
        conn.execute(sql, {'note': f'分析失败: {error_msg[:200]}', 'id': anomaly_id})
        conn.commit()


def _parse_json_field(val):
    """解析JSON字段"""
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def analyze_one(engine, anomaly: dict, bk_dic_str: str, gn_dic_str: str, redis_client) -> bool:
    """分析单条异动记录"""
    anomaly_id = anomaly['id']
    stock_code = anomaly['stock_code']
    trading_date = str(anomaly['trading_date'])

    # 分布式锁
    lock_key = f"anomaly_ai_lock:{stock_code}:{trading_date}"
    if not redis_client.set(lock_key, '1', nx=True, ex=900):
        return False  # 被其他进程锁定

    try:
        # 标记为处理中（乐观锁）
        if not _mark_processing(engine, anomaly_id):
            return False  # 已被其他进程处理

        # 构造 watchlist_info
        watchlist_info = None
        pre_messages = _parse_json_field(anomaly.get('pre_forecast_messages'))
        if pre_messages:
            industries = _parse_json_field(anomaly.get('related_industries')) or []
            concepts = _parse_json_field(anomaly.get('related_concepts')) or []
            watchlist_info = {
                'messages': pre_messages,
                'sectors': industries,
                'concepts': concepts,
                'direction': '利好'
            }

        # 构造 prompt
        anomaly_data = {
            'stock_code': stock_code,
            'stock_name': anomaly.get('stock_name', ''),
            'anomaly_type': anomaly.get('anomaly_type', 'zt_hit'),
            'anomaly_time': str(anomaly.get('anomaly_time', '')),
            'price': anomaly.get('price'),
            'change_pct': anomaly.get('change_pct'),
            'continuous_zt': anomaly.get('continuous_zt', 0),
        }
        prompt = build_anomaly_prompt(anomaly_data, watchlist_info, bk_dic_str, gn_dic_str)

        # 调用 DeepSeek（浏览器自动化）
        logger.info(f"[异动分析] 开始分析: {stock_code} {anomaly.get('stock_name', '')} "
                   f"({anomaly.get('anomaly_type', '')} {anomaly.get('anomaly_time', '')}) "
                   f"重试次数={anomaly.get('retry_count', 0)}")
        
        # 使用领域分析相同的 DeepSeek 调用方式
        response = deepseek_analysis(prompt, _headless=True)
        
        if not response or response == '{}':
            _mark_retry(engine, anomaly_id, 'DeepSeek返回空响应', anomaly.get('retry_count', 0))
            return False

        # 解析 JSON 结果
        try:
            # 尝试直接解析
            analysis = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    analysis = json.loads(json_match.group())
                except json.JSONDecodeError:
                    _mark_retry(engine, anomaly_id, f'JSON解析失败: {response[:100]}', anomaly.get('retry_count', 0))
                    return False
            else:
                _mark_retry(engine, anomaly_id, f'未找到JSON: {response[:100]}', anomaly.get('retry_count', 0))
                return False

        # 更新结果
        _update_result(engine, anomaly_id, analysis)
        logger.info(f"[异动分析] 完成: {stock_code} {anomaly.get('stock_name', '')} "
                   f"forecast_match={analysis.get('预判吻合度', 'unknown')}")
        return True

    except Exception as e:
        logger.error(f"[异动分析] 异常: {stock_code} {e}")
        _mark_retry(engine, anomaly_id, str(e), anomaly.get('retry_count', 0))
        return False
    finally:
        try:
            redis_client.delete(lock_key)
        except Exception:
            pass


def _should_stop(now: datetime, has_pending: bool) -> bool:
    """
    判断是否应该停止
    
    条件：
    1. 没有待分析数据（has_pending=False）
    2. 当前时间 >= 17:00（下午5点）
    
    Args:
        now: 当前时间
        has_pending: 是否有待分析数据
    
    Returns:
        True=应该停止
    """
    if has_pending:
        return False  # 有数据继续运行
    
    # 检查是否 >= 17:00
    current_time = now.time()
    stop_time_before = dt_time(9, 30)
    stop_time = dt_time(17, 0)  # 17:00
    
    return stop_time_before >= current_time >= stop_time


def main_loop():
    """主循环：每3秒轮询，无数据且17:00后自动停止"""
    global _should_exit
    
    logger.info("[异动分析] 启动异动分析进程...")
    
    # 注册信号处理（支持Ctrl+C优雅退出）
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # 确保 DeepSeek 代理运行
    ensure_proxy_daemon()
    
    engine = _get_engine()
    redis_client = _get_redis()
    
    # 加载行业/概念字典（启动时加载一次）
    bk_dic_str, gn_dic_str = _get_bk_gn_dicts(engine)
    logger.info(f"[异动分析] 字典加载完成: 板块{len(bk_dic_str.split(','))}个, 概念{len(gn_dic_str.split(','))}个")

    consecutive_empty = 0  # 连续空轮询计数
    
    while not _should_exit:
        try:
            now = datetime.now()
            pending = _query_pending(engine, limit=5)
            
            if pending:
                consecutive_empty = 0  # 重置空计数
                logger.info(f"[异动分析] 待分析: {len(pending)} 条")
                for anomaly in pending:
                    if _should_exit:  # 检查退出信号
                        break
                    analyze_one(engine, anomaly, bk_dic_str, gn_dic_str, redis_client)
            else:
                consecutive_empty += 1
                # 每10次空轮询打印一次日志（避免日志刷屏）
                if consecutive_empty % 10 == 1:
                    logger.info(f"[异动分析] 暂无数据，连续空轮询 {consecutive_empty} 次")
                
                # 检查停止条件：无数据且 >= 17:00
                if _should_stop(now, False):
                    logger.info(f"[异动分析] 无数据且时间 {now.strftime('%H:%M')} >= 17:00，自动停止")
                    break
            
            # 检查退出信号
            if _should_exit:
                break
                
            time.sleep(3)
            
        except KeyboardInterrupt:
            logger.info("[异动分析] 收到Ctrl+C，停止...")
            break
        except Exception as e:
            logger.error(f"[异动分析] 主循环异常: {e}")
            time.sleep(10)
    
    logger.info("[异动分析] 进程已停止")


if __name__ == '__main__':
    main_loop()
