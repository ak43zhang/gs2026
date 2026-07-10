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
        """通过哈希直接获取缓存"""
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        try:
            data = self.redis.get(cache_key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[BacktestCache] get_by_hash error: {e}")
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

        # 更新MySQL历史记录
        self._update_history(params, result, hash_key)

        return hash_key

    # ========== 历史记录（MySQL持久化，排行榜模式） ==========

    def _update_history(self, params: Dict, result: Dict, hash_key: str):
        """更新历史记录（排行榜模式：保留收益最高30条）"""
        if not self.engine:
            return

        try:
            summary = result.get('summary', {})
            total_return = float(summary.get('total_return_pct', 0))
            signal_count = int(summary.get('signal_count', 0))
            win_rate = float(summary.get('win_rate', 0))

            # 构建日期范围
            date_start = params.get('date_start', params.get('date', ''))
            date_end = params.get('date_end', '')
            date_range = f"{date_start}~{date_end}" if date_end and date_end != date_start else date_start

            # 构建摘要预览
            summary_preview = {
                'total_return_pct': total_return,
                'signal_count': signal_count,
                'win_rate': win_rate,
                'trade_count': summary.get('trade_count', 0),
                'avg_profit': summary.get('avg_profit_pct', 0),
            }

            with self.engine.connect() as conn:
                # 检查是否已存在（同hash不重复）
                existing = conn.execute(
                    text("SELECT id FROM backtest_history WHERE hash = :h"),
                    {'h': hash_key}
                ).fetchone()
                if existing:
                    return  # 已存在，不重复插入

                # 检查当前数量
                count = conn.execute(
                    text("SELECT COUNT(*) FROM backtest_history")
                ).scalar()

                if count >= self.MAX_HISTORY:
                    # 找到收益最低的记录
                    min_row = conn.execute(
                        text("SELECT id, total_return_pct FROM backtest_history ORDER BY total_return_pct ASC LIMIT 1")
                    ).fetchone()

                    if min_row and total_return <= float(min_row[1]):
                        return  # 新收益不够高，不入库

                    # 删除最低的
                    conn.execute(
                        text("DELETE FROM backtest_history WHERE id = :id"),
                        {'id': min_row[0]}
                    )

                # 插入新记录
                conn.execute(text("""
                    INSERT INTO backtest_history 
                    (hash, total_return_pct, signal_count, win_rate, date_range, scheme_name, params, summary_preview)
                    VALUES (:hash, :ret, :sig, :win, :date_range, :scheme, :params, :summary)
                """), {
                    'hash': hash_key,
                    'ret': total_return,
                    'sig': signal_count,
                    'win': win_rate,
                    'date_range': date_range,
                    'scheme': params.get('scheme_name', ''),
                    'params': json.dumps(params, default=str, ensure_ascii=False),
                    'summary': json.dumps(summary_preview, default=str, ensure_ascii=False),
                })
                conn.commit()

        except Exception as e:
            print(f"[BacktestCache] _update_history error: {e}")

    def get_history(self) -> List[Dict]:
        """获取历史记录（按收益倒序）"""
        if not self.engine:
            return []

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT hash, total_return_pct, signal_count, win_rate, 
                           date_range, scheme_name, params, summary_preview, created_at
                    FROM backtest_history 
                    ORDER BY total_return_pct DESC
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
                        'summary_preview': json.loads(row[7]) if row[7] else {},
                        'created_at': str(row[8]),
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
