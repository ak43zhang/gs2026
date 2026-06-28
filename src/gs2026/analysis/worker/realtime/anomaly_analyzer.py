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
from gs2026.analysis.worker.message.prompts import build_anomaly_prompt, build_correlation_prompt

# AI引擎配置：volcengine（火山方舟API）| deepseek（浏览器自动化）
AI_ENGINE = config_util.get_config('common.anomaly_ai_engine') or 'volcengine'

# 全局变量
_should_exit = False
MAX_RETRY_COUNT = 3  # 最大重试次数


def _call_ai(prompt: str) -> Optional[str]:
    """统一AI调用入口，根据配置切换引擎

    支持的引擎：
      - volcengine: 火山方舟HTTP API（默认，稳定快速）
      - deepseek: DeepSeek浏览器自动化（备用）
    """
    if AI_ENGINE == 'volcengine':
        from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
        return volcengine_analysis(prompt)
    else:
        from gs2026.analysis.worker.message.deepseek.proxy import ensure_proxy_daemon
        from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
        ensure_proxy_daemon()
        return deepseek_analysis(prompt, _headless=True)


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


def _watchdog_thread(engine, check_interval=60):
    """守护线程：每60秒检查一次，超过30分钟的 processing/correlating 自动重置
    
    - processing 超时 → 重置为 pending（等待Phase 1重新分析）
    - correlating 超时 → 重置为 analyzed（等待Phase 2重新归类）
    """
    TIMEOUT_MINUTES = 30
    
    while not _should_exit:
        try:
            sql = text("""
                UPDATE stock_anomaly 
                SET ai_status = CASE 
                    WHEN ai_status = 'processing' THEN 'pending'
                    WHEN ai_status = 'correlating' THEN 'analyzed'
                END,
                forecast_note = CONCAT(IFNULL(forecast_note,''), ' [超时重置]')
                WHERE ai_status IN ('processing', 'correlating')
                  AND ai_started_at < DATE_SUB(NOW(), INTERVAL :timeout MINUTE)
            """)
            with engine.connect() as conn:
                result = conn.execute(sql, {'timeout': TIMEOUT_MINUTES})
                conn.commit()
                if result.rowcount > 0:
                    logger.warning(f"[守护线程] 重置 {result.rowcount} 条超时记录(>{TIMEOUT_MINUTES}分钟)")
        except Exception as e:
            logger.error(f"[守护线程] 异常: {e}")
        
        time.sleep(check_interval)


def _query_pending(engine, limit: int = 1, target_date: str = None) -> list:
    """查询待分析的异动记录（按涨停时间排序，保证多进程全局顺序）"""
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')
    sql = text("""
        SELECT id, trading_date, stock_code, stock_name, anomaly_type, 
               anomaly_time, price, change_pct, continuous_zt,
               related_industries, related_concepts, pre_forecast_messages,
               retry_count
        FROM stock_anomaly 
        WHERE trading_date = :target_date
          AND ai_status = 'pending'
        ORDER BY anomaly_time ASC, created_at ASC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'target_date': target_date, 'limit': limit})
        columns = list(result.keys())
        rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _update_result(engine, anomaly_id: int, analysis: dict):
    """更新分析结果（Phase 1完成，标记为analyzed，等待Phase 2归类）"""
    forecast_match = analysis.get('预判吻合度', 'none')
    forecast_note = analysis.get('预判吻合说明', '')
    
    sql = text("""
        UPDATE stock_anomaly 
        SET ai_analysis = :analysis,
            ai_status = 'analyzed',
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
    """分析失败时回退到 pending 状态（不再有 failed 状态）"""
    new_retry_count = retry_count + 1
    sql = text("""
        UPDATE stock_anomaly 
        SET ai_status='pending', 
            forecast_note=:note,
            retry_count=:retry_count
        WHERE id=:id
    """)
    with engine.connect() as conn:
        conn.execute(sql, {
            'note': f'分析失败(第{new_retry_count}次)，等待重试: {error_msg[:200]}',
            'retry_count': new_retry_count,
            'id': anomaly_id
        })
        conn.commit()
    logger.info(f"[异动分析] 回退pending(第{new_retry_count}次): id={anomaly_id}")


def _mark_failed(engine, anomaly_id: int, error_msg: str):
    """分析失败回退到 pending（不再有 failed 状态）"""
    sql = text("UPDATE stock_anomaly SET ai_status='pending', forecast_note=:note WHERE id=:id")
    with engine.connect() as conn:
        conn.execute(sql, {'note': f'分析异常，回退pending: {error_msg[:200]}', 'id': anomaly_id})
        conn.commit()
    logger.info(f"[异动分析] 回退pending: id={anomaly_id}")


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


# ==================== 增量关联分析辅助函数 ====================

def _get_today_all_zt(engine, trading_date: str, exclude_id: int = None) -> list:
    """获取当天所有涨停记录（含已分析和未分析），按涨停时间排序"""
    sql = """
        SELECT id, stock_code, stock_name, anomaly_type, anomaly_time,
               change_pct, continuous_zt, ai_status, ai_analysis, mainline_names
        FROM stock_anomaly
        WHERE trading_date = :date AND anomaly_type IN ('zt_hit', 'zt_break')
        ORDER BY anomaly_time ASC
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), {'date': trading_date})
        columns = list(result.keys())
        rows = result.fetchall()

    items = []
    for row in rows:
        item = dict(zip(columns, row))
        if exclude_id and item['id'] == exclude_id:
            continue
        items.append(item)
    return items


def _extract_reason_from_analysis(ai_analysis) -> str:
    """从 ai_analysis JSON 中提取异动原因关键词"""
    try:
        if not ai_analysis:
            return ''
        if isinstance(ai_analysis, str):
            analysis = json.loads(ai_analysis)
        else:
            analysis = ai_analysis
        reason = analysis.get('异动原因', '') or analysis.get('涨停原因', '')
        return reason[:60] if reason else ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''


def _build_full_stocks_summary(all_stocks: list) -> str:
    """构建全部涨停股票完整摘要（无数量限制）"""
    lines = []
    for i, s in enumerate(all_stocks, 1):
        code = s.get('stock_code', '')
        name = s.get('stock_name', '')
        atime = str(s.get('anomaly_time', ''))[:5]  # HH:MM
        ai_status = s.get('ai_status', '')

        if ai_status == 'done':
            # 已分析：完整摘要
            reason = _extract_reason_from_analysis(s.get('ai_analysis'))
            mainline_names = s.get('mainline_names')
            if isinstance(mainline_names, str):
                try:
                    mainline_names = json.loads(mainline_names)
                except (json.JSONDecodeError, ValueError):
                    mainline_names = []
            mainlines_str = ', '.join(mainline_names) if mainline_names else '无（独立个股）'
            lines.append(f"{i}. {atime} | {code} {name} | 原因：{reason or '未提取'} | 主线：{mainlines_str}")
        else:
            # 未分析：标注
            lines.append(f"{i}. {atime} | {code} {name} | ⚠️未分析")

    return '\n'.join(lines) if lines else '（今日无涨停股票）'


def _get_existing_mainlines(engine, trading_date: str) -> str:
    """获取当天已识别的活跃主线，格式化为文本"""
    sql = """
        SELECT mainline_name, mainline_reason, catalyst, 
               related_stocks, confidence, stock_count
        FROM stock_anomaly_mainline
        WHERE trading_date = :date AND status = 'active'
        ORDER BY confidence DESC
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), {'date': trading_date})
        columns = list(result.keys())
        rows = result.fetchall()

    if not rows:
        return '暂无已识别主线，请独立分析当前股票并判断是否可与之前股票形成新主线。'

    lines = []
    for row in rows:
        item = dict(zip(columns, row))
        name = item['mainline_name']
        reason = item.get('mainline_reason', '') or ''
        catalyst = item.get('catalyst', '') or ''
        confidence = item.get('confidence', 0)
        stock_count = item.get('stock_count', 0)

        # 解析成员
        related = item.get('related_stocks')
        if isinstance(related, str):
            try:
                related = json.loads(related)
            except (json.JSONDecodeError, ValueError):
                related = []
        members = ', '.join(f"{s.get('name','')}({s.get('role','')})" for s in (related or []))

        lines.append(
            f"主线：{name} | 置信度{confidence}% | {stock_count}只 | 催化：{catalyst or '未明确'}\n"
            f"  成员：{members}\n"
            f"  逻辑：{reason}"
        )

    return '\n\n'.join(lines)


def _update_mainlines(engine, anomaly_id: int, trading_date: str, anomaly_data: dict, mainline_results: list):
    """根据AI返回的主线归属结果，更新主线表和关联关系"""
    import hashlib

    mainline_names_list = []

    for ml in mainline_results:
        ml_type = ml.get('type', 'independent')
        ml_name = ml.get('mainline_name', '独立个股')
        ml_reason = ml.get('mainline_reason', '')
        ml_catalyst = ml.get('catalyst', '')
        ml_role = ml.get('role', '跟风')
        ml_evidence = ml.get('evidence', '')
        ml_confidence_delta = ml.get('confidence_delta', 15)

        if ml_type == 'independent':
            # 独立个股不写主线表
            mainline_names_list.append('独立个股')
            continue

        # 生成主线ID
        mainline_id = hashlib.md5(f"{ml_name}_{trading_date}".encode()).hexdigest()
        mainline_names_list.append(ml_name)

        # 当前股票信息
        stock_info = {
            'code': anomaly_data.get('stock_code', ''),
            'name': anomaly_data.get('stock_name', ''),
            'time': str(anomaly_data.get('anomaly_time', ''))[:5],
            'role': ml_role
        }

        with engine.connect() as conn:
            # 检查主线是否已存在
            existing = conn.execute(text(
                "SELECT id, related_stocks, confidence, stock_count FROM stock_anomaly_mainline "
                "WHERE trading_date = :date AND mainline_id = :ml_id"
            ), {'date': trading_date, 'ml_id': mainline_id}).fetchone()

            if existing:
                # 更新已有主线
                existing_dict = dict(zip(['id', 'related_stocks', 'confidence', 'stock_count'], existing))
                related = existing_dict.get('related_stocks')
                if isinstance(related, str):
                    try:
                        related = json.loads(related)
                    except (json.JSONDecodeError, ValueError):
                        related = []
                elif related is None:
                    related = []

                # 添加当前股票（避免重复）
                existing_codes = [s.get('code', '') for s in related]
                if stock_info['code'] not in existing_codes:
                    related.append(stock_info)

                new_count = len(related)
                # 置信度规则
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
                    SET related_stocks = :related, confidence = :conf, 
                        stock_count = :count, last_updated_time = CURTIME(),
                        mainline_reason = COALESCE(NULLIF(:reason, ''), mainline_reason),
                        catalyst = COALESCE(NULLIF(:catalyst, ''), catalyst)
                    WHERE trading_date = :date AND mainline_id = :ml_id
                """), {
                    'related': json.dumps(related, ensure_ascii=False),
                    'conf': new_confidence,
                    'count': new_count,
                    'reason': ml_reason,
                    'catalyst': ml_catalyst,
                    'date': trading_date,
                    'ml_id': mainline_id
                })
            else:
                # 创建新主线
                new_confidence = 40 if ml_type == 'new' else 20
                conn.execute(text("""
                    INSERT INTO stock_anomaly_mainline 
                    (trading_date, mainline_id, mainline_name, mainline_reason, catalyst,
                     related_stocks, confidence, stock_count, first_seen_time, last_updated_time, status)
                    VALUES (:date, :ml_id, :name, :reason, :catalyst,
                            :related, :conf, 1, CURTIME(), CURTIME(), 'active')
                """), {
                    'date': trading_date,
                    'ml_id': mainline_id,
                    'name': ml_name,
                    'reason': ml_reason,
                    'catalyst': ml_catalyst,
                    'related': json.dumps([stock_info], ensure_ascii=False),
                    'conf': new_confidence
                })

            # 写入关联关系
            conn.execute(text("""
                INSERT INTO stock_anomaly_mainline_rel 
                (anomaly_id, mainline_id, role, evidence, confidence_contribution)
                VALUES (:aid, :ml_id, :role, :evidence, :delta)
            """), {
                'aid': anomaly_id,
                'ml_id': mainline_id,
                'role': ml_role,
                'evidence': ml_evidence,
                'delta': ml_confidence_delta
            })

            conn.commit()

    # 更新 stock_anomaly 的 mainline_names 字段
    if mainline_names_list:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE stock_anomaly SET mainline_names = :names WHERE id = :id
            """), {'names': json.dumps(mainline_names_list, ensure_ascii=False), 'id': anomaly_id})
            conn.commit()


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

        # 调用AI引擎分析
        logger.info(f"[异动分析] 开始分析: {stock_code} {anomaly.get('stock_name', '')} "
                   f"({anomaly.get('anomaly_type', '')} {anomaly.get('anomaly_time', '')}) "
                   f"重试次数={anomaly.get('retry_count', 0)} 引擎={AI_ENGINE}")
        
        response = _call_ai(prompt)
        
        if not response or response == '{}':
            _mark_retry(engine, anomaly_id, f'{AI_ENGINE}返回空响应', anomaly.get('retry_count', 0))
            return False

        # 清理AI返回的无用标记（[citation:N]、:ml-citation、【N†source】、```json等）
        from gs2026.utils.string_util import clean_ai_response
        response = clean_ai_response(response)

        # 移除 <think>...</think> 思考过程（火山方舟API的DeepSeek模型可能输出）
        response = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()

        # 使用 repair_llm_json 修复格式问题（与火山方舟新闻分析一致）
        from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import repair_llm_json
        response = repair_llm_json(response)

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

        # 防御性类型检查：AI可能多包一层[]
        if isinstance(analysis, list):
            if len(analysis) > 0 and isinstance(analysis[0], dict):
                analysis = analysis[0]
            else:
                _mark_retry(engine, anomaly_id, '解析结果为空列表', anomaly.get('retry_count', 0))
                return False
        if not isinstance(analysis, dict):
            _mark_retry(engine, anomaly_id, f'解析结果非字典: {type(analysis).__name__}', anomaly.get('retry_count', 0))
            return False

        # 更新结果（标记为 analyzed，等待 Phase 2 归类）
        _update_result(engine, anomaly_id, analysis)

        logger.info(f"[Phase1] 基础分析完成: {stock_code} {anomaly.get('stock_name', '')} "
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
    stop_time = dt_time(17, 0)  # 17:00
    
    return current_time >= stop_time


def main_loop(target_date: str = None):
    """主循环：每3秒轮询，无数据且17:00后自动停止
    
    Args:
        target_date: 目标日期(YYYY-MM-DD)，None=当天实时模式，指定日期=历史补分析模式
    """
    global _should_exit
    
    is_realtime = target_date is None
    display_date = target_date or date.today().strftime('%Y-%m-%d')
    mode_str = "实时模式" if is_realtime else f"历史补分析模式({target_date})"
    
    logger.info(f"[异动分析] 启动异动分析进程 - {mode_str}")
    
    # 注册信号处理（支持Ctrl+C优雅退出）
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # 确保 DeepSeek 代理运行
    # ensure_proxy_daemon()
    
    engine = _get_engine()
    redis_client = _get_redis()
    
    # 启动守护线程：检测超时的 processing/correlating 记录
    import threading
    watchdog = threading.Thread(target=_watchdog_thread, args=(engine,), daemon=True)
    watchdog.start()
    logger.info("[异动分析] 守护线程已启动（30分钟超时重置）")
    
    # 加载行业/概念字典（启动时加载一次）
    bk_dic_str, gn_dic_str = _get_bk_gn_dicts(engine)
    logger.info(f"[异动分析] 字典加载完成: 板块{len(bk_dic_str.split(','))}个, 概念{len(gn_dic_str.split(','))}个")

    consecutive_empty = 0  # 连续空轮询计数
    
    while not _should_exit:
        try:
            now = datetime.now()
            # 实时模式用当天日期，历史模式用指定日期
            query_date = target_date if target_date else date.today().strftime('%Y-%m-%d')
            pending = _query_pending(engine, limit=5, target_date=query_date)
            
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
                
                # 停止条件：
                # - 历史模式：无数据则直接停止（所有记录已分析完）
                # - 实时模式：无数据且 >= 17:00
                if not is_realtime:
                    logger.info(f"[异动分析] 历史模式: {target_date} 所有记录已分析完毕")
                    break
                elif _should_stop(now, False):
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
    # ========== 配置区 ==========
    # 指定日期则补分析历史数据，设为 None 则分析当天实时数据
    #TARGET_DATE = None            # 实时模式
    TARGET_DATE = '2026-06-26'  # 补分析模式（取消注释即可）
    # ============================
    
    # 也支持命令行参数（优先级高于上面的配置）
    import argparse
    parser = argparse.ArgumentParser(description='盘中异动AI分析')
    parser.add_argument('--date', type=str, default=TARGET_DATE,
                        help='指定分析日期(YYYY-MM-DD)，不指定则分析当天实时数据')
    args = parser.parse_args()
    
    main_loop(target_date=args.date)
