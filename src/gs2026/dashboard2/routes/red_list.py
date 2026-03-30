"""
红名单 API 路由（简化版）
"""
from flask import Blueprint, jsonify

from gs2026.dashboard2.routes.red_list_cache import (
    update_red_list_cache, get_red_list, is_in_red_list
)

bp = Blueprint("red_list", __name__, url_prefix="/api/red-list")


@bp.route("/status", methods=["GET"])
def get_status():
    """获取红名单状态"""
    codes = get_red_list()
    return jsonify({
        "success": True,
        "count": len(codes),
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
    """手动更新红名单"""
    result = update_red_list_cache()
    return jsonify(result)
