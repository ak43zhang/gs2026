"""领域分析路由"""

from flask import Blueprint, render_template

domain_analysis_bp = Blueprint('domain_analysis_page', __name__)


@domain_analysis_bp.route('/domain-analysis')
def domain_analysis():
    """领域分析页面"""
    return render_template('domain_analysis.html')
