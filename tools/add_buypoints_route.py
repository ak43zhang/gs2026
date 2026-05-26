# add_buypoints_route.py
import sys

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find end of file
end = len(lines)
insert_idx = end

# Build the buy-points route
route = '''

@monitor_bp.route('/api/monitor/buy-points', methods=['GET'])
def get_buy_points():
    """买点候选：基于多条件筛选"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
        
        # 获取大盘数据
        market_data = data_service.get_market_stats(date=date, use_mysql=True)
        stock_stats = market_data.get('stock', {}) if market_data else {}
        
        # 大盘条件评估
        body_up = stock_stats.get('body_up', 0) or 0
        cur_up = stock_stats.get('cur_up', 0) or 0
        tick_ratio = stock_stats.get('min_up_down_ratio', 0) or 0
        strength = stock_stats.get('strength_score', 0) or 0
        
        market_conditions = [
            {'name': '红柱>涨家数', 'passed': body_up > cur_up, 'detail': f'红柱{body_up} vs 涨{cur_up}'},
            {'name': 'tick比>100', 'passed': tick_ratio > 100, 'detail': f'tick比 {tick_ratio:.1f}'},
            {'name': '强度>50', 'passed': strength > 50, 'detail': f'强度 {strength:.1f}'},
        ]
        
        passed_count = sum(1 for c in market_conditions if c['passed'])
        total_count = len(market_conditions)
        
        if passed_count >= total_count * 0.8:
            market_signal = '积极'
        elif passed_count >= total_count * 0.6:
            market_signal = '谨慎'
        else:
            market_signal = '观望'
        
        return jsonify(
            success=True,
            market={
                'conditions': market_conditions,
                'passed': passed_count,
                'total': total_count,
                'signal': market_signal
            },
            candidates=[],
            count=0
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500
'''

lines.append(route)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Route added. New file: {len(lines)} lines')
