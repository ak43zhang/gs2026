"""
买点候选回溯工作器
完整重新计算历史买点候选，支持异步执行、实时进度、整库替换
"""
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from dataclasses import dataclass, field


@dataclass
class BacktestTask:
    """回溯任务状态"""
    task_id: str
    start_date: str
    end_date: str
    conditions: Dict
    status: str = 'pending'
    progress: float = 0.0
    current_date: str = ''
    current_time: str = ''
    total_points: int = 0
    processed_points: int = 0
    total_candidates: int = 0
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    completed_at: Optional[str] = None


class BacktestTaskManager:
    """回溯任务管理器（单例）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.tasks: Dict[str, BacktestTask] = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='backtest')

    def query_timepoints(self, start_date: str, end_date: str) -> Dict:
        """查询日期范围内每天的时间点数量"""
        from gs2026.dashboard.services.data_service import DataService
        ds = DataService()

        dates_info = {}
        total_points = 0

        # 遍历日期范围
        current = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')

        while current <= end:
            date_str = current.strftime('%Y%m%d')
            # 跳过周末
            if current.weekday() < 5:
                timestamps = ds.get_timestamps(date=date_str, use_mysql=True)
                if timestamps and len(timestamps) > 0:
                    dates_info[date_str] = {
                        'count': len(timestamps),
                        'first': timestamps[0] if timestamps else '',
                        'last': timestamps[-1] if timestamps else ''
                    }
                    total_points += len(timestamps)
            current += timedelta(days=1)

        return {
            'dates': dates_info,
            'total_points': total_points,
            'total_days': len(dates_info)
        }

    def submit(self, start_date: str, end_date: str, conditions: Dict) -> str:
        """提交回溯任务"""
        task_id = str(uuid.uuid4())[:8]
        task = BacktestTask(
            task_id=task_id,
            start_date=start_date,
            end_date=end_date,
            conditions=conditions
        )
        self.tasks[task_id] = task

        self.executor.submit(self._run_backtest, task)
        task.status = 'running'

        return task_id

    def get_status(self, task_id: str) -> Optional[BacktestTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    # ==================== 核心回溯逻辑 ====================

    def _run_backtest(self, task: BacktestTask):
        """执行回溯（在后台线程中运行）"""
        try:
            from gs2026.dashboard.services.data_service import DataService
            from gs2026.dashboard2.routes.monitor import (
                _get_shared_engine, _enrich_stock_data,
                _enrich_change_pct_and_main_net, data_service
            )
            from sqlalchemy import text

            engine = _get_shared_engine()

            # 1. 获取所有日期和时间点
            timepoints_info = self.query_timepoints(task.start_date, task.end_date)
            dates_info = timepoints_info['dates']
            task.total_points = timepoints_info['total_points']

            if task.total_points == 0:
                task.status = 'completed'
                task.completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                return

            # 2. 创建临时表
            temp_table = f"temp_bt_{task.task_id.replace('-', '_')}"
            self._create_temp_table(engine, temp_table)

            # 3. 遍历每个日期（使用并行线程池处理时间点）
            all_dates = sorted(dates_info.keys())
            tp_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='backtest_tp')

            for date_str in all_dates:
                task.current_date = date_str

                # 预加载该日期的绿名单和红名单
                self._preload_caches(date_str)

                # 获取该日期的时间点列表
                timestamps = data_service.get_timestamps(date=date_str, use_mysql=True)

                if not timestamps:
                    continue

                # 【并行】提交所有时间点任务
                futures = {}
                for time_str in timestamps:
                    futures[tp_executor.submit(
                        self._process_timepoint,
                        date_str, time_str, task.conditions, data_service
                    )] = time_str

                # 【并行】收集结果并批量保存
                day_candidates = 0
                for future in futures:
                    try:
                        candidates, market_ctx = future.result(timeout=60)

                        # 保存到临时表（批量）
                        if candidates:
                            self._save_batch(engine, temp_table, date_str,
                                             futures[future], candidates, market_ctx)
                            day_candidates += len(candidates)

                    except Exception as e:
                        print(f"[BACKTEST] 时间点处理失败 {date_str} {futures[future]}: {e}")

                    task.processed_points += 1
                    task.progress = task.processed_points / task.total_points

                task.total_candidates += day_candidates

            tp_executor.shutdown(wait=True)

            # 4. 事务替换
            self._replace_data(engine, all_dates, temp_table)

            # 5. 完成
            task.status = 'completed'
            task.completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            import traceback
            traceback.print_exc()

    def _process_timepoint(self, date: str, time_str: str, conditions: Dict,
                           ds) -> tuple:
        """处理单个时间点（批量获取 + 批量评估）"""
        from gs2026.dashboard2.routes.monitor import (
            _enrich_stock_data, _enrich_change_pct_and_main_net,
            _enrich_bond_data
        )

        # 1. 批量获取排行数据（每个只需1次查询）
        stock_ranking = ds.get_ranking_at_time('stock', limit=200, date=date, time_str=time_str)
        bond_ranking = ds.get_ranking_at_time('bond', limit=100, date=date, time_str=time_str)
        industry_ranking = ds.get_ranking_at_time('industry', limit=30, date=date, time_str=time_str)

        if not stock_ranking:
            return [], {}

        # 2. 批量enrichment（复用现有函数）
        stock_ranking = _enrich_stock_data(stock_ranking)
        stock_ranking = _enrich_change_pct_and_main_net(stock_ranking, date, time_str)

        # 【修复】为债券排行补充涨跌幅和价格
        bond_ranking = _enrich_bond_data(bond_ranking, date, time_str)

        # 3. 获取大盘数据
        market_data = ds.get_market_stats(date=date, use_mysql=True, time_str=time_str)

        # 4. 构建上下文
        bond_set = set(b['code'] for b in bond_ranking if b.get('code'))
        bond_map = {b['code']: b for b in bond_ranking if b.get('code')}
        ind_top = int(conditions.get('ind_top', 10))
        top_ind = set(i['name'] for i in industry_ranking[:ind_top] if i.get('name'))
        ctx = {'bondSet': bond_set, 'bondMap': bond_map, 'topInd': top_ind}

        # 5. 评估大盘条件
        mkt_conds, mkt_pass, critical_hit = self._evaluate_market(market_data, conditions)

        # 6. 评估所有股票（纯内存）
        candidates = self._evaluate_all_stocks(stock_ranking, conditions, ctx, bond_map)

        # 6.5 设置星星颜色：关键大盘条件命中则红色，否则黄色
        star_color = 'red' if critical_hit else 'yellow'
        for c in candidates:
            c['starColor'] = star_color

        # 7. 组装大盘上下文
        market_ctx = {
            'conditions': mkt_conds,
            'passed': mkt_pass,
            'total': len(mkt_conds),
            'criticalHit': critical_hit,
            'signal': '积极' if mkt_pass >= len(mkt_conds) else '谨慎' if len(mkt_conds) > 0 and mkt_pass >= len(mkt_conds) * 0.5 else '观望'
        }

        return candidates, market_ctx

    def _evaluate_market(self, mkt: Dict, conditions: Dict) -> tuple:
        """评估大盘条件（复刻前端逻辑，含关键模式追踪）
        
        星星颜色规则：所有 critical 条件都通过才标红，否则标黄
        """
        mkt_conds = []
        mkt_pass = 0
        has_critical = False
        all_critical_passed = True

        market_defs = self._get_market_conditions()
        for cond in market_defs:
            if not conditions.get(f'_on_{cond["id"]}', False):
                continue
            p = float(conditions.get(cond.get('param', ''), cond.get('def', 0))) if cond.get('param') else 0
            ok = False
            try:
                ok = cond['fn'](mkt, p)
            except Exception:
                pass
            mkt_conds.append({'name': cond['name'], 'passed': ok})
            if ok:
                mkt_pass += 1
            mode = conditions.get(f'_mode_{cond["id"]}', 'normal')
            if mode == 'critical':
                has_critical = True
                if not ok:
                    all_critical_passed = False

        critical_hit = has_critical and all_critical_passed
        return mkt_conds, mkt_pass, critical_hit

    def _evaluate_all_stocks(self, stocks: list, conditions: Dict, ctx: Dict,
                             bond_map: Dict) -> list:
        """批量评估所有股票（纯内存计算）"""
        stock_link_defs = self._get_stock_conditions() + self._get_link_conditions()

        required = [c for c in stock_link_defs
                    if conditions.get(f'_on_{c["id"]}', False) and
                    conditions.get(f'_mode_{c["id"]}', c.get('mode', 'required')) == 'required']
        bonus = [c for c in stock_link_defs
                 if conditions.get(f'_on_{c["id"]}', False) and
                 conditions.get(f'_mode_{c["id"]}', c.get('mode', 'required')) == 'bonus']

        if not required and not bonus:
            return []

        candidates = []
        for stock in stocks:
            # 必要条件
            pass_all = True
            tags = []
            for cond in required:
                p = float(conditions.get(cond.get('param', ''), cond.get('def', 0))) if cond.get('param') else 0
                ok = False
                try:
                    ok = cond['fn'](stock, p, ctx)
                except Exception:
                    pass
                if not ok:
                    pass_all = False
                    break
                tags.append(cond['name'])

            if not pass_all:
                continue

            # 加分条件
            bonus_hit = 0
            for cond in bonus:
                p = float(conditions.get(cond.get('param', ''), cond.get('def', 0))) if cond.get('param') else 0
                ok = False
                try:
                    ok = cond['fn'](stock, p, ctx)
                except Exception:
                    pass
                if ok:
                    bonus_hit += 1
                    tags.append(cond['name'])

            level = 1 + min(bonus_hit, 2)
            bond = bond_map.get(stock.get('bond_code'))

            candidates.append({
                'code': stock.get('code', ''),
                'name': stock.get('name', ''),
                'price': stock.get('price'),
                'change_pct': stock.get('change_pct'),
                'bond_code': stock.get('bond_code', '-'),
                'bond_name': stock.get('bond_name', '-'),
                'bond_price': bond.get('price') if bond else None,
                'bond_chg': bond.get('change_pct') if bond else None,
                'score': len([c for c in required if conditions.get(f'_on_{c["id"]}', False)]) + bonus_hit,
                'tags': tags,
                'level': level
            })

        candidates.sort(key=lambda x: (-x['level'], -x['score']))
        return candidates[:30]

    # ==================== 条件定义（复刻前端） ====================

    def _get_market_conditions(self) -> list:
        """大盘条件（与前端 BP_CONDITIONS type=market 完全对应）"""
        def _safe_div(a, b):
            return a / b if b and b > 0 else 0

        return [
            {'id': 'body_gt_cur', 'name': '股票红柱>涨家数',
             'fn': lambda m, p: float(m.get('stock', {}).get('body_up', 0) or 0) > float(m.get('stock', {}).get('cur_up', 0) or 0)},
            {'id': 'tick_ratio', 'name': '股票tick比', 'param': 'tick_min', 'def': 1.0,
             'fn': lambda m, p: _safe_div(float(m.get('stock', {}).get('min_up', 0) or 0), float(m.get('stock', {}).get('min_down', 0) or 0)) > p},
            {'id': 'strength', 'name': '股票强度', 'param': 'str_min', 'def': 50,
             'fn': lambda m, p: float(m.get('stock', {}).get('strength_score', 0) or 0) > p},
            {'id': 'bond_body_gt_cur', 'name': '债券红柱>涨家数',
             'fn': lambda m, p: float(m.get('bond', {}).get('body_up', 0) or 0) > float(m.get('bond', {}).get('cur_up', 0) or 0)},
            {'id': 'bond_tick_ratio', 'name': '债券tick比', 'param': 'btick_min', 'def': 1.0,
             'fn': lambda m, p: _safe_div(float(m.get('bond', {}).get('min_up', 0) or 0), float(m.get('bond', {}).get('min_down', 0) or 0)) > p},
            {'id': 'stock_ud_ratio', 'name': '股票涨跌比', 'param': 'sud_min', 'def': 0.8,
             'fn': lambda m, p: _safe_div(float(m.get('stock', {}).get('cur_up', 0) or 0), float(m.get('stock', {}).get('cur_down', 0) or 0)) > p},
            {'id': 'stock_body_ratio', 'name': '股票红绿柱比', 'param': 'sbody_min', 'def': 0.8,
             'fn': lambda m, p: _safe_div(float(m.get('stock', {}).get('body_up', 0) or 0), float(m.get('stock', {}).get('body_down', 0) or 0)) > p},
            {'id': 'bond_ud_ratio', 'name': '债券涨跌比', 'param': 'bud_min', 'def': 0.8,
             'fn': lambda m, p: _safe_div(float(m.get('bond', {}).get('cur_up', 0) or 0), float(m.get('bond', {}).get('cur_down', 0) or 0)) > p},
            {'id': 'bond_body_ratio', 'name': '债券红绿柱比', 'param': 'bbody_min', 'def': 0.8,
             'fn': lambda m, p: _safe_div(float(m.get('bond', {}).get('body_up', 0) or 0), float(m.get('bond', {}).get('body_down', 0) or 0)) > p},
        ]

    def _get_stock_conditions(self) -> list:
        """个股条件（与前端 BP_CONDITIONS type=stock 完全对应）"""
        return [
            {'id': 'net_ratio', 'mode': 'required', 'name': '主力/峰值', 'param': 'net_min', 'def': 0.9,
             'fn': lambda r, p, ctx: (float(r.get('cumulative_main_net', 0) or 0) / float(r.get('max_cumulative_main_net', 1) or 1) > p) if float(r.get('max_cumulative_main_net', 0) or 0) > 0 else False},
            {'id': 'change_pct', 'mode': 'required', 'name': '涨幅%', 'param': 'chg_min', 'def': 2,
             'fn': lambda r, p, ctx: float(r.get('change_pct', 0) or 0) > p},
            {'id': 'in_top_ind', 'mode': 'bonus', 'name': '行业前N', 'param': 'ind_top', 'def': 10,
             'fn': lambda r, p, ctx: r.get('industry_name') in ctx['topInd']},
            {'id': 'consec_attack', 'mode': 'required', 'name': '连续上攻>0',
             'fn': lambda r, p, ctx: int(r.get('consecutive_attacks', 0) or 0) > 0},
        ]

    def _get_link_conditions(self) -> list:
        """联动条件（与前端 BP_CONDITIONS type=link 完全对应）"""
        return [
            {'id': 'bond_in_rank', 'mode': 'bonus', 'name': '债券在排行',
             'fn': lambda r, p, ctx: r.get('bond_code') and r.get('bond_code') != '-' and r.get('bond_code') in ctx['bondSet']},
            {'id': 'bond_chg', 'mode': 'bonus', 'name': '债券涨幅', 'param': 'bchg_min', 'def': 2,
             'fn': lambda r, p, ctx: float((ctx['bondMap'].get(r.get('bond_code')) or {}).get('change_pct', 0) or 0) > p},
            {'id': 'green_bond_in', 'mode': 'required', 'name': '绿名单(内)',
             'fn': lambda r, p, ctx: r.get('bond_code') and r.get('bond_code') != '-' and r.get('is_green_bond') is True},
            {'id': 'green_bond_out', 'mode': 'required', 'name': '绿名单(外)',
             'fn': lambda r, p, ctx: r.get('bond_code') and r.get('bond_code') != '-' and r.get('is_green_bond') is not True},
        ]

    # ==================== 数据库操作 ====================

    def _preload_caches(self, date_str: str):
        """预加载指定日期的绿名单和红名单缓存"""
        try:
            from gs2026.dashboard2.routes.green_bond_list_cache import update_green_bond_list_cache
            update_green_bond_list_cache(date_str)
        except Exception as e:
            print(f"[BACKTEST] 预加载绿名单失败 {date_str}: {e}")

        try:
            from gs2026.dashboard2.routes.red_list_cache import update_red_list_cache
            update_red_list_cache(date_str)
        except Exception as e:
            print(f"[BACKTEST] 预加载红名单失败 {date_str}: {e}")

    def _create_temp_table(self, engine, temp_table: str):
        """创建临时表（与 buy_point_candidates 结构一致）"""
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
            conn.execute(text(f"""
                CREATE TABLE {temp_table} (
                    record_id VARCHAR(32) PRIMARY KEY,
                    date DATE,
                    time TIME,
                    stock_code VARCHAR(10),
                    stock_name VARCHAR(50),
                    stock_price DECIMAL(10,2),
                    stock_change_pct DECIMAL(6,2),
                    bond_code VARCHAR(10),
                    bond_price DECIMAL(10,3),
                    bond_change_pct DECIMAL(6,2),
                    level TINYINT,
                    star_color VARCHAR(10) DEFAULT 'yellow',
                    condition_count INT,
                    total_conditions INT,
                    conditions JSON,
                    market_context JSON,
                    INDEX idx_date_time (date, time)
                )
            """))
            conn.commit()

    def _save_batch(self, engine, temp_table: str, date: str, time_str: str,
                    candidates: list, market_ctx: Dict):
        """批量保存到临时表（executemany优化）"""
        from sqlalchemy import text

        save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        market_json = json.dumps(market_ctx, ensure_ascii=False, default=str)

        rows = []
        for c in candidates:
            record_id = hashlib.md5(f"{c['code']}{save_date}{time_str}".encode()).hexdigest()
            tags = c.get('tags', [])
            rows.append({
                'rid': record_id, 'd': save_date, 't': time_str,
                'sc': c['code'], 'sn': c.get('name', ''),
                'sp': c.get('price'), 'scp': c.get('change_pct'),
                'bc': c.get('bond_code', ''), 'bp': c.get('bond_price'),
                'bcp': c.get('bond_chg'),
                'lv': c['level'], 'stc': c.get('starColor', 'yellow'),
                'cc': len(tags), 'tc': len(tags),
                'cd': json.dumps([{'name': t, 'passed': True} for t in tags], ensure_ascii=False),
                'mc': market_json
            })

        if rows:
            with engine.connect() as conn:
                conn.execute(text(f"""
                    INSERT IGNORE INTO {temp_table}
                    (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
                     bond_code, bond_price, bond_change_pct, level, star_color, condition_count, total_conditions,
                     conditions, market_context)
                    VALUES (:rid, :d, :t, :sc, :sn, :sp, :scp, :bc, :bp, :bcp, :lv, :stc, :cc, :tc, :cd, :mc)
                """), rows)
                conn.commit()

    def _replace_data(self, engine, dates: list, temp_table: str):
        """事务替换：删除旧数据 -> 插入新数据"""
        from sqlalchemy import text

        with engine.begin() as conn:
            for date in dates:
                save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                conn.execute(text("DELETE FROM buy_point_candidates WHERE date = :d"), {'d': save_date})

            # 显式指定列名，避免表结构不一致
            conn.execute(text(f"""
                INSERT INTO buy_point_candidates 
                (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
                 bond_code, bond_price, bond_change_pct, level, star_color, condition_count, total_conditions,
                 conditions, market_context)
                SELECT record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
                       bond_code, bond_price, bond_change_pct, level, star_color, condition_count, total_conditions,
                       conditions, market_context
                FROM {temp_table}
            """))

        # 清理临时表
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
            conn.commit()


# 全局实例
task_manager = BacktestTaskManager()
