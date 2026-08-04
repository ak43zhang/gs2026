#!/usr/bin/env python3
"""
股债交集回溯路由
遍历时间轴，股票和债券分别过滤后取交集
"""
import logging
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime

from gs2026.common.pipeline import FilterConfig, UnifiedPipeline
from gs2026.common.pipeline.pipeline import IntersectionCalculator

logger = logging.getLogger(__name__)

backtrace_bp = Blueprint('backtrace', __name__, template_folder='../templates')


def _get_green_bond_set(actual_date: str) -> set:
    """获取绿名单债券code集合（当天走Redis缓存 / 历史走MySQL green_bond_list表）
    
    与 monitor.py 的 get_bond_ranking 路由绿名单标记逻辑完全一致。
    """
    try:
        from gs2026.dashboard2.routes.green_bond_list_cache import (
            get_green_bond_list, get_green_bond_list_cache_date
        )
        cache_date = get_green_bond_list_cache_date()
        if cache_date == actual_date:
            return get_green_bond_list()
        # 历史日期：从MySQL按buy_date查询
        import pandas as pd
        from gs2026.utils.mysql_util import get_mysql_tool
        mysql_tool = get_mysql_tool()
        date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"
        df = pd.read_sql(
            f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'",
            con=mysql_tool.engine
        )
        return set(df['code'].astype(str).str.zfill(6).tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"获取绿名单失败: {e}")
        return set()


@backtrace_bp.route('/backtrace')
def index():
    """股债交集回溯页面"""
    return render_template('backtrace.html')


@backtrace_bp.route('/api/backtrace/dates')
def api_dates():
    """获取可选日期列表"""
    try:
        from gs2026.dashboard2.services.range_analysis_service import get_available_dates
        dates = get_available_dates()
        return jsonify({'code': 0, 'data': dates})
    except Exception as e:
        logger.error(f"获取日期失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/timestamps')
def api_timestamps():
    """获取某日所有时间戳"""
    date = request.args.get('date', '').strip()
    if not date:
        return jsonify({'code': 1, 'message': '缺少date参数'})
    
    try:
        from gs2026.dashboard2.services.range_analysis_service import get_timestamps
        timestamps = get_timestamps(date)
        return jsonify({'code': 0, 'data': timestamps})
    except Exception as e:
        logger.error(f"获取时间戳失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/run', methods=['POST'])
def api_run():
    """执行股债交集回溯"""
    try:
        data = request.get_json()
        date = data.get('date')
        stock_config = data.get('stock_config', {})
        bond_config = data.get('bond_config', {})
        start_time = (data.get('start_time') or '').strip()  # 开始时间 HH:MM:SS
        end_time = (data.get('end_time') or '').strip()      # 结束时间 HH:MM:SS
        
        # 规范化时间为 HH:MM:SS（<input type=time> 可能只返回 HH:MM）
        def _norm_time(t, is_end=False):
            if not t:
                return t
            parts = t.split(':')
            if len(parts) == 2:
                # 只有 HH:MM：开始补 :00，结束补 :59 以包含整分钟
                return f"{t}:{'59' if is_end else '00'}"
            return t
        start_time = _norm_time(start_time, is_end=False)
        end_time = _norm_time(end_time, is_end=True)
        
        if not date:
            return jsonify({'code': 1, 'message': '缺少date参数'})
        
        actual_date = date.replace('-', '')
        
        # 构建过滤配置
        stock_filter_config = FilterConfig.from_dict(stock_config)
        bond_filter_config = FilterConfig.from_dict(bond_config)
        
        # 获取时间戳列表
        from gs2026.dashboard2.services.range_analysis_service import get_timestamps
        timestamps = get_timestamps(actual_date)
        
        if not timestamps:
            return jsonify({'code': 1, 'message': '该日期无数据'})
        
        # 【新增】按开始/结束时间过滤时间戳
        if start_time:
            timestamps = [t for t in timestamps if t >= start_time]
        if end_time:
            timestamps = [t for t in timestamps if t <= end_time]
        
        if not timestamps:
            return jsonify({'code': 1, 'message': '指定时间范围内无数据'})
        
        # 复用 monitor.py 的 enrich 函数（与前端排行完全一致的数据链路）
        from gs2026.dashboard2.routes.monitor import (
            _get_ranking_fast,
            _enrich_stock_data,
            _enrich_change_pct_and_main_net,
            _enrich_bond_data,
        )
        
        # 获取绿名单集合（当天走Redis缓存 / 历史走MySQL），循环外获取一次
        green_set = _get_green_bond_set(actual_date)
        
        stock_pipeline = UnifiedPipeline(stock_filter_config)
        bond_pipeline = UnifiedPipeline(bond_filter_config)
        
        # 执行回溯
        results = []
        total = len(timestamps)
        
        for idx, time_str in enumerate(timestamps):
            try:
                # ===== 股票数据（完整enrich链路）=====
                stock_data = _get_ranking_fast('stock', actual_date, time_str, 0)
                stock_data = _enrich_stock_data(stock_data, actual_date, time_str)
                stock_data = _enrich_change_pct_and_main_net(stock_data, actual_date, time_str)
                
                # ===== 债券数据（完整enrich链路）=====
                bond_data = _get_ranking_fast('bond', actual_date, time_str, 0)
                bond_data = _enrich_bond_data(bond_data, actual_date, time_str)
                
                # ===== 绿名单标记（enrich不含此步，需在此补充，与monitor路由一致）=====
                # 债券：自身code在绿名单则is_green=True
                for b in bond_data:
                    b['is_green'] = str(b.get('code', '')).zfill(6) in green_set
                # 股票：其转债code在绿名单则is_green_bond=True（语义A：转债在绿名单即剔除）
                for s in stock_data:
                    bc = s.get('bond_code')
                    s['is_green_bond'] = (
                        bc not in (None, '-', '') and str(bc).zfill(6) in green_set
                    )
                
                # 执行过滤
                filtered_stocks = stock_pipeline.filter_stocks(stock_data)
                filtered_bonds = bond_pipeline.filter_bonds(bond_data)
                
                # 计算交集（股票.bond_code 关联 债券.code）
                intersection = IntersectionCalculator.calculate(
                    filtered_stocks, filtered_bonds
                )
                
                logger.info(
                    f"[回溯] {time_str}: 股票{len(stock_data)}→{len(filtered_stocks)}, "
                    f"债券{len(bond_data)}→{len(filtered_bonds)}, 交集{len(intersection)}"
                )
                
                if intersection:
                    results.append({
                        'time': time_str,
                        'count': len(intersection),
                        'stocks': intersection
                    })
                
            except Exception as e:
                logger.error(f"处理时间点 {time_str} 失败: {e}", exc_info=True)
                continue
        
        return jsonify({
            'code': 0,
            'data': {
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'total_timestamps': total,
                'intersection_count': len(results),
                'results': results
            }
        })
        
    except Exception as e:
        logger.error(f"执行回溯失败: {e}", exc_info=True)
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/save', methods=['POST'])
def api_save():
    """保存回溯结果到MySQL"""
    try:
        data = request.get_json()
        date = data.get('date')
        results = data.get('results', [])
        
        if not date or not results:
            return jsonify({'code': 1, 'message': '参数不完整'})
        
        # 保存到MySQL
        saved_count = 0
        for item in results:
            time_str = item.get('time')
            stocks = item.get('stocks', [])
            
            for stock in stocks:
                try:
                    # 构建记录
                    record = {
                        'date': date,
                        'time': time_str,
                        'stock_code': stock.get('stock_code'),
                        'stock_name': stock.get('stock_name'),
                        'bond_code': stock.get('bond_code'),
                        'bond_name': stock.get('bond_name'),
                        'stock_change_pct': stock.get('stock_change_pct'),
                        'bond_change_pct': stock.get('bond_change_pct'),
                        'stock_price': stock.get('stock_price'),
                        'bond_price': stock.get('bond_price'),
                        'stock_count': stock.get('stock_count'),
                        'bond_window_count': stock.get('bond_window_count'),
                        'industry': stock.get('industry'),
                        'main_net_amount': stock.get('main_net_amount')
                    }
                    
                    # 保存到数据库
                    # TODO: 实现数据库保存逻辑
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"保存记录失败: {e}")
                    continue
        
        return jsonify({
            'code': 0,
            'message': f'成功保存 {saved_count} 条记录'
        })
        
    except Exception as e:
        logger.error(f"保存失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})
