#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回填脚本 v2
使用统一核心引擎，与实时量化选债逻辑完全一致
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

# 导入系统模块
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.services.quant_screen_core import (
    apply_scheme_conditions,
    save_quant_screen_hits
)
from sqlalchemy import text


class QuantScreenBackfiller:
    """量化选债历史数据回填器"""
    
    def __init__(self):
        self.data_service = DataService()
        self.engine = self.data_service.engine
        
    def _check_table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        check_sql = text("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = :table_name
        """)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(check_sql, {'table_name': table_name}).scalar()
                return result > 0
        except Exception as e:
            print(f"[检查表失败] {table_name}: {e}")
            return False
    
    def _get_latest_trading_date(self) -> str:
        """获取最新交易日"""
        try:
            from gs2026.dashboard2.routes.monitor import _get_shared_engine
            from sqlalchemy import text
            engine = _get_shared_engine()
            sql = text("""
                SELECT trade_date FROM data_jyrl 
                WHERE trade_date <= CURDATE() AND trade_status = '1'
                ORDER BY trade_date DESC LIMIT 1
            """)
            with engine.connect() as conn:
                result = conn.execute(sql).fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"[获取最新交易日失败] {e}")
            return None
    
    def _fetch_tick_groups(self, trade_date: str, time_start: str, time_end: str):
        """获取tick数据分组"""
        table_name = f"monitor_zq_sssj_{trade_date}"
        
        # 检查表是否存在
        if not self._check_table_exists(table_name):
            latest_date = self._get_latest_trading_date()
            if latest_date:
                print(f"[警告] 表 {table_name} 不存在，使用最新交易日: {latest_date}")
                table_name = f"monitor_zq_sssj_{latest_date}"
                trade_date = latest_date
            else:
                print(f"[错误] 表 {table_name} 不存在，且未找到可用交易日")
                return []
        
        # 查询所有字段
        sql = text(f"""
            SELECT * FROM {table_name}
            WHERE time BETWEEN :start AND :end
            ORDER BY time
        """)
        
        try:
            import pandas as pd
            with self.engine.connect() as conn:
                df = pd.read_sql(sql, conn, params={'start': time_start, 'end': time_end})
        except Exception as e:
            print(f"[查询失败] {table_name}: {e}")
            return []
        
        if df.empty:
            print(f"[警告] {table_name} 在 {time_start}-{time_end} 无数据")
            return []
        
        # 按time分组
        groups = []
        for tick_time, group in df.groupby('time'):
            groups.append((str(tick_time), group))
        
        return groups
    
    def _load_schemes_from_mysql(self) -> list:
        """从MySQL加载在用方案"""
        try:
            sql = text("""
                SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, 
                       max_hold_time, price_offset, offset_mode
                FROM quant_screen_schemes 
                WHERE is_active = 1 AND use_realtime = 1
            """)
            with self.engine.connect() as conn:
                result = conn.execute(sql)
                schemes = []
                for row in result:
                    import json
                    schemes.append({
                        'name': row.scheme_name,
                        'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
                        'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                        'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                        'max_hold_time': row.max_hold_time,
                        'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                        'offset_mode': row.offset_mode or 'fixed'
                    })
                return schemes
        except Exception as e:
            print(f"[加载方案失败] {e}")
            return []
    
    async def backfill(self, trade_date: str, time_start: str = '093000', 
                       time_end: str = '150000', speed: str = '0'):
        """
        执行回填
        
        Args:
            trade_date: 交易日期 '20260709'
            time_start: 开始时间 '093000'
            time_end: 结束时间 '150000'
            speed: 播放速度 '0'=立即完成, '1x'=实时, '10x'=10倍速
        """
        print(f"\n{'='*60}")
        print(f"开始回填: {trade_date}")
        print(f"时段: {time_start} - {time_end}")
        print(f"速度: {speed}")
        print(f"{'='*60}\n")
        
        # 1. 加载方案
        print("[1/4] 加载方案...")
        schemes = self._load_schemes_from_mysql()
        print(f"      调试: schemes={schemes}")
        if not schemes:
            print("[错误] 没有在用方案，请先在系统中启用方案")
            return
        print(f"      加载 {len(schemes)} 个方案:")
        for sch in schemes:
            print(f"        - {sch['name']}")
        
        # 2. 获取tick数据
        print("\n[2/4] 加载tick数据...")
        tick_groups = self._fetch_tick_groups(trade_date, time_start, time_end)
        if not tick_groups:
            print("[错误] 无tick数据")
            return
        print(f"      共 {len(tick_groups)} 个tick时间点")
        
        # 3. 遍历处理每个tick
        print("\n[3/4] 处理tick数据...")
        results = []
        total_matches = 0
        
        for i, (tick_time, df) in enumerate(tick_groups):
            # 使用统一筛选引擎
            matches, stats = apply_scheme_conditions(df, schemes)
            
            if matches:
                # 使用统一保存逻辑
                save_quant_screen_hits(trade_date, tick_time, matches, schemes, df, self.engine)
                total_matches += len(matches)
                
                # 显示进度
                if (i + 1) % 100 == 0 or i == len(tick_groups) - 1:
                    print(f"      进度: {i+1}/{len(tick_groups)} ticks, "
                          f"累计命中: {total_matches} 条")
            
            results.append({
                'time': tick_time,
                'matches_count': len(matches),
                'stats': stats
            })
            
            # 速度控制
            if speed != '0':
                delay = 1.0 / float(speed.replace('x', ''))
                await asyncio.sleep(delay)
        
        # 4. 汇总
        print("\n[4/4] 回填完成!")
        print(f"      处理ticks: {len(results)}")
        print(f"      总命中数: {total_matches}")
        
        # 统计各方案命中
        scheme_stats = {}
        for r in results:
            for name, count in r['stats'].items():
                scheme_stats[name] = scheme_stats.get(name, 0) + count
        
        print("\n      各方案命中统计:")
        for name, count in scheme_stats.items():
            print(f"        - {name}: {count}")
        
        return {
            'success': True,
            'trade_date': trade_date,
            'total_ticks': len(results),
            'total_matches': total_matches,
            'scheme_stats': scheme_stats
        }


async def main():
    today = datetime.now().strftime('%Y%m%d')
    
    parser = argparse.ArgumentParser(description='量化选债历史数据回填')
    parser.add_argument('--date', default=today, help=f'交易日期 (默认: {today})')
    parser.add_argument('--time-start', default='093000', help='开始时间 (默认: 093000)')
    parser.add_argument('--time-end', default='150000', help='结束时间 (默认: 150000)')
    parser.add_argument('--speed', default='0', help='速度: 0=立即, 1x=实时, 10x=10倍速')
    
    args = parser.parse_args()
    
    backfiller = QuantScreenBackfiller()
    result = await backfiller.backfill(
        trade_date=args.date,
        time_start=args.time_start,
        time_end=args.time_end,
        speed=args.speed
    )
    
    if result and result.get('success'):
        print("\n✓ 回填成功!")
    else:
        print("\n✗ 回填失败")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
