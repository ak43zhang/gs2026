"""
自动交易面板Flask路由模块
注入到现有server.py的Blueprint

用法:
    from auto_trader_routes import create_auto_trader_blueprint
    bp = create_auto_trader_blueprint()
    app.register_blueprint(bp, url_prefix='/api/auto_trade')
"""

from flask import Blueprint, jsonify, request, Response
from pathlib import Path


def create_auto_trader_blueprint():
    """
    创建自动交易面板Blueprint
    """
    bp = Blueprint('auto_trader', __name__)
    templates_dir = Path(__file__).resolve().parent / 'templates'

    @bp.route('/panel')
    def auto_trader_panel():
        """自动交易面板HTML页面"""
        html_path = templates_dir / 'auto_trader_panel.html'
        if html_path.exists():
            html_content = html_path.read_text(encoding='utf-8')
        else:
            # 如果专用面板不存在,使用通用面板
            html_path = templates_dir / 'panel.html'
            html_content = html_path.read_text(encoding='utf-8')
        return Response(html_content, content_type='text/html; charset=utf-8')

    @bp.route('/status', methods=['GET'])
    def auto_trader_status():
        """获取当前状态(每秒轮询)"""
        try:
            from trade_hook import get_status
            status = get_status()
            if status:
                return jsonify(status)
            else:
                return jsonify({
                    'state': 'DISABLED',
                    'hit_list': [],
                    'current': None,
                    'monitoring': None,
                    'history': [],
                })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/buy/<code>', methods=['POST'])
    def auto_trader_buy(code: str):
        """选择买入某code"""
        try:
            from auto_trader import get_auto_trader
            trader = get_auto_trader()
            result = trader.on_buy_click(code)
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @bp.route('/cancel', methods=['POST'])
    def auto_trader_cancel():
        """撤单(当前交易中)"""
        # TODO: 实现撤单API
        return jsonify({'success': True, 'message': '撤单功能待实现'})

    @bp.route('/skip', methods=['POST'])
    def auto_trader_skip():
        """跳过当前命中"""
        # TODO: 实现跳过API
        return jsonify({'success': True, 'message': '跳过功能待实现'})

    return bp
