"""
红名单 API 路由（优化版）
支持日期选择器切换日期
"""
from flask import Blueprint, jsonify, request

from gs2026.dashboard2.routes.red_list_cache import (
    update_red_list_cache, get_red_list, is_in_red_list, 
    get_red_list_cache_date, clear_red_list_cache
)

bp = Blueprint("red_list", __name__, url_prefix="/api/red-list")


@bp.route("/status", methods=["GET"])
def get_status():
    """获取红名单状态"""
    codes = get_red_list()
    cache_date = get_red_list_cache_date()
    return jsonify({
        "success": True,
        "count": len(codes),
        "date": cache_date,
        "codes": list(codes)[:20]  # 只返回前20个示例
    })


@bp.route("/check/<code>", methods=["GET"])
def check_code(code):
    """检查股票是否在红名单中"""
    return jsonify({
        "success": True,
        "code": code,
        "is_red": is_in_red_list(code)
    })


@bp.route("/update", methods=["POST"])
def force_update():
    """
    手动更新红名单
    支持指定日期参数 date (YYYYMMDD)
    """
    # 获取日期参数，默认今天
    data = request.get_json(silent=True) or {}
    date_str = data.get('date') or request.args.get('date')
    
    result = update_red_list_cache(date_str)
    return jsonify(result)


@bp.route("/clear", methods=["POST"])
def clear_cache():
    """清理红名单缓存"""
    success = clear_red_list_cache()
    return jsonify({
        "success": success,
        "message": "红名单缓存已清理" if success else "清理失败"
    })


@bp.route("/list", methods=["GET"])
def get_list():
    """获取红名单列表"""
    codes = get_red_list()
    cache_date = get_red_list_cache_date()
    return jsonify({
        "success": True,
        "date": cache_date,
        "count": len(codes),
        "codes": list(codes)
    })
