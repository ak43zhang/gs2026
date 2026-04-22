#!/usr/bin/env python3
"""
行业概念交叉选股路由
"""
import logging
import time
from flask import Blueprint, render_template, request, jsonify

from gs2026.dashboard2.services import stock_picker_service

logger = logging.getLogger(__name__)

stock_picker_bp = Blueprint('stock_picker', __name__, 
                            template_folder='../templates')


@stock_picker_bp.route('/stock-picker')
def index():
    """交叉行概选股页面"""
    return render_template('stock_picker.html')


@stock_picker_bp.route('/api/stock-picker/search')
def search():
    """搜索行业/概念"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    
    if not query:
        return jsonify({'code': 0, 'data': []})
    
    try:
        results = stock_picker_service.search_tags(query, limit)
        return jsonify({'code': 0, 'data': results})
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@stock_picker_bp.route('/api/stock-picker/query')
def query():
    """查询交叉选股结果"""
    tags_param = request.args.get('tags', '')
    
    if not tags_param:
        return jsonify({
            'code': 0,
            'data': {
                'tags': [],
                'groups': [],
                'summary': {'total_stocks': 0, 'with_bond': 0, 'query_time_ms': 0}
            }
        })
    
    # 解析 tags 参数: industry:881121,concept:309055,...
    selected_tags = []
    for tag_str in tags_param.split(','):
        if ':' not in tag_str:
            continue
        tag_type, code = tag_str.split(':', 1)
        
        # 根据code查找name
        # 这里简化处理，实际应该从搜索缓存中获取
        name = code  # 临时
        selected_tags.append({
            'name': name,
            'code': code,
            'type': tag_type
        })
    
    try:
        start_time = time.time()
        
        # 重新构建tags，包含正确的name
        # 从pinyin_searcher中获取
        searcher = stock_picker_service.init_pinyin_searcher()
        tag_map = {}
        for item in searcher.items:
            tag_map[f"{item['type']}:{item['code']}"] = {
                'name': item['name'],
                'code': item['code'],
                'type': item['type']
            }
        
        selected_tags = []
        invalid_tags = []
        for tag_str in tags_param.split(','):
            if tag_str in tag_map:
                selected_tags.append(tag_map[tag_str])
            else:
                invalid_tags.append(tag_str)
        
        # 如果有无效标签，返回提示
        if invalid_tags:
            return jsonify({
                'code': 0,
                'data': {
                    'tags': [],
                    'groups': [],
                    'summary': {'total_stocks': 0, 'with_bond': 0, 'query_time_ms': 0},
                    'message': f'以下标签无效: {", ".join(invalid_tags)}，请重新搜索选择'
                }
            })
        
        if not selected_tags:
            return jsonify({
                'code': 0,
                'data': {
                    'tags': [],
                    'groups': [],
                    'summary': {'total_stocks': 0, 'with_bond': 0, 'query_time_ms': 0},
                    'message': '未找到有效的行业或概念，请重新搜索选择'
                }
            })
        
        result = stock_picker_service.query_cross_stocks(selected_tags)
        result['summary']['query_time_ms'] = int((time.time() - start_time) * 1000)
        
        return jsonify({'code': 0, 'data': result})
        
    except Exception as e:
        logger.error(f"查询失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@stock_picker_bp.route('/api/stock-picker/refresh-cache', methods=['POST'])
def refresh_cache():
    """刷新缓存"""
    try:
        stock_picker_service.warm_up_cache()
        return jsonify({'code': 0, 'message': '缓存刷新成功'})
    except Exception as e:
        logger.error(f"刷新缓存失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@stock_picker_bp.route('/api/stock-picker/init-cache', methods=['POST'])
def init_cache():
    """初始化缓存（首次启动时调用）"""
    try:
        stock_picker_service.init_service()
        return jsonify({'code': 0, 'message': '缓存初始化成功'})
    except Exception as e:
        logger.error(f"初始化缓存失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@stock_picker_bp.route('/api/stock-picker/ztb-tags')
def ztb_tags():
    """获取涨停板行业概念标签"""
    date = request.args.get('date')
    try:
        result = stock_picker_service.get_ztb_tags(date)
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        logger.error(f"获取涨停标签失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})
