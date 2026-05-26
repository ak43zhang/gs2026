"""
买点候选回填工具 - 按真实逻辑回填历史买点候选数据到 buy_point_candidates 表

条件逻辑（与前端 BP_CONDITIONS 一致）：
  大盘条件（4个，仅记录不影响入选）：
    - 股票红柱>涨家数, 股票tick比>1.0, 债券红柱>涨家数, 债券tick比>1.0
  必要条件（4个，全部通过才入选）：
    - 主力/峰值 > 0.9
    - 涨幅 > 2%
    - 连续上攻 > 0
    - 债券在排行
  加分条件（2个，决定星级）：
    - 行业前10
    - 债券涨幅 > 2%
  星级 = 1 + min(bonus, 2)，只保存 >= 2星

用法：
  # 回填指定日期（全量时间点）
  python tools/backfill_buy_points.py --date 20260519

  # 回填指定日期和时间范围
  python tools/backfill_buy_points.py --date 20260519 --start 09:30:00 --end 10:00:00

  # 仅预览不写入
  python tools/backfill_buy_points.py --date 20260519 --dry-run

  # 指定采样间隔（秒），默认3
  python tools/backfill_buy_points.py --date 20260519 --interval 30
"""
import sys, json, hashlib, argparse, time as _time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache
from gs2026.dashboard2.config import Config


def parse_args():
    parser = argparse.ArgumentParser(description='买点候选回填工具')
    parser.add_argument('--date', required=True, help='日期，格式 YYYYMMDD，如 20260519')
    parser.add_argument('--start', default=None, help='起始时间，格式 HH:MM:SS，默认从最早时间开始')
    parser.add_argument('--end', default=None, help='结束时间，格式 HH:MM:SS，默认到最晚时间')
    parser.add_argument('--interval', type=int, default=3, help='采样间隔（秒），默认3（全量）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览不写入数据库')
    parser.add_argument('--clear', action='store_true', help='回填前清除该日期已有数据（默认使用UPSERT）')
    return parser.parse_args()


def get_engine():
    """获取数据库引擎"""
    return create_engine(Config.MYSQL_URI, pool_recycle=3600, pool_pre_ping=True)


def get_available_times(engine, table, start=None, end=None, interval=3):
    """获取可用时间点"""
    with engine.connect() as conn:
        where = ""
        if start:
            where += f" AND time >= '{start}'"
        if end:
            where += f" AND time <= '{end}'"
        result = conn.execute(text(f"SELECT DISTINCT time FROM {table} WHERE 1=1{where} ORDER BY time"))
        all_times = [str(row[0]) for row in result]
    
    if interval <= 3:
        return all_times
    
    # 按间隔采样
    sampled = []
    last_sec = -interval
    for t in all_times:
        parts = t.split(':')
        total_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if total_sec - last_sec >= interval:
            sampled.append(t)
            last_sec = total_sec
    return sampled


def evaluate_candidates(stocks, top_industries, bond_rank_set, bond_rank_map):
    """评估买点候选"""
    candidates = []
    for stock in stocks:
        code = stock.get('code', '')
        cum_net = float(stock.get('cumulative_main_net', 0) or 0)
        peak_net = float(stock.get('max_cumulative_main_net', 0) or 0)
        chg_pct = stock.get('change_pct')
        consec = int(stock.get('consecutive_attacks', 0) or 0)
        bond_code = stock.get('bond_code', '') or ''
        ind_name = stock.get('industry_name', '') or ''
        
        if chg_pct is None:
            continue
        chg_pct = float(chg_pct)
        
        # 必要条件（全部通过才入选）
        ratio = cum_net / peak_net if peak_net > 0 else 0
        cond_ratio = ratio > 0.9
        cond_chg = chg_pct > 2
        cond_consec = consec > 0
        cond_bond_rank = bond_code != '-' and bond_code != '' and bond_code in bond_rank_set
        
        if not (cond_ratio and cond_chg and cond_consec and cond_bond_rank):
            continue
        
        # 加分条件（决定星级）
        cond_ind = ind_name in top_industries
        bond_data = bond_rank_map.get(bond_code, {})
        bond_chg_val = float(bond_data.get('change_pct', 0) or 0)
        cond_bond_chg = bond_chg_val > 2
        
        bonus = sum([cond_ind, cond_bond_chg])
        level = 1 + min(bonus, 2)
        
        # 只保存 >= 2星
        if level < 2:
            continue
        
        bond_price_val = bond_data.get('price')
        
        candidates.append({
            'code': code,
            'name': stock.get('name', ''),
            'price': stock.get('price'),
            'change_pct': round(chg_pct, 2),
            'bond_code': bond_code,
            'bond_price': float(bond_price_val) if bond_price_val else None,
            'bond_chg': round(bond_chg_val, 2),
            'level': level,
            'cond_ratio': cond_ratio,
            'cond_chg': cond_chg,
            'cond_consec': cond_consec,
            'cond_bond_rank': cond_bond_rank,
            'cond_ind': cond_ind,
            'cond_bond_chg': cond_bond_chg
        })
    
    candidates.sort(key=lambda x: (-x['level'], -x['change_pct']))
    return candidates[:30]


def backfill(args):
    """执行回填"""
    date = args.date
    save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    table = f'monitor_gp_sssj_{date}'
    bond_table = f'monitor_zq_sssj_{date}'
    
    print(f"=== 买点候选回填: {save_date} ===")
    if args.dry_run:
        print("[DRY-RUN] 仅预览，不写入数据库")
    
    data_service = DataService()
    cache = get_cache()
    engine = get_engine()
    
    # 检查表是否存在
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='gs' AND TABLE_NAME='{table}'"))
        if result.fetchone()[0] == 0:
            print(f"ERROR: 表 {table} 不存在")
            return
    
    # 清除已有数据
    if args.clear and not args.dry_run:
        with engine.connect() as conn:
            result = conn.execute(text(f"DELETE FROM buy_point_candidates WHERE date = '{save_date}'"))
            conn.commit()
            print(f"已清除 {result.rowcount} 条旧数据")
    
    # 获取时间点
    sample_times = get_available_times(engine, table, args.start, args.end, args.interval)
    print(f"时间点: {len(sample_times)} 个 (间隔 {args.interval}s)")
    
    insert_sql = text("""
        INSERT INTO buy_point_candidates 
        (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
         bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
         conditions, market_context)
        VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
         :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
         :conditions, :market_context)
        ON DUPLICATE KEY UPDATE
        stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
        bond_price=VALUES(bond_price), bond_change_pct=VALUES(bond_change_pct),
        level=VALUES(level), conditions=VALUES(conditions), market_context=VALUES(market_context)
    """)
    
    total_inserted = 0
    t0 = _time.time()
    
    for idx, time_str in enumerate(sample_times):
        # 1. 获取股票上攻排行
        stocks = data_service.get_ranking_at_time(asset_type='stock', limit=500, date=date, time_str=time_str)
        if not stocks:
            continue
        
        # 2. 补充债券/行业信息
        stock_codes = [s.get('code', '') for s in stocks if s.get('code')]
        if not stock_codes:
            continue
        mappings = cache.get_mappings_smart(stock_codes)
        for stock in stocks:
            code = stock.get('code', '')
            mapping = mappings.get(code)
            if mapping:
                stock['bond_code'] = mapping.get('bond_code', '-')
                stock['industry_name'] = mapping.get('industry_name', '-')
            else:
                stock['bond_code'] = '-'
                stock['industry_name'] = '-'
        
        # 3. 从sssj表补充涨跌幅/主力净额/连续上攻/价格
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        try:
            with engine.connect() as conn:
                df = pd.read_sql(text(f"""
                    SELECT stock_code, change_pct, cumulative_main_net, max_cumulative_main_net, 
                           consecutive_attacks, price
                    FROM {table}
                    WHERE time = '{time_str}' AND stock_code IN ({codes_str})
                """), conn)
        except:
            continue
        
        if df.empty:
            continue
        
        df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
        chg_map = dict(zip(df['stock_code'], df['change_pct'].astype(float)))
        net_map = dict(zip(df['stock_code'], df['cumulative_main_net'].fillna(0).astype(float)))
        peak_map = dict(zip(df['stock_code'], df['max_cumulative_main_net'].fillna(0).astype(float)))
        consec_map = dict(zip(df['stock_code'], df['consecutive_attacks'].fillna(0).astype(int)))
        price_map = dict(zip(df['stock_code'], df['price'].fillna(0).astype(float)))
        
        for stock in stocks:
            code = stock.get('code', '')
            stock['change_pct'] = chg_map.get(code)
            stock['cumulative_main_net'] = net_map.get(code, 0)
            stock['max_cumulative_main_net'] = peak_map.get(code, 0)
            stock['consecutive_attacks'] = consec_map.get(code, 0)
            stock['price'] = price_map.get(code)
        
        # 4. 获取行业排行前10
        industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=time_str)
        top_industries = set()
        if industry_data:
            for ind in industry_data:
                name = ind.get('name', '') or ind.get('industry_name', '')
                if name:
                    top_industries.add(name)
        
        # 5. 获取债券上攻排行
        bond_rank = data_service.get_ranking_at_time(asset_type='bond', limit=30, date=date, time_str=time_str)
        bond_rank_set = set()
        bond_rank_map = {}
        if bond_rank:
            for b in bond_rank:
                bc = str(b.get('code', ''))
                bond_rank_set.add(bc)
                bond_rank_map[bc] = b
        
        # 5.5 从monitor_zq_sssj获取债券真实涨幅和价格
        if bond_rank_set:
            bond_codes_str = ','.join([f"'{c}'" for c in bond_rank_set])
            try:
                with engine.connect() as conn:
                    bond_df = pd.read_sql(text(f"""
                        SELECT bond_code, change_pct, price
                        FROM {bond_table}
                        WHERE time = '{time_str}' AND bond_code IN ({bond_codes_str})
                    """), conn)
                    if not bond_df.empty:
                        bond_df['bond_code'] = bond_df['bond_code'].astype(str)
                        for _, brow in bond_df.iterrows():
                            bc = brow['bond_code']
                            if bc in bond_rank_map:
                                bond_rank_map[bc]['change_pct'] = float(brow['change_pct'])
                                bond_rank_map[bc]['price'] = float(brow['price'])
            except:
                pass
        
        # 6. 获取大盘数据
        market_data = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)
        stock_stats = market_data.get('stock', {}) if market_data else {}
        bond_stats = market_data.get('bond', {}) if market_data else {}
        if not stock_stats:
            stock_stats = {}
        if not bond_stats:
            bond_stats = {}
        
        body_up = float(stock_stats.get('body_up', 0) or 0)
        cur_up = float(stock_stats.get('cur_up', 0) or 0)
        min_up = float(stock_stats.get('min_up', 0) or 0)
        min_down = float(stock_stats.get('min_down', 0) or 0)
        tick_ratio = round(min_up / min_down, 2) if min_down > 0 else 0
        
        b_body_up = float(bond_stats.get('body_up', 0) or 0)
        b_cur_up = float(bond_stats.get('cur_up', 0) or 0)
        b_min_up = float(bond_stats.get('min_up', 0) or 0)
        b_min_down = float(bond_stats.get('min_down', 0) or 0)
        b_tick = round(b_min_up / b_min_down, 2) if b_min_down > 0 else 0
        
        mkt_conds = [
            {'name': 'gp_body>up', 'passed': body_up > cur_up},
            {'name': 'gp_tick>1', 'passed': tick_ratio > 1.0},
            {'name': 'zq_body>up', 'passed': b_body_up > b_cur_up},
            {'name': 'zq_tick>1', 'passed': b_tick > 1.0}
        ]
        mkt_pass = sum(1 for c in mkt_conds if c['passed'])
        signal = 'positive' if mkt_pass >= 4 else ('cautious' if mkt_pass >= 2 else 'wait')
        
        # 7. 评估候选
        candidates = evaluate_candidates(stocks, top_industries, bond_rank_set, bond_rank_map)
        
        if not candidates:
            continue
        
        # 8. 保存
        if not args.dry_run:
            with engine.connect() as conn:
                for c in candidates:
                    record_id = hashlib.md5(f"{c['code']}{save_date}{time_str}".encode()).hexdigest()
                    conditions = [
                        {'name': 'net_ratio>0.9', 'passed': c['cond_ratio']},
                        {'name': 'chg>2%', 'passed': c['cond_chg']},
                        {'name': 'consec>0', 'passed': c['cond_consec']},
                        {'name': 'bond_in_rank', 'passed': c['cond_bond_rank']},
                        {'name': 'ind_top10', 'passed': c['cond_ind']},
                        {'name': 'bond_chg>2%', 'passed': c['cond_bond_chg']}
                    ]
                    cond_count = sum(1 for x in conditions if x['passed'])
                    market_ctx = {'signal': signal, 'passed': mkt_pass, 'total': 4, 'conditions': mkt_conds}
                    
                    params = {
                        'record_id': record_id, 'date': save_date, 'time': time_str,
                        'stock_code': c['code'], 'stock_name': c['name'],
                        'stock_price': c['price'], 'stock_change_pct': c['change_pct'],
                        'bond_code': c['bond_code'], 'bond_price': c['bond_price'],
                        'bond_change_pct': c['bond_chg'], 'level': c['level'],
                        'condition_count': cond_count, 'total_conditions': 6,
                        'conditions': json.dumps(conditions), 'market_context': json.dumps(market_ctx)
                    }
                    conn.execute(insert_sql, params)
                    total_inserted += 1
                conn.commit()
        
        stars = {2: 0, 3: 0}
        for c in candidates:
            stars[c['level']] = stars.get(c['level'], 0) + 1
        
        # 进度显示（每100个时间点或有候选时输出）
        if (idx + 1) % 100 == 0 or len(candidates) > 0:
            elapsed = _time.time() - t0
            pct = (idx + 1) / len(sample_times) * 100
            print(f"  [{pct:5.1f}%] {time_str}: {len(candidates)} cands (3*={stars.get(3,0)}, 2*={stars.get(2,0)}) | total={total_inserted} | {elapsed:.0f}s")
    
    # 最终统计
    elapsed = _time.time() - t0
    print(f"\n=== 完成 ===")
    print(f"耗时: {elapsed:.1f}s")
    
    if not args.dry_run:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*), SUM(level=2), SUM(level=3) FROM buy_point_candidates WHERE date = '{save_date}'"))
            row = result.fetchone()
            print(f"入库: {row[0]} 条 (2星={row[1]}, 3星={row[2]})")
    else:
        print(f"预览: {total_inserted} 条候选（未写入）")


if __name__ == '__main__':
    args = parse_args()
    backfill(args)
