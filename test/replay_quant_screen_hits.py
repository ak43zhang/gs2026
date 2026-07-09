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

import aiomysql

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


async def ensure_table_exists(pool):
    """确保quant_screen_hits表存在，不存在则自动创建"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 检查表是否存在
            await cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = DATABASE() AND table_name = 'quant_screen_hits'
            """)
            result = await cur.fetchone()
            
            if result[0] == 0:
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
                                await cur.execute(stmt)
                            except Exception as e:
                                print(f"[警告] 执行SQL失败: {e}")
                    await conn.commit()
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
            self.redis_client = await self.data_service._get_redis()
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
        
        # 0. 确保表存在
        pool = await self.data_service._get_mysql_pool()
        await ensure_table_exists(pool)
        
        # 1. 流式读取tick分组
        tick_groups = await self._fetch_tick_groups(trade_date, time_start, time_end)
        
        results = []
        total_ticks = 0
        start_time = datetime.now()
        
        async with self:  # 进入上下文（模式初始化）
            for tick_time, df_tick in tick_groups:
                total_ticks += 1
                
                if total_ticks % 100 == 0:
                    print(f"[进度] 处理第 {total_ticks} 个tick: {tick_time}")
                
                # 2. 设置当前tick数据
                if self.mode == 'mock':
                    self._mock_data = df_tick
                else:
                    # 模式二：写入Redis
                    await self._write_to_redis(df_tick)
                
                # 3. 调用系统量化筛选
                result = await self._call_quant_screen(trade_date, tick_time, schemes)
                
                # 4. 记录结果
                results.append({
                    'tick_time': tick_time,
                    'match_count': len(result.get('matches', [])),
                    'stats': result.get('stats', {})
                })
                
                # 5. 速度控制
                if speed != '0':
                    await self._sleep_by_speed(speed)
                    
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            'total_ticks': total_ticks,
            'elapsed_seconds': elapsed,
            'results': results,
            'summary': self._calc_summary(results)
        }
        
    async def _fetch_tick_groups(self, trade_date, time_start, time_end):
        """流式读取tick分组（generator）"""
        pool = await self.data_service._get_mysql_pool()
        
        table_name = f"monitor_zq_sssj_{trade_date}"
        
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                sql = f"""
                    SELECT * FROM {table_name}
                    WHERE time BETWEEN %s AND %s
                    ORDER BY time
                """
                await cur.execute(sql, (time_start, time_end))
                
                # 按time分组yield
                current_time = None
                current_rows = []
                
                async for row in cur:
                    row_time = str(row['time'])
                    if row_time != current_time:
                        if current_rows:
                            if HAS_PANDAS:
                                yield current_time, pd.DataFrame(current_rows)
                            else:
                                yield current_time, current_rows  # 返回列表
                        current_time = row_time
                        current_rows = []
                    current_rows.append(dict(row))
                    
                if current_rows:
                    if HAS_PANDAS:
                        yield current_time, pd.DataFrame(current_rows)
                    else:
                        yield current_time, current_rows
                    
    async def _write_to_redis(self, tick_data):
        """模式二：批量写入Redis"""
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
                
        await pipe.execute()
        
    async def _call_quant_screen(self, trade_date, tick_time, schemes):
        """调用系统量化筛选"""
        from flask import Flask, request
        import flask
        
        app = Flask(__name__)
        
        # 构造请求数据
        request_data = {
            'date': trade_date,
            'schemes': schemes or []
        }
        
        # 创建模拟请求上下文
        with app.test_request_context(
            path='/api/monitor/quant-screen',
            method='POST',
            data=json.dumps(request_data),
            content_type='application/json'
        ):
            # 手动设置request.json
            flask.request._cached_json = request_data
            
            # 调用系统函数
            try:
                # 检查quant_screen是否为异步函数
                import inspect
                if inspect.iscoroutinefunction(monitor.quant_screen):
                    result = await monitor.quant_screen()
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
    parser.add_argument('--speed', default='10x', help='播放速度：1x/10x/100x/0 (默认: 10x)')
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
        print(f"\n{'='*60}")
        print(f"回放完成!")
        print(f"{'='*60}")
        print(f"总tick数: {result['total_ticks']}")
        print(f"执行时间: {result['elapsed_seconds']:.2f}秒")
        print(f"有命中的tick: {result['summary']['ticks_with_matches']}")
        print(f"总命中次数: {result['summary']['total_matches']}")
        print(f"平均每tick命中: {result['summary']['avg_matches_per_tick']:.2f}")
        
        print(f"\n按方案统计:")
        for scheme_name, stats in result['summary']['scheme_stats'].items():
            print(f"  {scheme_name}: 总命中 {stats['total']}, 涉及 {stats['ticks']} 个tick")
        
        print(f"{'='*60}\n")
        
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
        await verify_database_records(args.date)
        
    except Exception as e:
        print(f"[错误] 回放失败: {e}")
        import traceback
        traceback.print_exc()


async def verify_database_records(trade_date):
    """验证数据库中是否正确保存了命中记录"""
    try:
        data_service = DataService()
        pool = await data_service._get_mysql_pool()
        
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 统计总记录数
                await cur.execute(
                    "SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = %s",
                    (trade_date,)
                )
                total = await cur.fetchone()
                
                # 按状态统计
                await cur.execute("""
                    SELECT signal_status, COUNT(*) 
                    FROM quant_screen_hits 
                    WHERE trade_date = %s 
                    GROUP BY signal_status
                """, (trade_date,))
                status_counts = await cur.fetchall()
                
                # 按方案统计
                await cur.execute("""
                    SELECT scheme_name, COUNT(*) 
                    FROM quant_screen_hits 
                    WHERE trade_date = %s 
                    GROUP BY scheme_name
                """, (trade_date,))
                scheme_counts = await cur.fetchall()
                
                print(f"  数据库记录总数: {total[0]}")
                print(f"  按状态分布:")
                for status, count in status_counts:
                    print(f"    {status}: {count}")
                print(f"  按方案分布:")
                for scheme, count in scheme_counts:
                    print(f"    {scheme}: {count}")
                    
    except Exception as e:
        print(f"  [警告] 验证失败: {e}")


if __name__ == '__main__':
    asyncio.run(main())
