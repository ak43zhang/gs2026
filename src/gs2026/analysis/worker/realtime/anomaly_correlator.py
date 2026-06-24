"""盘中异动 主线归类进程（Phase 2）

独立运行，单进程串行，每3秒轮询 stock_anomaly 表中 ai_status='analyzed' 的记录，
使用 DeepSeek 逐条进行主线归类分析。

保证每只股票做主线归类时，前面所有股票都已有完整的基础分析结果。

用法:
    python -m gs2026.analysis.worker.realtime.anomaly_correlator
"""
import json
import signal
import time
import re
from datetime import datetime, date, time as dt_time
from typing import Optional

from loguru import logger
from sqlalchemy import text

# 从 Phase 1 共享工具函数
from gs2026.analysis.worker.realtime.anomaly_analyzer import (
    _get_engine, _get_redis, _get_bk_gn_dicts,
    _parse_json_field, _extract_reason_from_analysis,
    _get_today_all_zt, _build_full_stocks_summary,
    _get_existing_mainlines, _update_mainlines,
    MAX_RETRY_COUNT
)
from gs2026.analysis.worker.message.deepseek.proxy import ensure_proxy_daemon
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
from gs2026.analysis.worker.message.prompts import build_correlation_prompt
from gs2026.utils.string_util import clean_ai_response

# 全局变量
_should_exit = False


def _signal_handler(signum, frame):
    """信号处理：收到SIGINT/SIGTERM时标记退出"""
    global _should_exit
    logger.info(f"[Phase2] 收到退出信号({signum})，等待当前任务完成...")
    _should_exit = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _query_analyzed(engine, limit: int = 1) -> list:
    """查询已完成基础分析但未做主线归类的记录"""
    today = date.today().strftime('%Y-%m-%d')
    sql = text("""
        SELECT id, trading_date, stock_code, stock_name, anomaly_type,
               anomaly_time, price, change_pct, continuous_zt,
               ai_analysis, related_industries, related_concepts,
               pre_forecast_messages, retry_count
        FROM stock_anomaly
        WHERE trading_date = :today
          AND ai_status = 'analyzed'
        ORDER BY anomaly_time ASC, created_at ASC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'today': today, 'limit': limit})
        columns = list(result.keys())
        rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _mark_correlating(engine, anomaly_id: int) -> bool:
    """标记为主线归类中（乐观锁）"""
    sql = text("UPDATE stock_anomaly SET ai_status='correlating' WHERE id=:id AND ai_status='analyzed'")
    with engine.connect() as conn:
        result = conn.execute(sql, {'id': anomaly_id})
        conn.commit()
        return result.rowcount > 0


# 全局计数器（用于触发潜在标的挖掘）
_done_count_since_last_trigger = 0
DONE_TRIGGER_THRESHOLD = 1  # 每1个done触发，后期可调整


def _mark_done(engine, anomaly_id: int, mainline_names: list = None, ai_analysis_merged: dict = None):
    """标记为全部完成（同时写回包含主线归属的ai_analysis）"""
    names_json = json.dumps(mainline_names, ensure_ascii=False) if mainline_names else None
    analysis_json = json.dumps(ai_analysis_merged, ensure_ascii=False) if ai_analysis_merged else None

    if analysis_json:
        sql = text("""
            UPDATE stock_anomaly 
            SET ai_status = 'done',
                mainline_names = :names,
                ai_analysis = :analysis
            WHERE id = :id
        """)
        params = {'names': names_json, 'analysis': analysis_json, 'id': anomaly_id}
    else:
        sql = text("""
            UPDATE stock_anomaly 
            SET ai_status = 'done',
                mainline_names = :names
            WHERE id = :id
        """)
        params = {'names': names_json, 'id': anomaly_id}

    with engine.connect() as conn:
        conn.execute(sql, params)
        conn.commit()
    
    # 触发潜在标的挖掘
    global _done_count_since_last_trigger
    _done_count_since_last_trigger += 1
    
    if _done_count_since_last_trigger >= DONE_TRIGGER_THRESHOLD:
        _done_count_since_last_trigger = 0
        
        try:
            trading_date = date.today().strftime('%Y-%m-%d')
            # 异步触发（不阻塞主线归类）
            import threading
            from gs2026.analysis.worker.realtime.anomaly_potential import find_potential_stocks
            
            threading.Thread(
                target=find_potential_stocks,
                args=(trading_date, 'auto'),
                daemon=True
            ).start()
            logger.info(f"[潜在标的] 触发自动挖掘（每{DONE_TRIGGER_THRESHOLD}个done）")
        except Exception as e:
            logger.warning(f"[潜在标的] 触发失败: {e}")


def _mark_correlate_failed(engine, anomaly_id: int, error_msg: str):
    """归类失败，回退为analyzed状态供下次重试"""
    sql = text("UPDATE stock_anomaly SET ai_status='analyzed' WHERE id=:id")
    with engine.connect() as conn:
        conn.execute(sql, {'id': anomaly_id})
        conn.commit()
    logger.warning(f"[Phase2] 归类失败，已回退: {error_msg}")


def _get_done_stocks(engine, trading_date: str) -> list:
    """获取已完成全部流程的股票（已归类，作为上下文）"""
    sql = text("""
        SELECT id, stock_code, stock_name, anomaly_type, anomaly_time,
               change_pct, continuous_zt, ai_analysis, mainline_names
        FROM stock_anomaly
        WHERE trading_date = :date AND ai_status = 'done'
        ORDER BY anomaly_time ASC
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'date': trading_date})
        columns = list(result.keys())
        rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _build_done_summary(done_stocks: list) -> str:
    """构建已归类股票的完整摘要"""
    lines = []
    for i, s in enumerate(done_stocks, 1):
        code = s.get('stock_code', '')
        name = s.get('stock_name', '')
        atime = str(s.get('anomaly_time', ''))[:5]

        reason = _extract_reason_from_analysis(s.get('ai_analysis'))
        mainline_names = s.get('mainline_names')
        if isinstance(mainline_names, str):
            try:
                mainline_names = json.loads(mainline_names)
            except (json.JSONDecodeError, ValueError):
                mainline_names = []
        mainlines_str = ', '.join(mainline_names) if mainline_names else '独立个股'
        lines.append(f"{i}. {atime} | {code} {name} | 原因：{reason or '未提取'} | 主线：{mainlines_str}")

    return '\n'.join(lines) if lines else '（今日无已归类股票，当前为首只）'


def correlate_one(engine, anomaly: dict, bk_dic_str: str, gn_dic_str: str, redis_client) -> bool:
    """对单条记录进行主线归类"""
    anomaly_id = anomaly['id']
    stock_code = anomaly['stock_code']
    trading_date = str(anomaly['trading_date'])

    try:
        # 乐观锁
        if not _mark_correlating(engine, anomaly_id):
            return False

        # 获取已归类的股票作为上下文
        done_stocks = _get_done_stocks(engine, trading_date)
        all_done_summary = _build_done_summary(done_stocks)
        existing_mainlines = _get_existing_mainlines(engine, trading_date)

        # 从 ai_analysis 提取基础分析结果
        ai_analysis = anomaly.get('ai_analysis')
        if isinstance(ai_analysis, str):
            try:
                ai_analysis = json.loads(ai_analysis)
            except (json.JSONDecodeError, ValueError):
                ai_analysis = {}
        elif ai_analysis is None:
            ai_analysis = {}

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

        # 构造异动数据
        anomaly_data = {
            'stock_code': stock_code,
            'stock_name': anomaly.get('stock_name', ''),
            'anomaly_type': anomaly.get('anomaly_type', 'zt_hit'),
            'anomaly_time': str(anomaly.get('anomaly_time', '')),
            'price': anomaly.get('price'),
            'change_pct': anomaly.get('change_pct'),
            'continuous_zt': anomaly.get('continuous_zt', 0),
        }

        # 构造关联 Prompt
        prompt = build_correlation_prompt(
            anomaly_data, watchlist_info,
            all_done_summary, existing_mainlines,
            bk_dic_str, gn_dic_str
        )

        # 调用 AI
        logger.info(f"[Phase2] 开始归类: {stock_code} {anomaly.get('stock_name', '')} "
                   f"(已有{len(done_stocks)}只已归类)")
        response = deepseek_analysis(prompt, _headless=True)

        if not response or response == '{}':
            _mark_correlate_failed(engine, anomaly_id, 'AI返回空响应')
            return False

        # 清理
        response = clean_ai_response(response)

        # 解析 JSON
        try:
            analysis = json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    analysis = json.loads(json_match.group())
                except json.JSONDecodeError:
                    _mark_correlate_failed(engine, anomaly_id, f'JSON解析失败: {response[:100]}')
                    return False
            else:
                _mark_correlate_failed(engine, anomaly_id, f'未找到JSON: {response[:100]}')
                return False

        # 处理主线归属结果
        mainline_results = analysis.get('主线归属', [])
        mainline_names_list = []

        if mainline_results and isinstance(mainline_results, list):
            _update_mainlines(engine, anomaly_id, trading_date, anomaly_data, mainline_results)
            for ml in mainline_results:
                name = ml.get('mainline_name', '')
                if name:
                    mainline_names_list.append(name)

        if not mainline_names_list:
            mainline_names_list = ['独立个股']

        # 将主线归属写回 ai_analysis，供前端直接读取
        ai_analysis_original = anomaly.get('ai_analysis')
        if isinstance(ai_analysis_original, str):
            try:
                ai_analysis_merged = json.loads(ai_analysis_original)
            except (json.JSONDecodeError, ValueError):
                ai_analysis_merged = {}
        elif isinstance(ai_analysis_original, dict):
            ai_analysis_merged = ai_analysis_original.copy()
        else:
            ai_analysis_merged = {}
        ai_analysis_merged['主线归属'] = mainline_results

        # 标记完成（同时更新 ai_analysis 包含主线归属）
        _mark_done(engine, anomaly_id, mainline_names_list, ai_analysis_merged)
        logger.info(f"[Phase2] 归类完成: {stock_code} {anomaly.get('stock_name', '')} "
                   f"→ {', '.join(mainline_names_list)}")
        return True

    except Exception as e:
        logger.error(f"[Phase2] 异常: {stock_code} {e}")
        _mark_correlate_failed(engine, anomaly_id, str(e))
        return False


def _should_stop(now: datetime, has_pending: bool) -> bool:
    """判断是否应该停止"""
    if has_pending:
        return False
    current_time = now.time()
    stop_time = dt_time(17, 0)
    return current_time >= stop_time


def main_loop():
    """Phase 2 主循环：每3秒轮询，找到 analyzed 的记录进行主线归类"""
    global _should_exit
    logger.info("[Phase2] 主线归类进程启动...")

    engine = _get_engine()
    redis_client = _get_redis()
    bk_dic_str, gn_dic_str = _get_bk_gn_dicts(engine)

    # 启动代理守护
    ensure_proxy_daemon()

    consecutive_empty = 0

    while not _should_exit:
        try:
            pending = _query_analyzed(engine, limit=1)
            has_pending = len(pending) > 0

            if not has_pending:
                consecutive_empty += 1
                # 检查是否应该停止
                if _should_stop(datetime.now(), False):
                    logger.info("[Phase2] 无待归类数据且已过17:00，自动停止")
                    break
                # 每10次空轮询输出一次日志
                if consecutive_empty % 10 == 1:
                    logger.info(f"[Phase2] 暂无待归类数据，等待中...")
                time.sleep(3)
                continue

            consecutive_empty = 0

            # 逐条归类（串行）
            for anomaly in pending:
                if _should_exit:
                    break
                correlate_one(engine, anomaly, bk_dic_str, gn_dic_str, redis_client)

        except Exception as e:
            logger.error(f"[Phase2] 主循环异常: {e}")
            time.sleep(5)

    logger.info("[Phase2] 主线归类进程退出")


if __name__ == '__main__':
    main_loop()
