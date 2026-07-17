"""
交易面板Flask路由模块
注入到现有server.py的Blueprint

用法:
    from trade_panel_routes import create_trade_blueprint
    bp = create_trade_blueprint(trade_flow_manager)
    app.register_blueprint(bp)
"""

from flask import Blueprint, jsonify, request, Response
from pathlib import Path

def create_trade_blueprint(manager):
    """
    创建交易面板Blueprint
    
    Args:
        manager: TradeFlowManager实例
    """
    bp = Blueprint('trade_panel', __name__)
    templates_dir = Path(__file__).resolve().parent / 'templates'

    @bp.route('/panel')
    def panel_page():
        """面板HTML页面"""
        html_path = templates_dir / 'panel.html'
        html_content = html_path.read_text(encoding='utf-8')
        return Response(html_content, content_type='text/html; charset=utf-8')

    @bp.route('/api/trade/status')
    def trade_status():
        """获取当前状态(每秒轮询)"""
        return jsonify(manager.get_status())

    @bp.route('/api/trade/bought', methods=['POST'])
    def trade_bought():
        """用户点了买入(WAIT_BUY→CONFIRMING)"""
        manager.on_bought()
        return jsonify({'success': True, 'message': '已标记买入,开始30秒倒计时'})

    @bp.route('/api/trade/confirm', methods=['POST'])
    def trade_confirm():
        """确认成交→触发止盈止损"""
        manager.on_confirm()
        return jsonify({'success': True, 'message': '已确认,正在设置止盈止损'})

    @bp.route('/api/trade/cancel', methods=['POST'])
    def trade_cancel():
        """撤单"""
        manager.on_cancel()
        return jsonify({'success': True, 'message': '已撤单'})

    @bp.route('/api/trade/skip', methods=['POST'])
    def trade_skip():
        """跳过当前订单"""
        manager.on_skip()
        return jsonify({'success': True, 'message': '已跳过'})

    return bp

