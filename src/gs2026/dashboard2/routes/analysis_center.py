"""分析中心路由"""

from flask import Blueprint, render_template

analysis_center_bp = Blueprint('analysis_center', __name__)


@analysis_center_bp.route('/ztb-analysis')
def analysis_center():
    """涨停分析主页面"""
    return render_template('analysis_center.html')
