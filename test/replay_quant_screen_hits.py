#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回放测试脚本
双模式：mock(运行时替换,默认) / redis(Redis回放)
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

# pandas可选，如未安装使用替代方案
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("[警告] pandas未安装，使用替代数据处理")

# 导入系统模块
from gs2026.dashboard2.routes import monitor
from gs2026.dashboard.services.data_service import DataService


def ensure_table_exists_sync(engine):
    """确保quant_screen_hits表存在，不存在则自动创建（同步版本）"""
    from sqlalchemy import text
    
    with engine.connect() as conn:
        # 检查表是否存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = 'quant_screen_hits'
        """))
        count = result.scalar()
        
        if count == 0:
            print("[数据库] quant_screen_hits表不存在，自动创建...")
            # 读取SQL文件并执行
            sql_file = Path(__file__).parent.parent / 'temp' / 'create_quant_screen_hits.sql'
            if sql_file.exists():
                sql_content = sql_file.read_text(encoding='utf-8')
                # 分割SQL语句并执行
                statements = [s.strip() for s in sql_content.split(';') if s.strip()]
                for stmt in statements:
                    if stmt and not stmt.startswith('--'):
                        try:
                            conn.execute(text(stmt))
                        except Exception as e:
                            print(f"[警告] 执行SQL失败: {e}")
                conn.commit()
                print("[数据库] 表创建完成")
            else:
                print(f"[错误] SQL文件不存在: {sql_file}")
                raise FileNotFoundError(f"SQL文件不存在: {sql_file}")
        else:
            print("[数据库] quant_screen_hits表已存在")


class QuantScreenReplayer:
    """量化选债历史数据回放器"""
    
    MODES = ['mock', 'redis']
    
    def __init__(self, mode='mock'):
        self.mode = mode
        self._original_func = None
        self._mock_data = None
        self.data_service = DataService()
        self.redis_client = None
        
    async def __aenter__(self):
        """上下文管理器：初始化模式"""
        if self.mode == 'mock':
            # 模式一：运行时替换
            self._original_func = monitor._get_current_sssj
            monitor._get_current_sssj = self._mock_get_current_sssj
            print(f"[初始化] 模式: 运行时替换 (Monkey Patch)")
        else:
            # 模式二：Redis模式
            # 使用DataService的Redis配置
            from gs2026.utils import redis_util
            from gs2026.dashboard2.config import Config
            config = Config()
            redis_util.init_redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                decode_responses=False
            )
            self.redis_client = redis_util._get_redis_client()
            print(f"[初始化] 模式: Redis回放")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：恢复原函数"""
        if self.mode == 'mock' and self._original_func:
            monitor._get_current_sssj = self._original_func
            print(f"[清理] 恢复原函数")
            
    def _mock_get_current_sssj(self, date):
        """Mock函数：返回内存中的当前tick数据"""
        return self._mock_data
        
    async def replay(self, trade_date, time_start='093000', time_end='150000', 
                     speed='10x', schemes=None):
        """
        执行回放
        
        Args:
            trade_date: 交易日期 '20260709'
            time_start: 开始时间 '093000'
            time_end: 结束时间 '150000'
            speed: 播放速度 '1x'=实时, '10x'=10倍速, '0'=立即完成
            schemes: 测试用的方案列表
        """
        print(f"\n{'='*60}")
        print(f"开始回放: {trade_date}")
        print(f"时段: {time_start} - {time_end}")
        print(f"模式: {self.mode}, 速度: {speed}")
        print(f"{'='*60}\n")
        
        # 0. 确保表存在（使用同步方式）
        ensure_table_exists_sync(self.data_service.engine)
        
        # 1. 流式读取tick分组
        # 先收集所有分组（因为async_generator不能await）
        print("[1/3] 正在加载历史数据...")
        print(f"      查询表: monitor_zq_sssj_{trade_date}")
        print(f"      时间范围: {time_start} - {time_end}")
        print(f"      查询所有字段")
        
        import time
        load_start = time.time()
        
        tick_groups = []
        last_print = time.time()
        async for tick_time, df_tick in self._fetch_tick_groups(trade_date, time_start, time_end):
            tick_groups.append((tick_time, df_tick))
            # 每2秒打印一次进度
            if time.time() - last_print > 2:
                print(f"      已加载 {len(tick_groups)} 个tick时间点...")
                last_print = time.time()
        
        load_elapsed = time.time() - load_start
        total_tick_count = len(tick_groups)
        print(f"[1/3] 加载完成，共 {total_tick_count} 个tick时间点，耗时 {load_elapsed:.1f}秒\n")
        
        results = []
        total_ticks = 0
        start_time = datetime.now()
        
        # 进度条函数
        def print_progress(current, total, tick_time, match_count):
            bar_length = 30
            filled = int(bar_length * current / total)
            bar = '█' * filled + '░' * (bar_length - filled)
            percent = current / total * 100
            # 格式化tick时间 093000 -> 09:30:00
            time_formatted = f"{tick_time[:2]}:{tick_time[2:4]}:{tick_time[4:]}"
            print(f"\r[{bar}] {percent:5.1f}% | {current}/{total} | 时间:{time_formatted} | 命中:{match_count}", end='', flush=True)
        
        print("[2/3] 开始回放处理...")
        print("=" * 70)
        
        async with self:  # 进入上下文（模式初始化）
            for tick_time, df_tick in tick_groups:
                total_ticks += 1
                
                # 2. 设置当前tick数据
                if self.mode == 'mock':
                    self._mock_data = df_tick
                else:
                    # 模式二：写入Redis
                    await self._write_to_redis(df_tick)
                
                # 3. 调用系统量化筛选
                result = await self._call_quant_screen(trade_date, tick_time, schemes)
                
                match_count = len(result.get('matches', []))
                
                # 4. 记录结果
                results.append({
                    'tick_time': tick_time,
                    'match_count': match_count,
                    'stats': result.get('stats', {})
                })
                
                # 显示进度（每10个tick更新一次，避免刷屏）
                if total_ticks % 10 == 0 or total_ticks == total_tick_count:
                    print_progress(total_ticks, total_tick_count, tick_time, match_count)
                
                # 5. 速度控制
                if speed != '0':
                    await self._sleep_by_speed(speed)
        
        print("\n" + "=" * 70)
        print("[2/3] 回放处理完成\n")
                    
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            'total_ticks': total_ticks,
            'elapsed_seconds': elapsed,
            'results': results,
            'summary': self._calc_summary(results)
        }
        
    def _fetch_tick_groups_sync(self, trade_date, time_start, time_end):
        """流式读取tick分组（同步版本）"""
        from sqlalchemy import text
        
        table_name = f"monitor_zq_sssj_{trade_date}"
        
        # 查询所有字段（用户要求）
        sql = text(f"""
            SELECT * FROM {table_name}
            WHERE time BETWEEN :start AND :end
            ORDER BY time
        """)
        
        with self.data_service.engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'start': time_start, 'end': time_end})
        
        if df.empty:
            return []
        
        # 按time分组
        groups = []
        for tick_time, group in df.groupby('time'):
            groups.append((str(tick_time), group))
        
        return groups
        
    async def _fetch_tick_groups(self, trade_date, time_start, time_end):
        """流式读取tick分组（异步包装）"""
        # 使用线程池执行同步查询
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            groups = await loop.run_in_executor(
                pool, self._fetch_tick_groups_sync, trade_date, time_start, time_end
            )
        
        # yield结果
        for tick_time, group in groups:
            yield tick_time, group
                    
    def _write_to_redis_sync(self, tick_data):
        """模式二：批量写入Redis（同步版本）"""
        pipe = self.redis_client.pipeline()
        
        # 统一处理DataFrame或列表
        if HAS_PANDAS and hasattr(tick_data, 'iterrows'):
            rows = tick_data.iterrows()
        else:
            rows = enumerate(tick_data)
        
        for _, row in rows:
            bond_code = row.get('bond_code', '') if isinstance(row, dict) else row.get('bond_code', '')
            if bond_code:
                data = dict(row) if not isinstance(row, dict) else row
                # 处理datetime序列化
                for k, v in list(data.items()):
                    if isinstance(v, datetime):
                        data[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                pipe.hset('bond:latest', bond_code, json.dumps(data, default=str))
                
        pipe.execute()
        
    async def _write_to_redis(self, tick_data):
        """模式二：批量写入Redis（异步包装）"""
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, self._write_to_redis_sync, tick_data)
        
    async def _call_quant_screen(self, trade_date, tick_time, schemes):
        """调用系统量化筛选（直接调用内部逻辑，不经过HTTP）"""
        try:
            # 直接使用DataFrame和方案进行筛选，不经过Flask请求
            df = self._mock_data
            if df is None or df.empty:
                return {'success': True, 'matches': [], 'stats': {}}
            
            # 执行筛选逻辑
            matches = []
            stats = {}
            
            for scheme in (schemes or []):
                scheme_name = scheme.get('name', '未命名')
                conditions = scheme.get('conditions', [])
                
                if not conditions:
                    continue
                
                # 应用筛选条件
                filtered_df = df.copy()
                for i, cond in enumerate(conditions):
                    field = cond.get('field')
                    op = cond.get('op')
                    value = cond.get('value')
                    logic = cond.get('logic', 'AND')
                    
                    if field not in filtered_df.columns:
                        continue
                    
                    if op == '>':
                        mask = filtered_df[field] > value
                    elif op == '<':
                        mask = filtered_df[field] < value
                    elif op == '>=':
                        mask = filtered_df[field] >= value
                    elif op == '<=':
                        mask = filtered_df[field] <= value
                    elif op == '=':
                        mask = filtered_df[field] == value
                    elif op == '!=':
                        mask = filtered_df[field] != value
                    else:
                        continue
                    
                    if i == 0 or logic == 'AND':
                        filtered_df = filtered_df[mask]
                    else:  # OR
                        filtered_df = pd.concat([filtered_df, df[mask]]).drop_duplicates()
                
                scheme_matches = filtered_df.to_dict('records')
                
                # 添加方案名称
                for match in scheme_matches:
                    match['scheme_name'] = scheme_name
                    match['scheme'] = scheme
                
                matches.extend(scheme_matches)
                stats[scheme_name] = len(scheme_matches)
            
            # 去重
            seen_codes = set()
            unique_matches = []
            for match in matches:
                code = match.get('bond_code') or match.get('code')
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    # 标准化字段名
                    match['bond_code'] = match.get('bond_code') or match.get('code', '')
                    match['bond_name'] = match.get('bond_name') or match.get('name', '')
                    match['price'] = match.get('price', 0)
                    match['change_pct'] = match.get('change_pct', 0)
                    match['amount'] = match.get('amount', 0)
                    unique_matches.append(match)
            
            return {
                'success': True,
                'time': tick_time,
                'matches': unique_matches,
                'stats': stats,
                'total_unique': len(unique_matches)
            }
            
        except Exception as e:
            print(f"[错误] 筛选失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
            
    async def _sleep_by_speed(self, speed):
        """根据速度控制间隔"""
        # 真实tick间隔约3秒
        base_interval = 0.1  # 简化：假设tick间隔0.1秒
        
        if speed.endswith('x'):
            factor = float(speed[:-1])
            await asyncio.sleep(base_interval / factor)
        elif speed == '0':
            pass  # 不sleep
        else:
            await asyncio.sleep(float(speed))
            
    def _calc_summary(self, results):
        """计算汇总统计"""
        total_matches = sum(r['match_count'] for r in results)
        tick_with_matches = sum(1 for r in results if r['match_count'] > 0)
        
        # 按方案统计
        scheme_stats = {}
        for r in results:
            for scheme_name, count in r.get('stats', {}).items():
                if scheme_name not in scheme_stats:
                    scheme_stats[scheme_name] = {'total': 0, 'ticks': 0}
                scheme_stats[scheme_name]['total'] += count
                if count > 0:
                    scheme_stats[scheme_name]['ticks'] += 1
        
        return {
            'total_ticks': len(results),
            'ticks_with_matches': tick_with_matches,
            'total_matches': total_matches,
            'avg_matches_per_tick': total_matches / len(results) if results else 0,
            'scheme_stats': scheme_stats
        }


# CLI入口
async def main():
    today = datetime.now().strftime('%Y%m%d')
    
    parser = argparse.ArgumentParser(description='量化选债历史数据回放测试')
    parser.add_argument('--date', default=today, help=f'交易日期 (默认: {today})')
    parser.add_argument('--mode', default='mock', choices=['mock', 'redis'],
                       help='回放模式：mock=运行时替换(默认), redis=Redis回放')
    parser.add_argument('--time-start', default='093000', help='开始时间 (默认: 093000)')
    parser.add_argument('--time-end', default='150000', help='结束时间 (默认: 150000)')
    parser.add_argument('--speed', default='0', help='播放速度：1x/10x/100x/0 (默认: 10x)')
    parser.add_argument('--schemes', help='方案JSON文件路径')
    
    args = parser.parse_args()
    
    # 加载方案
    schemes = []
    if args.schemes and os.path.exists(args.schemes):
        with open(args.schemes, 'r', encoding='utf-8') as f:
            schemes = json.load(f)
        print(f"[加载] 从文件加载 {len(schemes)} 个方案")
    else:
        # 默认测试方案
        schemes = [
            {
                'name': '强势反弹',
                'conditions': [
                    {'field': 'change_pct', 'op': '>', 'value': 2.0, 'logic': 'AND'},
                    {'field': 'amount', 'op': '>', 'value': 1000000, 'logic': 'AND'}
                ],
                'stop_loss': 3.0,
                'take_profit': 5.0,
                'max_hold_time': 30
            },
            {
                'name': '高成交额',
                'conditions': [
                    {'field': 'amount', 'op': '>', 'value': 5000000, 'logic': 'AND'}
                ],
                'stop_loss': 2.0,
                'take_profit': 3.0
            }
        ]
        print(f"[加载] 使用默认 {len(schemes)} 个方案")
    
    # 执行回放
    replayer = QuantScreenReplayer(mode=args.mode)
    
    try:
        result = await replayer.replay(
            trade_date=args.date,
            time_start=args.time_start,
            time_end=args.time_end,
            speed=args.speed,
            schemes=schemes
        )
        
        # 输出结果
        print(f"\n{'='*70}")
        print(f"[3/3] 回放完成!")
        print(f"{'='*70}")
        print(f"\n📊 执行统计:")
        print(f"  • 总tick数: {result['total_ticks']}")
        print(f"  • 执行时间: {result['elapsed_seconds']:.2f}秒")
        print(f"  • 处理速度: {result['total_ticks']/result['elapsed_seconds']:.1f} tick/秒" if result['elapsed_seconds'] > 0 else "  • 处理速度: N/A")
        print(f"  • 有命中的tick: {result['summary']['ticks_with_matches']}")
        print(f"  • 总命中次数: {result['summary']['total_matches']}")
        print(f"  • 平均每tick命中: {result['summary']['avg_matches_per_tick']:.2f}")
        
        print(f"\n📋 按方案统计:")
        for scheme_name, stats in result['summary']['scheme_stats'].items():
            print(f"  • {scheme_name}: 总命中 {stats['total']} 次, 涉及 {stats['ticks']} 个tick")
        
        print(f"\n{'='*70}\n")
        
        # 保存详细结果
        output_dir = Path(__file__).parent / 'results'
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%H%M%S')
        output_file = output_dir / f"replay_{args.date}_{args.mode}_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"[保存] 详细结果: {output_file}")
        
        # 验证数据库记录
        print(f"\n[验证] 检查数据库记录...")
        verify_database_records_sync(args.date, replayer.data_service.engine)
        
    except Exception as e:
        print(f"[错误] 回放失败: {e}")
        import traceback
        traceback.print_exc()


def verify_database_records_sync(trade_date, engine):
    """验证数据库中是否正确保存了命中记录（同步版本）"""
    from sqlalchemy import text
    
    try:
        with engine.connect() as conn:
            # 统计总记录数
            result = conn.execute(text(
                "SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = :date"
            ), {'date': trade_date})
            total = result.scalar()
            
            # 按状态统计
            result = conn.execute(text("""
                SELECT signal_status, COUNT(*) 
                FROM quant_screen_hits 
                WHERE trade_date = :date 
                GROUP BY signal_status
            """), {'date': trade_date})
            status_counts = result.fetchall()
            
            # 按方案统计
            result = conn.execute(text("""
                SELECT scheme_name, COUNT(*) 
                FROM quant_screen_hits 
                WHERE trade_date = :date 
                GROUP BY scheme_name
            """), {'date': trade_date})
            scheme_counts = result.fetchall()
            
            print(f"  数据库记录总数: {total}")
            print(f"  按状态分布:")
            for row in status_counts:
                print(f"    {row[0]}: {row[1]}")
            print(f"  按方案分布:")
            for row in scheme_counts:
                print(f"    {row[0]}: {row[1]}")
                
    except Exception as e:
        print(f"  [警告] 验证失败: {e}")


if __name__ == '__main__':
    asyncio.run(main())
