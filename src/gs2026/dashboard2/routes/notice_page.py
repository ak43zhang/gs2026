"""公告分析路由"""

from flask import Blueprint, render_template

notice_analysis_bp = Blueprint('notice_analysis', __name__)


@notice_analysis_bp.route('/notice-analysis')
def notice_analysis():
    """公告分析页面"""
    return render_template('notice_analysis.html')
