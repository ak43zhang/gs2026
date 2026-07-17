"""
回测缓存管理模块
- 单次结果缓存：Redis（TTL 7天，避免重复计算）
- 历史记录：MySQL持久化（排行榜模式，保留收益最高30条）
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, Optional, List
from sqlalchemy import text


class BacktestCache:
    """回测缓存管理器"""

    CACHE_PREFIX = "backtest:v1"
    CACHE_TTL = 7 * 24 * 3600  # 7天
    MAX_HISTORY = 30  # 历史记录最大条数

    def __init__(self, redis_client, engine=None):
        """
        Args:
            redis_client: Redis客户端（用于结果缓存）
            engine: SQLAlchemy引擎（用于历史记录持久化）
        """
        self.redis = redis_client
        self.engine = engine
        self._migrated = False

    def _ensure_avg_daily_column(self):
        """自动迁移：确保 avg_daily_return_pct 和 order_mode 列存在"""
        if self._migrated or not self.engine:
            return
        self._migrated = True
        try:
            with self.engine.connect() as conn:
                # 检查 avg_daily_return_pct 列
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name='backtest_history' AND column_name='avg_daily_return_pct'"
                )).scalar()
                if result == 0:
                    conn.execute(text(
                        "ALTER TABLE backtest_history ADD COLUMN avg_daily_return_pct DECIMAL(10,4) DEFAULT 0"
                    ))
                    conn.execute(text(
                        "UPDATE backtest_history SET avg_daily_return_pct = "
                        "total_return_pct / GREATEST(JSON_EXTRACT(summary_preview, '$.trade_days'), 1) "
                        "WHERE avg_daily_return_pct = 0 OR avg_daily_return_pct IS NULL"
                    ))
                    conn.commit()
                    print("[BacktestCache] 已自动添加 avg_daily_return_pct 列并回填数据")

                # 检查 order_mode 列
                result2 = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name='backtest_history' AND column_name='order_mode'"
                )).scalar()
                if result2 == 0:
                    conn.execute(text(
                        "ALTER TABLE backtest_history ADD COLUMN order_mode VARCHAR(20) DEFAULT 'market'"
                    ))
                    conn.execute(text(
                        "UPDATE backtest_history SET order_mode = "
                        "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(params, '$.order_mode')), 'market')"
                    ))
                    conn.commit()
                    print("[BacktestCache] 已自动添加 order_mode 列并回填数据")

                # 检查 result_data 列
                result3 = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name='backtest_history' AND column_name='result_data'"
                )).scalar()
                if result3 == 0:
                    conn.execute(text(
                        "ALTER TABLE backtest_history ADD COLUMN result_data LONGTEXT"
                    ))
                    conn.commit()
                    print("[BacktestCache] 已自动添加 result_data 列")
        except Exception as e:
            print(f"[BacktestCache] _ensure_avg_daily_column error: {e}")
            import traceback
            traceback.print_exc()

    def _compute_hash(self, params: Dict) -> str:
        """计算参数哈希"""
        # 排序确保相同参数产生相同哈希
        stable = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(stable.encode()).hexdigest()[:16]

    # ========== 单次结果缓存（Redis） ==========

    def get(self, params: Dict) -> Optional[Dict]:
        """获取缓存的回测结果"""
        hash_key = self._compute_hash(params)
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        try:
            data = self.redis.get(cache_key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[BacktestCache] get error: {e}")
        return None

    def get_by_hash(self, hash_key: str) -> Optional[Dict]:
        """通过哈希直接获取缓存（Redis优先，MySQL回退）"""
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        try:
            data = self.redis.get(cache_key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[BacktestCache] get_by_hash redis error: {e}")

        # Redis未命中，尝试从MySQL回退
        if self.engine:
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT params, result_data, created_at, summary_preview FROM backtest_history WHERE hash = :h"),
                        {'h': hash_key}
                    ).fetchone()
                    if row and row[1]:
                        # 完整数据可用
                        params = json.loads(row[0]) if row[0] else {}
                        result_data = json.loads(row[1])
                        reconstructed = {
                            "meta": {
                                "created_at": str(row[2]),
                                "hash": hash_key,
                                "params": params
                            },
                            "result": result_data
                        }
                        # 回写Redis缓存（加速后续访问）
                        try:
                            self.redis.set(cache_key, json.dumps(reconstructed, default=str), ex=self.CACHE_TTL)
                        except Exception:
                            pass
                        return reconstructed
                    elif row:
                        # 记录存在但 result_data 为NULL（旧记录），返回降级数据
                        params = json.loads(row[0]) if row[0] else {}
                        summary_preview = json.loads(row[3]) if row[3] else {}
                        degraded = {
                            "meta": {
                                "created_at": str(row[2]),
                                "hash": hash_key,
                                "params": params
                            },
                            "result": {
                                "summary": summary_preview,
                                "trades": [],
                                "degraded": True
                            }
                        }
                        print(f"[BacktestCache] get_by_hash: returning degraded data for hash={hash_key} (result_data is NULL)")
                        return degraded
            except Exception as e:
                print(f"[BacktestCache] get_by_hash mysql fallback error: {e}")

        return None

    def set(self, params: Dict, result: Dict) -> str:
        """
        设置缓存并更新历史记录

        Args:
            params: 回测参数
            result: 回测结果

        Returns:
            缓存哈希值
        """
        hash_key = self._compute_hash(params)
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"

        data = {
            "meta": {
                "created_at": datetime.now().isoformat(),
                "hash": hash_key,
                "params": params
            },
            "result": result
        }

        try:
            # 写入Redis缓存（带TTL）
            self.redis.set(cache_key, json.dumps(data, default=str), ex=self.CACHE_TTL)
        except Exception as e:
            print(f"[BacktestCache] set redis error: {e}")

        # 更新MySQL历史记录（含完整result持久化）
        self._update_history(params, result, hash_key)

        return hash_key

    # ========== 历史记录（MySQL持久化，排行榜模式） ==========

    def _update_history(self, params: Dict, result: Dict, hash_key: str):
        """更新历史记录（排行榜模式：保留日均收益最高30条）"""
        if not self.engine:
            return

        self._ensure_avg_daily_column()

        try:
            summary = result.get('summary', {})
            total_return = float(summary.get('total_return_pct', 0))
            signal_count = int(summary.get('total_signals', summary.get('signal_count', 0)))
            win_rate = float(summary.get('win_rate', 0))
            trade_days = max(int(summary.get('trade_days', 1)), 1)
            avg_daily_return = round(total_return / trade_days, 4)

            # 构建日期范围
            date_start = params.get('date_start', params.get('date', ''))
            date_end = params.get('date_end', '')
            date_range = f"{date_start}~{date_end}" if date_end and date_end != date_start else date_start

            # 构建摘要预览（含前端需要的 trade_days 和 total_signals）
            summary_preview = {
                'total_return_pct': total_return,
                'signal_count': signal_count,
                'total_signals': signal_count,  # 前端使用 total_signals
                'win_rate': win_rate,
                'trade_count': summary.get('trade_count', 0),
                'trade_days': trade_days,
                'avg_daily_return_pct': avg_daily_return,
                'avg_profit': summary.get('avg_profit_pct', 0),
                'date_start': date_start,
                'date_end': date_end or date_start,
            }

            with self.engine.connect() as conn:
                # 检查是否已存在
                existing = conn.execute(
                    text("SELECT id FROM backtest_history WHERE hash = :h"),
                    {'h': hash_key}
                ).fetchone()
                if existing:
                    # 更新已有记录（数据变更后重测场景）
                    conn.execute(text("""
                        UPDATE backtest_history 
                        SET total_return_pct = :ret, signal_count = :sig, win_rate = :win,
                            avg_daily_return_pct = :avg_daily, order_mode = :order_mode,
                            summary_preview = :summary, result_data = :result_data,
                            params = :params, date_range = :date_range
                        WHERE hash = :hash
                    """), {
                        'hash': hash_key,
                        'ret': total_return,
                        'sig': signal_count,
                        'win': win_rate,
                        'avg_daily': avg_daily_return,
                        'order_mode': params.get('order_mode', 'market'),
                        'summary': json.dumps(summary_preview, default=str, ensure_ascii=False),
                        'result_data': json.dumps(result, default=str, ensure_ascii=False),
                        'params': json.dumps(params, default=str, ensure_ascii=False),
                        'date_range': date_range,
                    })
                    conn.commit()
                    return

                # 插入新记录（不限数量，前端控制显示条数）
                conn.execute(text("""
                    INSERT INTO backtest_history 
                    (hash, total_return_pct, signal_count, win_rate, avg_daily_return_pct, order_mode, date_range, scheme_name, params, summary_preview, result_data)
                    VALUES (:hash, :ret, :sig, :win, :avg_daily, :order_mode, :date_range, :scheme, :params, :summary, :result_data)
                """), {
                    'hash': hash_key,
                    'ret': total_return,
                    'sig': signal_count,
                    'win': win_rate,
                    'avg_daily': avg_daily_return,
                    'order_mode': params.get('order_mode', 'market'),
                    'date_range': date_range,
                    'scheme': params.get('scheme_name', ''),
                    'params': json.dumps(params, default=str, ensure_ascii=False),
                    'summary': json.dumps(summary_preview, default=str, ensure_ascii=False),
                    'result_data': json.dumps(result, default=str, ensure_ascii=False),
                })
                conn.commit()

        except Exception as e:
            print(f"[BacktestCache] _update_history error: {e}")

    def get_history(self) -> List[Dict]:
        """获取历史记录（排除的排后面，然后按日均收益倒序）"""
        if not self.engine:
            return []

        self._ensure_avg_daily_column()

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT hash, total_return_pct, signal_count, win_rate, 
                           date_range, scheme_name, params, summary_preview, created_at,
                           COALESCE(note, '') as note, COALESCE(is_excluded, 0) as is_excluded,
                           COALESCE(order_mode, 'market') as order_mode
                    FROM backtest_history 
                    ORDER BY is_excluded ASC, avg_daily_return_pct DESC
                """)).fetchall()

                history = []
                for row in rows:
                    entry = {
                        'hash': row[0],
                        'total_return_pct': float(row[1]),
                        'signal_count': row[2],
                        'win_rate': float(row[3]),
                        'date_range': row[4],
                        'scheme_name': row[5],
                        'params': json.loads(row[6]) if row[6] else {},
                        'summary_preview': json.loads(row[7]) if row[7] else {},
                        'timestamp': str(row[8]),
                        'note': row[9] or '',
                        'is_excluded': bool(row[10]),
                        'order_mode': row[11] or 'market',
                    }
                    history.append(entry)
                return history

        except Exception as e:
            print(f"[BacktestCache] get_history error: {e}")
            return []

    def delete_history(self, hash_key: str) -> bool:
        """删除指定历史记录"""
        if not self.engine:
            return False

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("DELETE FROM backtest_history WHERE hash = :h"),
                    {'h': hash_key}
                )
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            print(f"[BacktestCache] delete_history error: {e}")
            return False

    def update_history_note(self, hash_key: str, note: str = None, is_excluded: bool = None) -> bool:
        """更新历史记录的备注和排除标记"""
        if not self.engine:
            return False
        try:
            updates = []
            params = {'h': hash_key}
            if note is not None:
                updates.append("note = :note")
                params['note'] = note
            if is_excluded is not None:
                updates.append("is_excluded = :excluded")
                params['excluded'] = 1 if is_excluded else 0
            if not updates:
                return False
            sql = f"UPDATE backtest_history SET {', '.join(updates)} WHERE hash = :h"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            print(f"[BacktestCache] update_history_note error: {e}")
            return False

    def clear_history(self):
        """清空所有历史记录"""
        if not self.engine:
            return

        try:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM backtest_history"))
                conn.commit()
        except Exception as e:
            print(f"[BacktestCache] clear_history error: {e}")
