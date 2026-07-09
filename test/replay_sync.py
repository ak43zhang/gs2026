#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步版本量化选债历史数据回放测试
使用SQLAlchemy同步查询，兼容DataService
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from sqlalchemy import text
import pandas as pd

# 导入系统模块
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.routes import monitor


def ensure_table_exists(engine):
    """确保quant_screen_hits表存在"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = 'quant_screen_hits'
        """))
        count = result.scalar()
        
        if count == 0:
            print("[数据库] quant_screen_hits表不存在，自动创建...")
            sql_file = Path(__file__).parent.parent / 'temp' / 'create_quant_screen_hits.sql'
            if sql_file.exists():
                sql_content = sql_file.read_text(encoding='utf-8')
                statements = [s.strip() for s in sql_content.split(';') if s.strip()]
                for stmt in statements:
                    if stmt and not stmt.startswith('--') and not stmt.startswith('/*'):
                        try:
                            conn.execute(text(stmt))
                        except Exception as e:
                            print(f"[警告] 执行SQL失败: {e}")
                conn.commit()
                print("[数据库] 表创建完成")
            else:
                raise FileNotFoundError(f"SQL文件不存在: {sql_file}")
        else:
            print("[数据库] quant_screen_hits表已存在")


def fetch_tick_groups(engine, trade_date, time_start, time_end):
    """读取tick分组"""
    table_name = f"monitor_zq_sssj_{trade_date}"
    
    sql = text(f"""
        SELECT * FROM {table_name}
        WHERE time BETWEEN :start AND :end
        ORDER BY time
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'start': time_start, 'end': time_end})
    
    if df.empty:
        return []
    
    # 按time分组
    groups = []
    for tick_time, group in df.groupby('time'):
        groups.append((str(tick_time), group))
    
    return groups


def mock_get_current_sssj(date):
    """Mock函数，返回预设数据"""
    global _current_tick_data
    return _current_tick_data


def run_quant_screen_core(df_tick, schemes, trade_date, tick_time):
    """核心筛选逻辑"""
    import flask
    from flask import Flask
    
    app = Flask(__name__)
    
    request_data = {
        'date': trade_date,
        'time': tick_time,
        'schemes': schemes
    }
    
    with app.test_request_context(
        path='/api/monitor/quant-screen',
        method='POST',
        data=json.dumps(request_data),
        content_type='application/json'
    ):
        flask.request._cached_json = request_data
        
        try:
            # 检查是否为异步函数
            import inspect
            if inspect.iscoroutinefunction(monitor.quant_screen):
                import asyncio
                result = asyncio.run(monitor.quant_screen())
            else:
                result = monitor.quant_screen()
            
            if hasattr(result, 'get_json'):
                return result.get_json()
            elif isinstance(result, dict):
                return result
            return {'success': False, 'error': 'Invalid response'}
        except Exception as e:
            print(f"[错误] 调用quant_screen失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}


def save_hits_to_mysql(engine, hits, trade_date, tick_time, schemes):
    """保存命中记录到MySQL"""
    if not hits:
        return
    
    with engine.connect() as conn:
        for match in hits:
            scheme_name = match.get('scheme_name', '')
            bond_code = match.get('bond_code', '')
            bond_name = match.get('bond_name', '')
            entry_price = match.get('price', 0)
            entry_change_pct = match.get('change_pct', 0)
            entry_amount = match.get('amount', 0)
            
            # 查找方案参数
            stop_loss_pct = 0
            take_profit_pct = 0
            max_hold_time = None
            for s in schemes:
                if s['name'] == scheme_name:
                    stop_loss_pct = s.get('stop_loss', 0)
                    take_profit_pct = s.get('take_profit', 0)
                    max_hold_time = s.get('max_hold_time')
                    break
            
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
            take_profit_price = entry_price * (1 + take_profit_pct / 100) if take_profit_pct else None
            
            sql = text("""
                INSERT INTO quant_screen_hits (
                    trade_date, tick_time, scheme_name, bond_code, bond_name,
                    entry_price, entry_change_pct, entry_amount,
                    stop_loss_pct, take_profit_pct, max_hold_time,
                    stop_loss_price, take_profit_price,
                    current_price, current_return_pct, signal_status,
                    is_locked, created_at
                ) VALUES (
                    :trade_date, :tick_time, :scheme_name, :bond_code, :bond_name,
                    :entry_price, :entry_change_pct, :entry_amount,
                    :stop_loss_pct, :take_profit_pct, :max_hold_time,
                    :stop_loss_price, :take_profit_price,
                    :current_price, :current_return_pct, :signal_status,
                    :is_locked, NOW()
                )
            """)
            
            try:
                conn.execute(sql, {
                    'trade_date': trade_date,
                    'tick_time': tick_time,
                    'scheme_name': scheme_name,
                    'bond_code': bond_code,
                    'bond_name': bond_name,
                    'entry_price': entry_price,
                    'entry_change_pct': entry_change_pct,
                    'entry_amount': entry_amount,
                    'stop_loss_pct': stop_loss_pct,
                    'take_profit_pct': take_profit_pct,
                    'max_hold_time': max_hold_time,
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'current_price': entry_price,
                    'current_return_pct': 0,
                    'signal_status': 'entry',
                    'is_locked': 0
                })
            except Exception as e:
                print(f"[警告] 保存记录失败: {e}")
        
        conn.commit()


def replay(trade_date, time_start='093000', time_end='150000', speed='10x', schemes=None):
    """执行回放"""
    print(f"\n{'='*60}")
    print(f"开始回放: {trade_date}")
    print(f"时段: {time_start} - {time_end}")
    print(f"速度: {speed}")
    print(f"{'='*60}\n")
    
    # 初始化DataService
    data_service = DataService()
    engine = data_service.engine
    
    # 确保表存在
    ensure_table_exists(engine)
    
    # Monkey Patch
    original_func = monitor._get_current_sssj
    monitor._get_current_sssj = mock_get_current_sssj
    
    global _current_tick_data
    
    try:
        # 读取tick分组
        tick_groups = fetch_tick_groups(engine, trade_date, time_start, time_end)
        
        if not tick_groups:
            print("[警告] 未找到tick数据")
            return
        
        print(f"[信息] 共 {len(tick_groups)} 个tick时间点")
        
        results = []
        total_ticks = 0
        start_time = datetime.now()
        
        for tick_time, df_tick in tick_groups:
            total_ticks += 1
            
            if total_ticks % 100 == 0:
                print(f"[进度] 处理第 {total_ticks}/{len(tick_groups)} 个tick: {tick_time}")
            
            # 设置当前tick数据
            _current_tick_data = df_tick
            
            # 调用筛选
            result = run_quant_screen_core(df_tick, schemes, trade_date, tick_time)
            
            # 保存命中
            if result.get('success') and result.get('matches'):
                save_hits_to_mysql(engine, result['matches'], trade_date, tick_time, schemes)
            
            results.append({
                'tick_time': tick_time,
                'match_count': len(result.get('matches', [])),
                'stats': result.get('stats', {})
            })
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # 汇总
        total_matches = sum(r['match_count'] for r in results)
        tick_with_matches = sum(1 for r in results if r['match_count'] > 0)
        
        print(f"\n{'='*60}")
        print(f"回放完成!")
        print(f"{'='*60}")
        print(f"总tick数: {total_ticks}")
        print(f"执行时间: {elapsed:.2f}秒")
        print(f"有命中的tick: {tick_with_matches}")
        print(f"总命中次数: {total_matches}")
        print(f"{'='*60}\n")
        
        # 验证数据库
        verify_database(engine, trade_date)
        
    finally:
        # 恢复原函数
        monitor._get_current_sssj = original_func


def verify_database(engine, trade_date):
    """验证数据库记录"""
    print(f"[验证] 检查数据库记录...")
    
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = :date"
        ), {'date': trade_date})
        total = result.scalar()
        print(f"  数据库记录总数: {total}")
        
        result = conn.execute(text("""
            SELECT signal_status, COUNT(*) 
            FROM quant_screen_hits 
            WHERE trade_date = :date 
            GROUP BY signal_status
        """), {'date': trade_date})
        for row in result:
            print(f"  状态 {row[0]}: {row[1]}条")
        
        result = conn.execute(text("""
            SELECT scheme_name, COUNT(*) 
            FROM quant_screen_hits 
            WHERE trade_date = :date 
            GROUP BY scheme_name
        """), {'date': trade_date})
        for row in result:
            print(f"  方案 {row[0]}: {row[1]}条")


def main():
    """主入口"""
    import argparse
    
    today = datetime.now().strftime('%Y%m%d')
    
    parser = argparse.ArgumentParser(description='量化选债历史数据回放测试（同步版）')
    parser.add_argument('--date', default=today, help=f'交易日期 (默认: {today})')
    parser.add_argument('--time-start', default='093000', help='开始时间')
    parser.add_argument('--time-end', default='100000', help='结束时间（默认1小时）')
    parser.add_argument('--schemes', help='方案JSON文件路径')
    
    args = parser.parse_args()
    
    # 默认方案
    schemes = [
        {
            'name': '强势反弹',
            'conditions': [
                {'field': 'change_pct', 'op': '>', 'value': 2.0, 'logic': 'AND'}
            ],
            'stop_loss': 3.0,
            'take_profit': 5.0,
            'max_hold_time': 30
        }
    ]
    
    if args.schemes and os.path.exists(args.schemes):
        with open(args.schemes, 'r', encoding='utf-8') as f:
            schemes = json.load(f)
    
    print(f"[加载] 使用 {len(schemes)} 个方案")
    
    # 执行回放
    replay(
        trade_date=args.date,
        time_start=args.time_start,
        time_end=args.time_end,
        schemes=schemes
    )


if __name__ == '__main__':
    main()
