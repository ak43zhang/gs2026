"""
盘中异动潜在最强标的挖掘模块

基于已识别主线，挖掘尚未涨停但可能即将涨停的潜在标的。

用法:
    from gs2026.analysis.worker.realtime.anomaly_potential import find_potential_stocks
    potential = find_potential_stocks('2026-06-24', trigger_type='auto')
"""
import json
import threading
from datetime import datetime, date
from typing import List, Dict, Optional

from sqlalchemy import create_engine, text
from loguru import logger

from gs2026.utils import config_util
from gs2026.analysis.worker.message.prompts import build_potential_prompt
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis

# anomaly_potential 的进程名常量
_PROCESS_NAME = "anomaly_potential"


def _get_engine():
    return config_util.get_engine()


def _get_active_mainlines(engine, trading_date: str, target_time: str = None) -> List[Dict]:
    """获取当前所有活跃主线（复盘模式下只取 target_time 之前的主线）"""
    sql = """
        SELECT 
            mainline_name,
            catalyst,
            stock_count,
            first_seen_time,
            confidence
        FROM stock_anomaly_mainline
        WHERE trading_date = :date
        AND status = 'active'
    """
    
    # 复盘模式：只取 first_seen_time <= target_time 的主线
    if target_time:
        sql += " AND first_seen_time <= :time"
    
    sql += " ORDER BY confidence DESC, stock_count DESC"
    
    params = {'date': trading_date}
    if target_time:
        params['time'] = target_time
    
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = result.fetchall()
    
    mainlines = []
    for row in rows:
        mainlines.append({
            'name': row[0],
            'catalyst': row[1] or '',
            'stock_count': row[2],
            'first_seen_time': str(row[3]) if row[3] else '',
            'confidence': row[4]
        })
    
    return mainlines


def _get_zt_stocks(engine, trading_date: str, target_time: str = None) -> List[Dict]:
    """获取所有已涨停股票（复盘模式下只取 target_time 之前的）"""
    sql = """
        SELECT 
            stock_code,
            stock_name,
            anomaly_time,
            ai_analysis
        FROM stock_anomaly
        WHERE trading_date = :date
        AND ai_status = 'done'
    """
    
    # 复盘模式：只取 anomaly_time <= target_time 的股票
    if target_time:
        sql += " AND anomaly_time <= :time"
    
    sql += " ORDER BY anomaly_time"
    
    params = {'date': trading_date}
    if target_time:
        params['time'] = target_time
    
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = result.fetchall()
    
    stocks = []
    for row in rows:
        ai_analysis = row[3]
        if isinstance(ai_analysis, str):
            try:
                ai_analysis = json.loads(ai_analysis)
            except:
                ai_analysis = {}
        
        mainlines = []
        if ai_analysis and '主线归属' in ai_analysis:
            for ml in ai_analysis['主线归属']:
                mainlines.append(ml.get('mainline_name', ''))
        
        stocks.append({
            'code': row[0],
            'name': row[1],
            'time': str(row[2]) if row[2] else '',
            'mainlines': mainlines
        })
    
    return stocks


def _parse_potential_result(result_text: str) -> List[Dict]:
    """解析AI返回的潜在标的"""
    try:
        # 提取JSON
        start = result_text.find('[')
        end = result_text.rfind(']')
        if start == -1 or end == -1:
            logger.warning("[潜在标的] 未找到JSON数组")
            return []
        
        json_str = result_text[start:end+1]
        data = json.loads(json_str)
        
        if not isinstance(data, list):
            logger.warning("[潜在标的] 返回不是数组")
            return []
        
        # 标准化字段
        potential = []
        for i, item in enumerate(data[:10]):  # 最多10只
            potential.append({
                'rank': i + 1,
                'code': item.get('code', ''),
                'name': item.get('name', ''),
                'mainline_count': item.get('mainline_count', 0),
                'mainlines': item.get('mainlines', []),
                'total_score': item.get('total_score', 0),
                'suggested_entry': item.get('suggested_entry', ''),
                'risk_level': item.get('risk_level', '中'),
                'logic': item.get('logic', '')
            })
        
        return potential
    
    except Exception as e:
        logger.error(f"[潜在标的] 解析失败: {e}")
        return []


def _save_to_db(engine, trading_date: str, trigger_type: str, potential: List[Dict], replay_time: str = None):
    """保存到数据库
    
    Args:
        replay_time: 复盘时间点，None表示实时模式
    """
    trigger_time = datetime.now().strftime('%H:%M:%S')
    
    # 复盘模式：先删除该时间点的旧数据，然后清理只保留最近5个时间点
    if replay_time:
        # 删除该时间点的旧数据
        delete_sql = """
            DELETE FROM stock_anomaly_potential
            WHERE trading_date = :date AND replay_time = :replay_time
        """
        with engine.connect() as conn:
            conn.execute(text(delete_sql), {
                'date': trading_date,
                'replay_time': replay_time
            })
            conn.commit()
        logger.info(f"[潜在标的] 清除 {replay_time} 的旧数据")
        
        # 清理：只保留最近5个复盘时间点
        _cleanup_old_replay_times(engine, trading_date)
    
    sql = """
        INSERT INTO stock_anomaly_potential
        (trading_date, trigger_time, trigger_type, replay_time, stock_code, stock_name,
         rank_num, mainline_count, mainlines, total_score, suggested_entry,
         risk_level, logic)
        VALUES
        (:date, :time, :type, :replay, :code, :name, :rank, :ml_count, :mls, :score,
         :entry, :risk, :logic)
        ON DUPLICATE KEY UPDATE
            trigger_time = VALUES(trigger_time),
            trigger_type = VALUES(trigger_type),
            stock_name = VALUES(stock_name),
            rank_num = VALUES(rank_num),
            mainline_count = VALUES(mainline_count),
            mainlines = VALUES(mainlines),
            total_score = VALUES(total_score),
            suggested_entry = VALUES(suggested_entry),
            risk_level = VALUES(risk_level),
            logic = VALUES(logic)
    """
    
    with engine.connect() as conn:
        for item in potential:
            conn.execute(text(sql), {
                'date': trading_date,
                'time': trigger_time,
                'type': trigger_type,
                'replay': replay_time,  # NULL表示实时模式
                'code': item['code'],
                'name': item['name'],
                'rank': item['rank'],
                'ml_count': item['mainline_count'],
                'mls': json.dumps(item['mainlines'], ensure_ascii=False),
                'score': item['total_score'],
                'entry': item['suggested_entry'],
                'risk': item['risk_level'],
                'logic': item['logic']
            })
        conn.commit()
    
    mode_info = f"复盘 {replay_time}" if replay_time else "实时"
    logger.info(f"[潜在标的] 保存 {len(potential)} 条记录（{mode_info}），触发时间 {trigger_time}")


def _cleanup_old_replay_times(engine, trading_date: str):
    """清理：只保留最近5个复盘时间点"""
    try:
        # 获取所有复盘时间点（按时间倒序）
        sql_select = """
            SELECT DISTINCT replay_time
            FROM stock_anomaly_potential
            WHERE trading_date = :date AND replay_time IS NOT NULL
            ORDER BY replay_time DESC
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql_select), {'date': trading_date})
            times = [row[0] for row in result.fetchall()]
        
        # 如果超过5个，删除旧的
        if len(times) > 5:
            times_to_delete = times[5:]  # 保留前5个，删除后面的
            sql_delete = """
                DELETE FROM stock_anomaly_potential
                WHERE trading_date = :date AND replay_time IN :times
            """
            with engine.connect() as conn:
                conn.execute(text(sql_delete), {
                    'date': trading_date,
                    'times': tuple(times_to_delete)
                })
                conn.commit()
            logger.info(f"[潜在标的] 清理旧复盘时间点：{times_to_delete}")
    
    except Exception as e:
        logger.error(f"[潜在标的] 清理复盘时间点失败: {e}")


def find_potential_stocks(trading_date: str, trigger_type: str = 'auto', target_time: str = None) -> List[Dict]:
    """
    挖掘潜在最强标的
    
    Args:
        trading_date: 交易日期 YYYY-MM-DD
        trigger_type: 'auto' | 'manual'
        target_time: 复盘时间点 HH:MM:SS，None表示全天（实时模式）
    
    Returns:
        10只潜在标的，按相关度排序
    """
    engine = _get_engine()
    
    try:
        # 1. 获取当前所有主线（复盘模式下只取 target_time 之前的主线）
        mainlines = _get_active_mainlines(engine, trading_date, target_time)
        if not mainlines:
            logger.info(f"[潜在标的] 暂无活跃主线{'（' + target_time + '之前）' if target_time else ''}，跳过挖掘")
            return []
        
        # 2. 获取所有已涨停股票（复盘模式下只取 target_time 之前的）
        zt_stocks = _get_zt_stocks(engine, trading_date, target_time)
        
        # 3. 构建Prompt
        from gs2026.analysis.worker.message.prompts import build_potential_prompt
        prompt = build_potential_prompt(mainlines, zt_stocks)
        
        # 4. 调用AI分析
        time_info = f"（{target_time}之前）" if target_time else ""
        logger.info(f"[潜在标的] 开始挖掘{time_info}，主线数 {len(mainlines)}，已涨停 {len(zt_stocks)}")
        result = deepseek_analysis(prompt, _headless=True, process_name=_PROCESS_NAME)
        
        # 5. 解析结果
        potential = _parse_potential_result(result)
        if not potential:
            logger.warning("[潜在标的] 未解析到有效数据")
            return []
        
        # 6. 保存到数据库（实时模式也保存为复盘时间点，使用当前时间）
        current_time = datetime.now().strftime('%H:%M:%S')
        _save_to_db(engine, trading_date, trigger_type, potential, replay_time=current_time)
        
        logger.info(f"[潜在标的] 挖掘完成，返回 {len(potential)} 只")
        return potential
    
    except Exception as e:
        logger.error(f"[潜在标的] 挖掘失败: {e}")
        return []


def get_potential_by_time(trading_date: str, target_time: str = None, is_replay: bool = False) -> List[Dict]:
    """
    获取特定时间的潜在标的
    
    Args:
        trading_date: 交易日期
        target_time: 目标时间 HH:MM:SS，None表示最新
        is_replay: 是否复盘模式（使用 replay_time 字段查询）
    
    Returns:
        10只潜在标的
    """
    engine = _get_engine()
    
    try:
        if is_replay and target_time:
            # 复盘模式：精确匹配 replay_time
            sql = """
                SELECT 
                    stock_code, stock_name, rank_num, mainline_count,
                    mainlines, total_score, suggested_entry, risk_level, logic,
                    trigger_time, replay_time
                FROM stock_anomaly_potential
                WHERE trading_date = :date
                AND replay_time = :time
                ORDER BY rank_num ASC
                LIMIT 10
            """
            params = {'date': trading_date, 'time': target_time}
        elif target_time:
            # 实时模式历史查询：找 trigger_time 最接近 target_time 的记录
            sql = """
                SELECT 
                    stock_code, stock_name, rank_num, mainline_count,
                    mainlines, total_score, suggested_entry, risk_level, logic,
                    trigger_time, replay_time
                FROM stock_anomaly_potential
                WHERE trading_date = :date
                AND trigger_time <= :time
                AND replay_time IS NULL
                ORDER BY trigger_time DESC, rank_num ASC
                LIMIT 10
            """
            params = {'date': trading_date, 'time': target_time}
        else:
            # 实时模式：取最新（replay_time IS NULL）
            sql = """
                SELECT 
                    stock_code, stock_name, rank_num, mainline_count,
                    mainlines, total_score, suggested_entry, risk_level, logic,
                    trigger_time, replay_time
                FROM stock_anomaly_potential
                WHERE trading_date = :date
                AND replay_time IS NULL
                AND trigger_time = (
                    SELECT MAX(trigger_time) FROM stock_anomaly_potential
                    WHERE trading_date = :date AND replay_time IS NULL
                )
                ORDER BY rank_num ASC
            """
            params = {'date': trading_date}
        
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
        
        potential = []
        for row in rows:
            mainlines = row[4]
            if isinstance(mainlines, str):
                try:
                    mainlines = json.loads(mainlines)
                except:
                    mainlines = []
            
            potential.append({
                'stock_code': row[0],
                'stock_name': row[1],
                'rank_num': row[2],
                'mainline_count': row[3],
                'mainlines': mainlines,
                'total_score': row[5],
                'suggested_entry': row[6],
                'risk_level': row[7],
                'logic': row[8],
                'trigger_time': str(row[9]) if row[9] else '',
                'replay_time': str(row[10]) if row[10] else None
            })
        
        return potential
    
    except Exception as e:
        logger.error(f"[潜在标的] 查询失败: {e}")
        return []


def get_replay_times(trading_date: str) -> List[str]:
    """
    获取已保存的复盘时间点列表
    
    Returns:
        时间点列表（如 ['09:30:00', '10:00:00', '13:21:00']）
    """
    engine = _get_engine()
    
    try:
        sql = """
            SELECT DISTINCT replay_time
            FROM stock_anomaly_potential
            WHERE trading_date = :date
            AND replay_time IS NOT NULL
            ORDER BY replay_time ASC
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql), {'date': trading_date})
            rows = result.fetchall()
        
        times = [str(row[0]) for row in rows]
        logger.info(f"[潜在标的] 获取到 {len(times)} 个复盘时间点")
        return times
    
    except Exception as e:
        logger.error(f"[潜在标的] 查询复盘时间点失败: {e}")
        return []


def get_potential_history(trading_date: str) -> List[Dict]:
    """
    获取挖掘历史时间点
    
    Returns:
        历史触发记录列表
    """
    engine = _get_engine()
    
    try:
        sql = """
            SELECT DISTINCT trigger_time, trigger_type, COUNT(*) as stock_count
            FROM stock_anomaly_potential
            WHERE trading_date = :date
            GROUP BY trigger_time, trigger_type
            ORDER BY trigger_time DESC
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql), {'date': trading_date})
            rows = result.fetchall()
        
        history = []
        for row in rows:
            history.append({
                'time': str(row[0]),
                'type': row[1],
                'count': row[2]
            })
        
        return history
    
    except Exception as e:
        logger.error(f"[潜在标的] 查询历史失败: {e}")
        return []


def analyze_potential_with_mainlines(trading_date: str, target_time: str, mainlines: List[Dict]) -> List[Dict]:
    """
    复盘模式：使用前端传递的主线列表分析潜在标的并保存
    
    步骤：
    1. 获取 target_time 之前的已涨停股票
    2. 使用前端传递的主线列表组成提示词
    3. 调用 AI 分析潜在标的
    4. 保存结果到数据库（带 replay_time）
    5. 返回潜在标的
    
    Args:
        trading_date: 交易日期
        target_time: 复盘时间点 HH:MM:SS
        mainlines: 前端传递的主线列表 [{name, catalyst, stock_count, confidence, stocks}]
    
    Returns:
        10只潜在标的
    """
    engine = _get_engine()
    
    try:
        if not mainlines:
            logger.info(f"[复盘] 未提供主线列表")
            return []
        
        logger.info(f"[复盘] 使用前端传递的 {len(mainlines)} 条主线")
        
        # 1. 获取 target_time 之前的已涨停股票
        zt_stocks = _get_zt_stocks(engine, trading_date, target_time)
        
        if not zt_stocks:
            logger.info(f"[复盘] {target_time} 之前无已涨停数据")
            return []
        
        logger.info(f"[复盘] 获取到 {len(zt_stocks)} 只已涨停股票")
        
        # 2. 使用前端传递的主线列表构建 Prompt
        from gs2026.analysis.worker.message.prompts import build_potential_prompt
        prompt = build_potential_prompt(mainlines, zt_stocks)
        
        # 3. 调用 AI 分析
        logger.info(f"[复盘] 开始 AI 分析，主线数 {len(mainlines)}，已涨停 {len(zt_stocks)}")
        result = deepseek_analysis(prompt, _headless=True, process_name=_PROCESS_NAME)
        
        # 4. 解析结果
        potential = _parse_potential_result(result)
        if not potential:
            logger.warning("[复盘] 未解析到有效数据")
            return []
        
        # 5. 保存到数据库（带 replay_time）
        _save_to_db(engine, trading_date, 'replay', potential, replay_time=target_time)
        
        logger.info(f"[复盘] 分析完成，保存 {len(potential)} 只潜在标的")
        return potential
    
    except Exception as e:
        logger.error(f"[复盘] 分析失败: {e}")
        return []
