"""公告分析路由"""

from flask import Blueprint, render_template

from gs2026.dashboard2.services import notice_analysis_service

notice_analysis_bp = Blueprint('notice_analysis', __name__)


@notice_analysis_bp.route('/notice-analysis')
def notice_analysis():
    """公告分析页面"""
    return render_template('notice_analysis.html')


@notice_analysis_bp.route('/notice-detail/<content_hash>')
def notice_detail(content_hash):
    """公告分析详情页"""
    detail = notice_analysis_service.get_notice_detail(content_hash)
    if not detail:
        return render_template('notice_detail.html', detail=None, error='该公告不存在')
    return render_template('notice_detail.html', detail=detail)
