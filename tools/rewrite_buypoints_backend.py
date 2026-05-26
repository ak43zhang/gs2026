# rewrite_buypoints_backend.py
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the entire buy-points route
old_marker = "@monitor_bp.route('/buy-points', methods=['GET'])"
if old_marker not in content:
    print('ERROR: buy-points route not found')
    exit(1)

# Find the start of the route
start = content.find(old_marker)
# Find the end - next @monitor_bp.route or end of file
next_route = content.find('@monitor_bp.route', start + 10)
if next_route == -1:
    end = len(content)
else:
    end = next_route

# Also trim any trailing newlines before the next route
while end > start and content[end-1] == '\n':
    end -= 1

print(f'Replacing buy-points route: chars {start}-{end}')

new_route = '''@monitor_bp.route('/buy-points', methods=['GET'])
def get_buy_points():
    """买点候选：基于可配置条件筛选"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
        time_str = request.args.get('time')

        # 解析条件参数
        body_gt_up = request.args.get('body_gt_up', 'true') == 'true'
        tick_ratio_min = float(request.args.get('tick_ratio_min', '1.0'))
        strength_min = float(request.args.get('strength_min', '0'))
        net_ratio_min = float(request.args.get('net_ratio_min', '0.9'))
        industry_top = int(request.args.get('industry_top', '10'))
        change_pct_min = float(request.args.get('change_pct_min', '0'))

        # 1. 获取大盘数据
        market_data = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)
        stock_stats = market_data.get('stock', {}) if market_data else {}

        body_up = float(stock_stats.get('body_up', 0) or 0)
        cur_up = float(stock_stats.get('cur_up', 0) or 0)
        min_up = float(stock_stats.get('min_up', 0) or 0)
        min_down = float(stock_stats.get('min_down', 0) or 0)
        tick_ratio = round(min_up / min_down, 2) if min_down > 0 else 0
        strength = float(stock_stats.get('strength_score', 0) or 0)

        # 2. 评估大盘条件
        market_conditions = []
        if body_gt_up:
            market_conditions.append({
                'name': '红柱>涨家数',
                'passed': body_up > cur_up,
                'detail': f'红柱{int(body_up)} vs 涨{int(cur_up)}'
            })
        if tick_ratio_min > 0:
            market_conditions.append({
                'name': f'tick比>{tick_ratio_min}',
                'passed': tick_ratio > tick_ratio_min,
                'detail': f'tick比 {tick_ratio}'
            })
        if strength_min > 0:
            market_conditions.append({
                'name': f'强度>{strength_min}',
                'passed': strength > strength_min,
                'detail': f'强度 {strength:.1f}'
            })

        passed_count = sum(1 for c in market_conditions if c['passed'])
        total_count = len(market_conditions) if market_conditions else 1

        if total_count == 0 or passed_count >= total_count * 0.8:
            market_signal = '积极'
        elif passed_count >= total_count * 0.6:
            market_signal = '谨慎'
        else:
            market_signal = '观望'

        # 3. 获取股票排行
        stocks = data_service.get_rising_ranking(
            asset_type='stock', limit=500, date=date, use_mysql=True)
        if not stocks:
            stocks = []

        # 4. 获取行业排行前N
        industry_data = data_service.get_rising_ranking(
            asset_type='industry', limit=industry_top, date=date, use_mysql=True)
        top_industries = set()
        if industry_data:
            for ind in industry_data:
                name = ind.get('name', '') or ind.get('industry_name', '')
                if name:
                    top_industries.add(name)

        # 5. 逐股评估
        candidates = []
        for stock in stocks:
            cum_net = float(stock.get('cumulative_main_net', 0) or 0)
            peak_net = float(stock.get('max_cumulative_main_net', 0) or 0)
            chg_pct = stock.get('change_pct')
            if isinstance(chg_pct, str):
                try:
                    chg_pct = float(chg_pct)
                except (ValueError, TypeError):
                    chg_pct = None

            # 条件: 主力净额/峰值
            ratio = cum_net / peak_net if peak_net > 0 else 0
            cond_ratio = ratio > net_ratio_min if net_ratio_min > 0 else False

            # 条件: 行业排行
            ind_name = stock.get('industry_name', '') or ''
            cond_ind = ind_name in top_industries if industry_top > 0 else False

            # 条件: 涨幅
            cond_pct = (chg_pct is not None and chg_pct > change_pct_min) if change_pct_min > 0 else False

            score = sum([cond_ratio, cond_ind, cond_pct])
            if score > 0:
                candidates.append({
                    'code': stock.get('code', ''),
                    'name': stock.get('name', ''),
                    'change_pct': round(chg_pct, 2) if chg_pct is not None else None,
                    'net_ratio': round(ratio, 3),
                    'industry_name': ind_name,
                    'cond_net_ratio': cond_ratio,
                    'cond_industry': cond_ind,
                    'cond_change_pct': cond_pct,
                    'score': score
                })

        candidates.sort(key=lambda x: (-x['score'], -x['net_ratio']))
        candidates = candidates[:30]

        return jsonify(
            success=True,
            market={
                'conditions': market_conditions,
                'passed': passed_count,
                'total': total_count,
                'signal': market_signal
            },
            candidates=candidates,
            count=len(candidates)
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500
'''

content = content[:start] + new_route + content[end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Backend route rewritten')

# Verify
import py_compile
py_compile.compile(path, doraise=True)
print('Syntax OK')
