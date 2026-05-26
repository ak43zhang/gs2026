"""
绿名单 API 路由
支持日期选择器切换日期
"""
from flask import Blueprint, jsonify, request

from gs2026.dashboard2.routes.green_bond_list_cache import (
    update_green_bond_list_cache, get_green_bond_list, 
    is_in_green_bond_list, get_green_bond_list_cache_date, 
    clear_green_bond_list_cache
)

bp = Blueprint("green_bond_list", __name__, url_prefix="/api/green-bond")


@bp.route("/status", methods=["GET"])
def get_status():
    """获取绿名单状态"""
    codes = get_green_bond_list()
    cache_date = get_green_bond_list_cache_date()
    return jsonify({
        "success": True,
        "count": len(codes),
        "date": cache_date,
        "codes": list(codes)[:20]  # 只返回前20个示例
    })


@bp.route("/check/<code>", methods=["GET"])
def check_code(code):
    """检查债券是否在绿名单中"""
    return jsonify({
        "success": True,
        "code": code,
        "is_green": is_in_green_bond_list(code)
    })


@bp.route("/update", methods=["POST"])
def force_update():
    """
    手动更新绿名单
    支持指定日期参数 date (YYYYMMDD)
    """
    # 获取日期参数，默认今天
    data = request.get_json(silent=True) or {}
    date_str = data.get('date') or request.args.get('date')
    
    result = update_green_bond_list_cache(date_str)
    return jsonify(result)


@bp.route("/clear", methods=["POST"])
def clear_cache():
    """清理绿名单缓存"""
    success = clear_green_bond_list_cache()
    return jsonify({
        "success": success,
        "message": "绿名单缓存已清理" if success else "清理失败"
    })


@bp.route("/list", methods=["GET"])
def get_list():
    """获取绿名单列表"""
    codes = get_green_bond_list()
    cache_date = get_green_bond_list_cache_date()
    return jsonify({
        "success": True,
        "date": cache_date,
        "count": len(codes),
        "codes": list(codes)
    })
