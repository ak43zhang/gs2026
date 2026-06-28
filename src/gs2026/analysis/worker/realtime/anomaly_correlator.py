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
    MAX_RETRY_COUNT, _call_ai, AI_ENGINE
)
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


def _query_analyzed(engine, limit: int = 1, target_date: str = None) -> list:
    """查询已完成基础分析但未做主线归类的记录"""
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')
    sql = text("""
        SELECT id, trading_date, stock_code, stock_name, anomaly_type,
               anomaly_time, price, change_pct, continuous_zt,
               ai_analysis, related_industries, related_concepts,
               pre_forecast_messages, retry_count
        FROM stock_anomaly
        WHERE trading_date = :target_date
          AND ai_status = 'analyzed'
        ORDER BY anomaly_time ASC, created_at ASC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'target_date': target_date, 'limit': limit})
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
                   f"(已有{len(done_stocks)}只已归类) 引擎={AI_ENGINE}")
        response = _call_ai(prompt)

        if not response or response == '{}':
            _mark_correlate_failed(engine, anomaly_id, f'{AI_ENGINE}返回空响应')
            return False

        # 清理
        response = clean_ai_response(response)

        # 移除 <think>...</think> 思考过程（火山方舟API的DeepSeek模型可能输出）
        response = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()

        # 使用 repair_llm_json 修复格式问题（与火山方舟新闻分析一致）
        from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import repair_llm_json
        response = repair_llm_json(response)

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

        # 防御性类型检查：AI可能多包一层[]
        if isinstance(analysis, list):
            if len(analysis) > 0 and isinstance(analysis[0], dict):
                analysis = analysis[0]
            else:
                _mark_correlate_failed(engine, anomaly_id, '解析结果为空列表')
                return False
        if not isinstance(analysis, dict):
            _mark_correlate_failed(engine, anomaly_id, f'解析结果非字典: {type(analysis).__name__}')
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

        # 处理回溯归属：将之前遗漏的股票补充归入新主线
        retroactive_list = analysis.get('回溯归属', [])
        if retroactive_list and isinstance(retroactive_list, list):
            _process_retroactive(engine, trading_date, retroactive_list)

        # 标记完成（同时更新 ai_analysis 包含主线归属）
        _mark_done(engine, anomaly_id, mainline_names_list, ai_analysis_merged)
        logger.info(f"[Phase2] 归类完成: {stock_code} {anomaly.get('stock_name', '')} "
                   f"→ {', '.join(mainline_names_list)}")
        return True

    except Exception as e:
        logger.error(f"[Phase2] 异常: {stock_code} {e}")
        _mark_correlate_failed(engine, anomaly_id, str(e))
        return False


def _process_retroactive(engine, trading_date: str, retroactive_list: list):
    """处理回溯归属：将之前遗漏的股票补充归入主线
    
    当AI在分析当前股票时发现之前已处理的股票也应属于某主线，
    通过此函数回溯更新那些股票的主线归属。
    """
    import hashlib
    
    for item in retroactive_list:
        if not isinstance(item, dict):
            continue
        
        stock_code = item.get('stock_code', '')
        stock_name = item.get('stock_name', '')
        mainline_name = item.get('mainline_name', '')
        role = item.get('role', '跟风')
        evidence = item.get('evidence', '')
        
        if not stock_code or not mainline_name:
            continue
        
        try:
            # 1. 查找该股票是否在今日异动表中（已done）
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT id, mainline_names, ai_analysis, anomaly_time
                    FROM stock_anomaly 
                    WHERE trading_date = :date AND stock_code = :code AND ai_status = 'done'
                    LIMIT 1
                """), {'date': trading_date, 'code': stock_code})
                row = result.fetchone()
            
            if not row:
                logger.debug(f"[回溯] {stock_code} {stock_name} 未找到done记录，跳过")
                continue
            
            target_id, existing_names_raw, existing_analysis_raw, anomaly_time = row
            
            # 2. 检查是否已在该主线中（避免重复）
            existing_names = []
            if existing_names_raw:
                try:
                    existing_names = json.loads(existing_names_raw) if isinstance(existing_names_raw, str) else existing_names_raw
                except (json.JSONDecodeError, ValueError):
                    existing_names = []
            
            if mainline_name in existing_names:
                logger.debug(f"[回溯] {stock_code} {stock_name} 已在主线 {mainline_name} 中，跳过")
                continue
            
            # 3. 更新 mainline_names（追加新主线）
            new_names = [n for n in existing_names if n != '独立个股']  # 移除独立个股标记
            new_names.append(mainline_name)
            if not new_names:
                new_names = [mainline_name]
            
            # 4. 更新 ai_analysis['主线归属']（追加新条目）
            existing_analysis = {}
            if existing_analysis_raw:
                try:
                    existing_analysis = json.loads(existing_analysis_raw) if isinstance(existing_analysis_raw, str) else existing_analysis_raw
                except (json.JSONDecodeError, ValueError):
                    existing_analysis = {}
            
            mainline_attribution = existing_analysis.get('主线归属', [])
            if not isinstance(mainline_attribution, list):
                mainline_attribution = []
            # 移除"独立个股"条目
            mainline_attribution = [m for m in mainline_attribution if m.get('mainline_name') != '独立个股']
            # 追加新主线
            mainline_attribution.append({
                'type': 'existing',
                'mainline_name': mainline_name,
                'role': role,
                'evidence': f'[回溯归属] {evidence}'
            })
            existing_analysis['主线归属'] = mainline_attribution
            
            # 5. 写回数据库
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE stock_anomaly 
                    SET mainline_names = :names, ai_analysis = :analysis
                    WHERE id = :id
                """), {
                    'names': json.dumps(new_names, ensure_ascii=False),
                    'analysis': json.dumps(existing_analysis, ensure_ascii=False),
                    'id': target_id
                })
                conn.commit()
            
            # 6. 更新主线表的 related_stocks（追加成员）
            mainline_id = hashlib.md5(f"{mainline_name}_{trading_date}".encode()).hexdigest()
            stock_info = {
                'code': stock_code,
                'name': stock_name,
                'time': str(anomaly_time)[:5] if anomaly_time else '',
                'role': role
            }
            
            with engine.connect() as conn:
                existing_ml = conn.execute(text("""
                    SELECT related_stocks, stock_count FROM stock_anomaly_mainline
                    WHERE trading_date = :date AND mainline_id = :ml_id
                """), {'date': trading_date, 'ml_id': mainline_id}).fetchone()
                
                if existing_ml:
                    related = existing_ml[0]
                    if isinstance(related, str):
                        try:
                            related = json.loads(related)
                        except (json.JSONDecodeError, ValueError):
                            related = []
                    elif related is None:
                        related = []
                    
                    # 避免重复添加
                    existing_codes = [s.get('code', '') for s in related]
                    if stock_code not in existing_codes:
                        related.append(stock_info)
                        new_count = len(related)
                        
                        # 更新置信度
                        if new_count >= 5:
                            new_confidence = min(95, 85 + (new_count - 5) * 2)
                        elif new_count == 4:
                            new_confidence = 75
                        elif new_count == 3:
                            new_confidence = 60
                        elif new_count == 2:
                            new_confidence = 40
                        else:
                            new_confidence = 20
                        
                        conn.execute(text("""
                            UPDATE stock_anomaly_mainline 
                            SET related_stocks = :related, confidence = :conf, stock_count = :count
                            WHERE trading_date = :date AND mainline_id = :ml_id
                        """), {
                            'related': json.dumps(related, ensure_ascii=False),
                            'conf': new_confidence,
                            'count': new_count,
                            'date': trading_date,
                            'ml_id': mainline_id
                        })
                        conn.commit()
            
            logger.info(f"[回溯] 成功: {stock_code} {stock_name} → 归入主线 [{mainline_name}]({role})")
        
        except Exception as e:
            logger.error(f"[回溯] 处理 {stock_code} {stock_name} 异常: {e}")
            continue


def _should_stop(now: datetime, has_pending: bool) -> bool:
    """判断是否应该停止"""
    if has_pending:
        return False
    current_time = now.time()
    stop_time = dt_time(17, 0)
    return current_time >= stop_time


def main_loop(target_date: str = None):
    """Phase 2 主循环：每3秒轮询，找到 analyzed 的记录进行主线归类
    
    Args:
        target_date: 目标日期(YYYY-MM-DD)，None=当天实时模式，指定日期=历史补归类模式
    """
    global _should_exit
    
    is_realtime = target_date is None
    display_date = target_date or date.today().strftime('%Y-%m-%d')
    mode_str = "实时模式" if is_realtime else f"历史补归类模式({target_date})"
    
    logger.info(f"[Phase2] 主线归类进程启动 - {mode_str}")

    engine = _get_engine()
    redis_client = _get_redis()
    bk_dic_str, gn_dic_str = _get_bk_gn_dicts(engine)

    # 启动代理守护
    # ensure_proxy_daemon()

    consecutive_empty = 0

    while not _should_exit:
        try:
            # 实时模式用当天日期，历史模式用指定日期
            query_date = target_date if target_date else date.today().strftime('%Y-%m-%d')
            pending = _query_analyzed(engine, limit=1, target_date=query_date)
            has_pending = len(pending) > 0

            if not has_pending:
                consecutive_empty += 1
                # 停止条件：
                # - 历史模式：无数据则直接停止
                # - 实时模式：无数据且 >= 17:00
                if not is_realtime:
                    logger.info(f"[Phase2] 历史模式: {target_date} 所有记录已归类完毕")
                    break
                elif _should_stop(datetime.now(), False):
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
    # ========== 配置区 ==========
    # 指定日期则补归类历史数据，设为 None 则处理当天实时数据
    TARGET_DATE = None            # 实时模式
    # TARGET_DATE = '2026-06-26'  # 补归类模式（取消注释即可）
    # ============================
    
    # 也支持命令行参数（优先级高于上面的配置）
    import argparse
    parser = argparse.ArgumentParser(description='盘中异动主线归类')
    parser.add_argument('--date', type=str, default=TARGET_DATE,
                        help='指定归类日期(YYYY-MM-DD)，不指定则处理当天实时数据')
    args = parser.parse_args()
    
    main_loop(target_date=args.date)
