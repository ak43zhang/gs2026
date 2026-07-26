"""
TickStateCache — 基于上一tick计算的通用状态缓存

═══════════════════════════════════════════════════════════════════
设计背景
═══════════════════════════════════════════════════════════════════
量化实时计算中，大量指标是"递推累积"型：
    当前tick值 = f(上一tick值, 当前增量)
如：累计主力净额、峰值净额、累计次数等。

这类计算的正确实现必须遵循标准流程：
    ① 拿上一tick的值（L1内存 → L2Redis → L3MySQL 三级降级）
    ② 基于上一tick + 当前增量，计算当前tick
    ③ 【关键】算完后立即把"当前tick"存入内存，供下一tick使用
    ④ 异步存Redis/MySQL（供重启恢复）

历史教训（本类要解决的bug）：
    旧实现（monitor_stock._get_cached_prev_main）缺少步骤③，
    内存里存的是"绕道Redis查来的上一tick"，且timestamp标签与data内容
    错位1个tick，导致缓存命中时返回落后2个tick的数据，累计净额计算错误。

═══════════════════════════════════════════════════════════════════
核心原则
═══════════════════════════════════════════════════════════════════
1. 语义清晰：内存缓存永远存"最近算完的那个tick"（timestamp与data一致）
2. 算完即存：put_current 在所有指标计算完成后调用
3. 放宽命中：只要缓存是"当前时间之前的最近tick"（0<diff<=容错窗口）即命中
4. 三级降级：内存未命中 → Redis → MySQL，任何一级失败自动降级
5. 不宕机必命中：只要上一tick执行了put_current，本tick get_prev必命中L1

═══════════════════════════════════════════════════════════════════
使用示例
═══════════════════════════════════════════════════════════════════
    cache = TickStateCache(
        name='main_net',
        redis_loader=lambda tbl, t: redis_util.load_dataframe_by_time(tbl, t),
        prev_time_finder=lambda tbl, t: redis_util.get_prev_timestamp_with_data(tbl, t),
        mysql_loader=lambda tbl, t: _load_from_mysql(tbl, t),
    )

    def deal_tick(loop_start):
        # ① 拿上一tick
        df_prev = cache.get_prev(sssj_table, time_full, date_str)
        # ② 计算当前tick
        df_now = calculate_cumulative(df_now, df_prev)
        # ③ 算完所有指标后存内存（供下一tick）
        cache.put_current(sssj_table, time_full, date_str, df_now)
        # ④ 存表（Redis/MySQL由业务侧或本类异步完成）
        save_dataframe_async(df_now, sssj_table, ...)
"""

from datetime import datetime
from typing import Optional, Callable, Any

from gs2026.utils import log_util
from pathlib import Path

logger = log_util.setup_logger(str(Path(__file__).absolute()))


class TickStateCache:
    """
    基于上一tick计算的通用状态缓存（三级：内存 → Redis → MySQL）

    适用于所有"当前tick = f(上一tick, 当前增量)"的递推计算。
    """

    def __init__(
        self,
        name: str,
        redis_loader: Optional[Callable[[str, str], Any]] = None,
        prev_time_finder: Optional[Callable[[str, str], Optional[str]]] = None,
        mysql_loader: Optional[Callable[[str, str], Any]] = None,
        hit_window_seconds: int = 60,
        enable_debug_log: bool = False,
    ):
        """
        Args:
            name: 缓存名（用于日志区分，如 'main_net'）
            redis_loader: (table, time_str) -> data，从Redis加载指定时间数据
            prev_time_finder: (table, current_time) -> prev_time，找上一个有数据的时间戳
            mysql_loader: (table, time_str) -> data，从MySQL加载（兜底）
            hit_window_seconds: 内存命中容错窗口（秒），默认60秒（覆盖tick抖动/跳tick）
            enable_debug_log: 是否输出详细排查日志（排查完统一关闭）
        """
        self.name = name
        self._redis_loader = redis_loader
        self._prev_time_finder = prev_time_finder
        self._mysql_loader = mysql_loader
        self._hit_window = hit_window_seconds
        self._debug = enable_debug_log

        # 内存缓存：存"最近算完的那个tick"
        # 结构: {'date': 'YYYYMMDD', 'timestamp': 'HH:MM:SS', 'data': <当前tick数据>}
        self._mem = {'date': None, 'timestamp': None, 'data': None}

        # 统计
        self._stat = {'l1_hit': 0, 'l2_hit': 0, 'l3_hit': 0, 'miss': 0}

    # ─────────────────────────────────────────────────────────
    # 步骤①：获取上一tick的值（三级降级）
    # ─────────────────────────────────────────────────────────
    def get_prev(self, table: str, current_time: str, date_str: str):
        """
        获取上一tick的值（L1内存 → L2Redis → L3MySQL）

        Returns:
            上一tick数据，全部失败返回 None
        """
        # ===== L1: 内存 =====
        data = self._get_from_memory(current_time, date_str)
        if data is not None:
            self._stat['l1_hit'] += 1
            if self._debug:
                logger.info(f"[{self.name}][L1命中] current={current_time} "
                            f"mem_ts={self._mem['timestamp']}")
            return self._copy(data)

        # ===== L2: Redis =====
        prev_time = None
        if self._prev_time_finder is not None:
            try:
                prev_time = self._prev_time_finder(table, current_time)
            except Exception as e:
                logger.warning(f"[{self.name}] 查上一tick时间戳失败: {e}")

        if prev_time and self._redis_loader is not None:
            try:
                data = self._redis_loader(table, prev_time)
                if self._non_empty(data):
                    self._stat['l2_hit'] += 1
                    if self._debug:
                        logger.info(f"[{self.name}][L2命中] current={current_time} "
                                    f"prev_time={prev_time}")
                    return data
            except Exception as e:
                logger.warning(f"[{self.name}] Redis加载失败: {e}")

        # ===== L3: MySQL 兜底 =====
        if prev_time and self._mysql_loader is not None:
            try:
                data = self._mysql_loader(table, prev_time)
                if self._non_empty(data):
                    self._stat['l3_hit'] += 1
                    logger.info(f"[{self.name}][L3兜底] current={current_time} "
                                f"prev_time={prev_time} (Redis未命中，走MySQL)")
                    return data
            except Exception as e:
                logger.warning(f"[{self.name}] MySQL加载失败: {e}")

        # ===== 全部未命中：用内存旧值兜底（保证累计连续，避免断裂）=====
        if self._mem['data'] is not None and self._mem['date'] == date_str:
            self._stat['miss'] += 1
            logger.warning(f"[{self.name}][兜底] current={current_time} "
                           f"三级全未命中，沿用内存旧tick={self._mem['timestamp']} "
                           f"保证累计连续")
            return self._copy(self._mem['data'])

        self._stat['miss'] += 1
        logger.warning(f"[{self.name}][MISS] current={current_time} "
                       f"三级全未命中且无内存旧值，返回None(将走重启恢复)")
        return None

    # ─────────────────────────────────────────────────────────
    # 步骤③：算完所有指标后，把当前tick存入内存（供下一tick）
    # ─────────────────────────────────────────────────────────
    def put_current(self, table: str, current_time: str, date_str: str, data):
        """
        算完当前tick后调用，把当前tick存入内存（供下一tick get_prev命中L1）

        注意：必须在所有指标计算完成后调用，data应为完整的当前tick数据。
        """
        self._mem = {
            'date': date_str,
            'timestamp': current_time,  # 当前tick时间（与data一致，无错位）
            'data': self._copy(data),
        }
        if self._debug:
            logger.info(f"[{self.name}][存内存] 当前tick={current_time} 已存入，供下一tick使用")

    # ─────────────────────────────────────────────────────────
    # 内存清理（日期切换/重启）
    # ─────────────────────────────────────────────────────────
    def invalidate(self):
        """清空内存缓存（日期切换时调用）"""
        self._mem = {'date': None, 'timestamp': None, 'data': None}
        logger.info(f"[{self.name}] 内存缓存已清空")

    def get_stats(self) -> dict:
        """获取命中统计（用于排查/监控）"""
        total = sum(self._stat.values())
        return {
            **self._stat,
            'total': total,
            'l1_rate': f"{self._stat['l1_hit'] / total * 100:.1f}%" if total else "0%",
        }

    # ─────────────────────────────────────────────────────────
    # 内部：内存有效性判断（放宽窗口 + 无错位）
    # ─────────────────────────────────────────────────────────
    def _get_from_memory(self, current_time: str, date_str: str):
        """
        内存命中判断：
        - 同一交易日
        - 缓存时间 < 当前时间（是过去的tick）
        - 时间差在容错窗口内（0 < diff <= hit_window，默认60秒）
        """
        c = self._mem
        if c['date'] != date_str or c['data'] is None or c['timestamp'] is None:
            return None
        try:
            cache_dt = datetime.strptime(f"{date_str} {c['timestamp']}", "%Y%m%d %H:%M:%S")
            cur_dt = datetime.strptime(f"{date_str} {current_time}", "%Y%m%d %H:%M:%S")
            diff = (cur_dt - cache_dt).total_seconds()
            # 放宽窗口：只要是"当前时间之前的最近tick"就命中
            if 0 < diff <= self._hit_window:
                return c['data']
        except ValueError:
            pass
        return None

    @staticmethod
    def _copy(data):
        """安全拷贝（DataFrame用.copy()，其他直接返回）"""
        if data is None:
            return None
        copy_fn = getattr(data, 'copy', None)
        return copy_fn() if callable(copy_fn) else data

    @staticmethod
    def _non_empty(data) -> bool:
        """判断数据非空（兼容DataFrame和普通对象）"""
        if data is None:
            return False
        empty_attr = getattr(data, 'empty', None)
        if empty_attr is not None:
            return not empty_attr
        return bool(data)
