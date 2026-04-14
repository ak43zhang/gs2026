"""
股票-债券-行业映射 API
"""

from flask import Blueprint, jsonify
from gs2026.utils.stock_bond_mapping_cache import get_cache

bp = Blueprint('stock_bond_mapping', __name__, url_prefix='/api/stock-bond-mapping')


@bp.route('/status', methods=['GET'])
def get_status():
    """获取缓存状态"""
    cache = get_cache()
    
    return jsonify({
        "success": True,
        "latest_date": cache.get_latest_date(),
        "is_valid": cache.is_cache_valid(),
        "meta": cache.get_meta()
    })


@bp.route('/update', methods=['POST'])
def force_update():
    """手动触发更新"""
    cache = get_cache()
    result = cache.update_mapping(force=True)
    return jsonify(result)


@bp.route('/<stock_code>', methods=['GET'])
def get_mapping(stock_code):
    """获取单只股票映射"""
    cache = get_cache()
    
    # 确保缓存存在
    if not cache.ensure_cache():
        return jsonify({
            "success": False,
            "message": "缓存创建失败"
        }), 500
    
    mapping = cache.get_mapping(stock_code)
    
    return jsonify({
        "success": True,
        "exists": mapping is not None,
        "data": mapping
    })
