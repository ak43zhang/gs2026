"""分析中心路由"""

from flask import Blueprint, render_template

analysis_center_bp = Blueprint('analysis_center', __name__)


@analysis_center_bp.route('/analysis-center')
def analysis_center():
    """分析中心主页面"""
    return render_template('analysis_center.html')
