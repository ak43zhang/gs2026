#!/usr/bin/env python3
"""
区间测算路由
分析区间内行业（板块）的涨幅最强/最弱变化，判断大盘涨跌由哪些板块带动。
数据源: monitor_hy_top30_{date} 宽表（一表多用）。
"""
import logging
from flask import Blueprint, render_template, request, jsonify

from gs2026.dashboard2.services import range_analysis_service as svc

logger = logging.getLogger(__name__)

range_analysis_bp = Blueprint('range_analysis', __name__,
                              template_folder='../templates')


@range_analysis_bp.route('/range-analysis')
def index():
    """区间测算页面"""
    return render_template('range_analysis.html')


@range_analysis_bp.route('/api/range-analysis/dates')
def api_dates():
    """可选交易日列表"""
    try:
        return jsonify({'code': 0, 'data': svc.get_available_dates()})
    except Exception as e:
        logger.error(f"获取日期失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@range_analysis_bp.route('/api/range-analysis/timestamps')
def api_timestamps():
    """某日所有tick时间戳"""
    date = request.args.get('date', '').strip()
    if not date:
        return jsonify({'code': 1, 'message': '缺少date参数'})
    try:
        return jsonify({'code': 0, 'data': svc.get_timestamps(date)})
    except Exception as e:
        logger.error(f"获取时间戳失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@range_analysis_bp.route('/api/range-analysis/range')
def api_range():
    """区间聚合：最强/最弱行业当选次数排行"""
    date = request.args.get('date', '').strip()
    start_time = request.args.get('start_time', '').strip()
    end_time = request.args.get('end_time', '').strip()
    metric = request.args.get('metric', 'change_pct').strip()

    if not (date and start_time and end_time):
        return jsonify({'code': 1, 'message': '缺少date/start_time/end_time参数'})
    try:
        data = svc.query_range_industry(date, start_time, end_time, metric)
        return jsonify({'code': 0, 'data': data})
    except Exception as e:
        logger.error(f"区间聚合失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@range_analysis_bp.route('/api/range-analysis/industry-trend')
def api_industry_trend():
    """某行业区间趋势"""
    date = request.args.get('date', '').strip()
    code = request.args.get('code', '').strip()
    start_time = request.args.get('start_time', '').strip()
    end_time = request.args.get('end_time', '').strip()
    metric = request.args.get('metric', 'change_pct').strip()

    if not (date and code and start_time and end_time):
        return jsonify({'code': 1, 'message': '缺少参数'})
    try:
        data = svc.get_industry_trend(date, code, start_time, end_time, metric)
        return jsonify({'code': 0, 'data': data})
    except Exception as e:
        logger.error(f"行业趋势失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})
