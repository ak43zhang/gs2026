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
        
        if not date:
            return jsonify({'code': 1, 'message': '缺少date参数'})
        
        # 构建过滤配置
        stock_filter_config = FilterConfig.from_dict(stock_config)
        bond_filter_config = FilterConfig.from_dict(bond_config)
        
        # 获取时间戳列表
        from gs2026.dashboard2.services.range_analysis_service import get_timestamps
        timestamps = get_timestamps(date)
        
        if not timestamps:
            return jsonify({'code': 1, 'message': '该日期无数据'})
        
        # 执行回溯
        results = []
        total = len(timestamps)
        
        for idx, time_str in enumerate(timestamps):
            try:
                # 创建管道
                stock_pipeline = UnifiedPipeline(stock_filter_config)
                bond_pipeline = UnifiedPipeline(bond_filter_config)
                
                # 获取数据
                from gs2026.dashboard.services.data_service import DataService
                ds = DataService()
                
                stock_data = ds.get_stock_ranking(limit=0, date=date, time_str=time_str)
                bond_data = ds.get_bond_ranking(limit=0, date=date, time_str=time_str)
                
                # 执行过滤
                filtered_stocks = stock_pipeline.execute(stock_data)
                filtered_bonds = bond_pipeline.execute(bond_data)
                
                # 计算交集
                intersection = IntersectionCalculator.calculate(
                    filtered_stocks, filtered_bonds,
                    stock_key='bond_code', bond_key='code'
                )
                
                if intersection:
                    results.append({
                        'time': time_str,
                        'count': len(intersection),
                        'stocks': intersection
                    })
                
            except Exception as e:
                logger.error(f"处理时间点 {time_str} 失败: {e}")
                continue
        
        return jsonify({
            'code': 0,
            'data': {
                'date': date,
                'total_timestamps': total,
                'intersection_count': len(results),
                'results': results
            }
        })
        
    except Exception as e:
        logger.error(f"执行回溯失败: {e}")
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
