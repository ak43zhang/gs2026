"""
买点候选回溯工作器（性能优化版）
日级预加载模式：每天仅 ~6 次 MySQL 查询，其余纯内存计算
"""
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import pandas as pd
from dataclasses import dataclass, field

# 进度阶段权重
PHASE_LOAD = 0.3
PHASE_COMPUTE = 0.5
PHASE_SAVE = 0.2


@dataclass
class DayCache:
    """一天的预加载数据缓存"""
    date: str
    timestamps: list  # sorted list of time strings
    stock_top30: dict  # {time_str: [row_dicts]}
    bond_top30: dict   # {time_str: [row_dicts]}
    industry_top30: dict  # {time_str: [row_dicts]}
    stock_apqd: dict   # {time_str: row_dict}
    bond_apqd: dict    # {time_str: row_dict}
    stock_sssj: dict   # {(time_str, code): row_dict}
    bond_sssj: dict    # {(time_str, bond_code): row_dict}


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
    status_detail: str = ''
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
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='backtest')

    def query_timepoints(self, start_date: str, end_date: str) -> Dict:
        """查询日期范围内每天的时间点数量"""
        from gs2026.dashboard.services.data_service import DataService
        ds = DataService()
        dates_info = {}
        total_points = 0
        current = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        while current <= end:
            date_str = current.strftime('%Y%m%d')
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
        return {'dates': dates_info, 'total_points': total_points, 'total_days': len(dates_info)}

    def submit(self, start_date: str, end_date: str, conditions: Dict) -> str:
        """提交回溯任务"""
        task_id = str(uuid.uuid4())[:8]
        task = BacktestTask(
            task_id=task_id, start_date=start_date,
            end_date=end_date, conditions=conditions
        )
        self.tasks[task_id] = task
        self.executor.submit(self._run_backtest, task)
        task.status = 'running'
        return task_id

    def get_status(self, task_id: str) -> Optional[BacktestTask]:
        return self.tasks.get(task_id)

    # ==================== 核心回溯逻辑（优化版） ====================

    def _run_backtest(self, task: BacktestTask):
        """执行回溯（日级预加载模式）"""
        try:
            from gs2026.dashboard2.routes.monitor import (
                _get_shared_engine, _enrich_stock_data, data_service
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

            all_dates = sorted(dates_info.keys())
            total_days = len(all_dates)

            # 3. 遍历每个日期（日级预加载）
            for day_idx, date_str in enumerate(all_dates):
                task.current_date = date_str

                # 预加载绿/红名单
                self._preload_caches(date_str)

                # === 阶段1：预加载（30%） ===
                task.status_detail = '加载数据...'
                day_cache = self._preload_day_data(date_str, engine, data_service)
                task.progress = (day_idx + PHASE_LOAD) / total_days

                if not day_cache.timestamps:
                    task.processed_points += dates_info[date_str]['count']
                    task.progress = (day_idx + 1) / total_days
                    continue

                # === 阶段2：计算（50%） ===
                task.status_detail = '评估候选...'
                day_candidates = []
                ts_count = len(day_cache.timestamps)

                for tp_idx, time_str in enumerate(day_cache.timestamps):
                    try:
                        candidates, market_ctx = self._process_timepoint_fast(
                            day_cache, time_str, task.conditions
                        )
                        if candidates:
                            save_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            market_json = json.dumps(market_ctx, ensure_ascii=False, default=str)
                            for c in candidates:
                                day_candidates.append((save_date, time_str, c, market_json))
                    except Exception as e:
                        print(f"[BACKTEST] 时间点处理失败 {date_str} {time_str}: {e}")

                    task.processed_points += 1
                    if tp_idx % 50 == 0 or tp_idx == ts_count - 1:
                        compute_pct = (tp_idx + 1) / ts_count
                        task.progress = (day_idx + PHASE_LOAD + PHASE_COMPUTE * compute_pct) / total_days
                        task.current_time = time_str

                # === 阶段3：写入（20%） ===
                task.status_detail = '保存结果...'
                if day_candidates:
                    self._save_batch_bulk(engine, temp_table, day_candidates)
                task.total_candidates += len(day_candidates)
                task.progress = (day_idx + 1) / total_days

                # 释放内存
                del day_cache

            # 4. 事务替换
            task.status_detail = '替换数据...'
            self._replace_data(engine, all_dates, temp_table)

            # 5. 完成
            task.status = 'completed'
            task.status_detail = ''
            task.completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            import traceback
            traceback.print_exc()

    # ==================== 日级预加载 ====================

    def _preload_day_data(self, date_str: str, engine, ds) -> DayCache:
        """一次性加载全天数据到内存（~6次查询替代28000次）"""
        timestamps = ds.get_timestamps(date=date_str, use_mysql=True) or []

        stock_top30 = self._load_table_grouped(engine, f"monitor_gp_top30_{date_str}", 'time')
        bond_top30 = self._load_table_grouped(engine, f"monitor_zq_top30_{date_str}", 'time')
        industry_top30 = self._load_table_grouped(engine, f"monitor_hy_top30_{date_str}", 'time')
        stock_apqd = self._load_table_as_time_dict(engine, f"monitor_gp_apqd_{date_str}")
        bond_apqd = self._load_table_as_time_dict(engine, f"monitor_zq_apqd_{date_str}")

        # 提取排行中出现的所有代码
        stock_codes = set()
        bond_codes = set()
        for rows in stock_top30.values():
            for r in rows:
                code = r.get('stock_code') or r.get('code', '')
                if code:
                    stock_codes.add(str(code).zfill(6))
        for rows in bond_top30.values():
            for r in rows:
                code = r.get('bond_code') or r.get('code', '')
                if code:
                    bond_codes.add(str(code))

        # 批量加载 sssj（仅排行内的代码）
        stock_sssj = self._load_sssj_for_codes(
            engine, f"monitor_gp_sssj_{date_str}",
            'stock_code', stock_codes
        )
        bond_sssj = self._load_sssj_for_codes(
            engine, f"monitor_zq_sssj_{date_str}",
            'bond_code', bond_codes
        )

        print(f"[BACKTEST] 预加载 {date_str}: "
              f"stock_top30={sum(len(v) for v in stock_top30.values())}行, "
              f"bond_top30={sum(len(v) for v in bond_top30.values())}行, "
              f"stock_sssj={len(stock_sssj)}条, bond_sssj={len(bond_sssj)}条, "
              f"timestamps={len(timestamps)}")

        return DayCache(
            date=date_str, timestamps=timestamps,
            stock_top30=stock_top30, bond_top30=bond_top30,
            industry_top30=industry_top30,
            stock_apqd=stock_apqd, bond_apqd=bond_apqd,
            stock_sssj=stock_sssj, bond_sssj=bond_sssj
        )

    def _load_table_grouped(self, engine, table_name: str, group_col: str) -> dict:
        """加载整表并按 group_col 分组 → {time: [row_dicts]}"""
        try:
            with engine.connect() as conn:
                df = pd.read_sql(f"SELECT * FROM `{table_name}`", conn)
            if df.empty:
                return {}
            result = {}
            for time_val, group in df.groupby(group_col):
                key = str(time_val)
                result[key] = group.to_dict('records')
            return result
        except Exception:
            return {}

    def _load_table_as_time_dict(self, engine, table_name: str) -> dict:
        """加载整表 → {time: row_dict}（每个时间点一行）"""
        try:
            with engine.connect() as conn:
                df = pd.read_sql(f"SELECT * FROM `{table_name}`", conn)
            if df.empty:
                return {}
            result = {}
            for _, row in df.iterrows():
                key = str(row.get('time', ''))
                result[key] = row.to_dict()
            return result
        except Exception:
            return {}

    def _load_sssj_for_codes(self, engine, table_name: str,
                              code_col: str, codes: set) -> dict:
        """加载指定代码的 sssj 数据 → {(time, code): row_dict}"""
        if not codes:
            return {}
        try:
            codes_str = ','.join(f"'{c}'" for c in codes)
            with engine.connect() as conn:
                df = pd.read_sql(
                    f"SELECT * FROM `{table_name}` WHERE `{code_col}` IN ({codes_str})",
                    conn
                )
            if df.empty:
                return {}
            result = {}
            for _, row in df.iterrows():
                time_val = str(row.get('time', ''))
                code_val = str(row.get(code_col, ''))
                if code_col == 'stock_code':
                    code_val = code_val.zfill(6)
                result[(time_val, code_val)] = row.to_dict()
            return result
        except Exception as e:
            print(f"[BACKTEST] 加载 sssj 失败 {table_name}: {e}")
            return {}

    # ==================== 内存计算 ====================

    def _compute_ranking_at_time(self, day_cache: DayCache, asset_type: str,
                                  time_str: str) -> list:
        """从预加载数据计算截止 time_str 的累积排行"""
        if asset_type == 'stock':
            top30 = day_cache.stock_top30
            code_key = 'stock_code'
            name_key = 'stock_name'
        elif asset_type == 'bond':
            top30 = day_cache.bond_top30
            code_key = 'bond_code'
            name_key = 'bond_name'
        else:  # industry
            top30 = day_cache.industry_top30
            code_key = 'code'
            name_key = 'name'

        code_counts = {}
        code_names = {}
        for t in day_cache.timestamps:
            if t > time_str:
                break
            for row in top30.get(t, []):
                code = row.get(code_key) or row.get('code', '')
                if not code:
                    continue
                code_counts[code] = code_counts.get(code, 0) + 1
                code_names[code] = row.get(name_key) or row.get('name', '')

        sorted_items = sorted(code_counts.items(), key=lambda x: -x[1])
        return [
            {'code': str(code), 'name': code_names.get(code, ''),
             'count': count, 'rank': idx + 1, 'type': asset_type}
            for idx, (code, count) in enumerate(sorted_items)
        ]

    def _enrich_from_cache(self, stocks: list, day_cache: DayCache, time_str: str):
        """从缓存填充股票的 change_pct / 主力净额等字段"""
        for stock in stocks:
            code = str(stock.get('code', '')).zfill(6)
            sssj = day_cache.stock_sssj.get((time_str, code)) or {}
            stock['change_pct'] = sssj.get('change_pct', 0)
            stock['price'] = sssj.get('price', 0)
            stock['cumulative_main_net'] = sssj.get('cumulative_main_net', 0)
            stock['main_net_amount'] = sssj.get('main_net_amount', 0)
            stock['consecutive_attacks'] = sssj.get('consecutive_attacks', 0)
            stock['max_cumulative_main_net'] = sssj.get('max_cumulative_main_net', 0)
            stock['main_net_count'] = sssj.get('main_net_count', 0)

    def _enrich_bonds_from_cache(self, bonds: list, day_cache: DayCache, time_str: str):
        """从缓存填充债券的 change_pct / price"""
        for bond in bonds:
            code = str(bond.get('code', ''))
            sssj = day_cache.bond_sssj.get((time_str, code)) or {}
            bond['change_pct'] = sssj.get('change_pct', 0)
            bond['price'] = sssj.get('price', 0)

    def _process_timepoint_fast(self, day_cache: DayCache, time_str: str,
                                 conditions: Dict) -> tuple:
        """处理单个时间点（纯内存，无 DB 查询）"""
        from gs2026.dashboard2.routes.monitor import _enrich_stock_data

        # 1. 内存计算排行
        stock_ranking = self._compute_ranking_at_time(day_cache, 'stock', time_str)
        bond_ranking = self._compute_ranking_at_time(day_cache, 'bond', time_str)
        industry_ranking = self._compute_ranking_at_time(day_cache, 'industry', time_str)

        if not stock_ranking:
            return [], {}

        # 2. enrichment（从缓存）
        stock_ranking = _enrich_stock_data(stock_ranking)
        self._enrich_from_cache(stock_ranking, day_cache, time_str)
        self._enrich_bonds_from_cache(bond_ranking, day_cache, time_str)

        # 3. 大盘数据（从缓存）
        market_data = {
            'stock': day_cache.stock_apqd.get(time_str),
            'bond': day_cache.bond_apqd.get(time_str)
        }

        # 4. 构建上下文
        bond_set = set(b['code'] for b in bond_ranking if b.get('code'))
        bond_map = {b['code']: b for b in bond_ranking if b.get('code')}
        ind_top = int(conditions.get('ind_top', 10))
        top_ind = set(i['name'] for i in industry_ranking[:ind_top] if i.get('name'))
        ctx = {'bondSet': bond_set, 'bondMap': bond_map, 'topInd': top_ind}

        # 5. 评估
        mkt_conds, mkt_pass, critical_hit = self._evaluate_market(market_data, conditions)
        candidates = self._evaluate_all_stocks(stock_ranking, conditions, ctx, bond_map)

        star_color = 'red' if critical_hit else 'yellow'
        for c in candidates:
            c['starColor'] = star_color

        market_ctx = {
            'conditions': mkt_conds,
            'passed': mkt_pass,
            'total': len(mkt_conds),
            'criticalHit': critical_hit,
            'signal': '积极' if mkt_pass >= len(mkt_conds) else '谨慎' if len(mkt_conds) > 0 and mkt_pass >= len(mkt_conds) * 0.5 else '观望'
        }
        return candidates, market_ctx

    # ==================== 条件评估（不变） ====================

    def _evaluate_market(self, mkt: Dict, conditions: Dict) -> tuple:
        """评估大盘条件（复刻前端逻辑，含关键模式追踪）"""
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

    # ==================== 条件定义（不变） ====================

    def _get_market_conditions(self) -> list:
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
            {'id': 'stock_phase_up', 'name': '股票阶段(升/弹)',
             'fn': lambda m: (m.get('stock', {}).get('market_phase') or '') in ('rising', 'rebound')},
            {'id': 'bond_phase_up', 'name': '债券阶段(升/弹)',
             'fn': lambda m: (m.get('bond', {}).get('market_phase') or m.get('market_phase') or '') in ('rising', 'rebound')},
        ]

    def _get_stock_conditions(self) -> list:
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

    def _save_batch_bulk(self, engine, temp_table: str, day_candidates: list):
        """批量保存一天的所有候选到临时表（一次 executemany）"""
        from sqlalchemy import text

        rows = []
        for save_date, time_str, c, market_json in day_candidates:
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
            # 分批写入（每批 1000 条避免超大 SQL）
            batch_size = 1000
            with engine.connect() as conn:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    conn.execute(text(f"""
                        INSERT IGNORE INTO {temp_table}
                        (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
                         bond_code, bond_price, bond_change_pct, level, star_color, condition_count, total_conditions,
                         conditions, market_context)
                        VALUES (:rid, :d, :t, :sc, :sn, :sp, :scp, :bc, :bp, :bcp, :lv, :stc, :cc, :tc, :cd, :mc)
                    """), batch)
                conn.commit()
            print(f"[BACKTEST] 批量保存 {len(rows)} 条候选")

    def _replace_data(self, engine, dates: list, temp_table: str):
        """事务替换：删除旧数据 -> 插入新数据"""
        from sqlalchemy import text
        with engine.begin() as conn:
            for date in dates:
                save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                conn.execute(text("DELETE FROM buy_point_candidates WHERE date = :d"), {'d': save_date})
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
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
            conn.commit()

    # 保留旧方法供兼容（不再主动调用）
    def _process_timepoint(self, date: str, time_str: str, conditions: Dict, ds) -> tuple:
        """旧版单时间点处理（保留兼容，不再使用）"""
        from gs2026.dashboard2.routes.monitor import (
            _enrich_stock_data, _enrich_change_pct_and_main_net, _enrich_bond_data
        )
        stock_ranking = ds.get_ranking_at_time('stock', limit=200, date=date, time_str=time_str)
        bond_ranking = ds.get_ranking_at_time('bond', limit=100, date=date, time_str=time_str)
        industry_ranking = ds.get_ranking_at_time('industry', limit=30, date=date, time_str=time_str)
        if not stock_ranking:
            return [], {}
        stock_ranking = _enrich_stock_data(stock_ranking)
        stock_ranking = _enrich_change_pct_and_main_net(stock_ranking, date, time_str)
        bond_ranking = _enrich_bond_data(bond_ranking, date, time_str)
        market_data = ds.get_market_stats(date=date, use_mysql=True, time_str=time_str)
        bond_set = set(b['code'] for b in bond_ranking if b.get('code'))
        bond_map = {b['code']: b for b in bond_ranking if b.get('code')}
        ind_top = int(conditions.get('ind_top', 10))
        top_ind = set(i['name'] for i in industry_ranking[:ind_top] if i.get('name'))
        ctx = {'bondSet': bond_set, 'bondMap': bond_map, 'topInd': top_ind}
        mkt_conds, mkt_pass, critical_hit = self._evaluate_market(market_data, conditions)
        candidates = self._evaluate_all_stocks(stock_ranking, conditions, ctx, bond_map)
        star_color = 'red' if critical_hit else 'yellow'
        for c in candidates:
            c['starColor'] = star_color
        market_ctx = {
            'conditions': mkt_conds, 'passed': mkt_pass, 'total': len(mkt_conds),
            'criticalHit': critical_hit,
            'signal': '积极' if mkt_pass >= len(mkt_conds) else '谨慎' if len(mkt_conds) > 0 and mkt_pass >= len(mkt_conds) * 0.5 else '观望'
        }
        return candidates, market_ctx

    def _save_batch(self, engine, temp_table: str, date: str, time_str: str,
                    candidates: list, market_ctx: Dict):
        """旧版单时间点保存（保留兼容）"""
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


# 全局实例
task_manager = BacktestTaskManager()
