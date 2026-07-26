"""
中间状态快照缓存模块（Snapshot Cache）

用途：持久化 monitor_bond.py 的累积型中间状态，解决服务重启后计算错误问题。

背景：
    VWAP、斜率、形态等指标依赖跨tick累积的中间状态（如 _mkt_trend_vwap_sum_pv）。
    这些状态仅存在于内存，服务重启后从零开始累积，导致计算结果错误。
    数学上不可逆：从结果 mkt_vwap_bias 无法反推 sum_pv/sum_v。

方案（v12.0 Snapshot快照模式）：
    - 每tick生成完整状态快照（大盘 + 400只债券），存入 Redis（覆盖更新）
    - 每30秒同步一份到 MySQL（稀疏备份）
    - 服务重启时从 Redis/MySQL 恢复最新快照

存储结构：
    Redis: snapshot:mkt:{date}   Hash{time_sec: mkt_snapshot_json}
    Redis: snapshot:bonds:{date} Hash{time_sec: bonds_snapshot_json}
    MySQL: snapshot_backup 表（每30秒1行）

设计原则：
    - 不改动原有计算逻辑，只新增持久化与恢复
    - 存储异步执行，不阻塞主tick
    - 恢复/存储失败自动降级，不影响主流程（保持原行为）
"""

import json
from pathlib import Path

from gs2026.utils import log_util, redis_util

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# Redis key 前缀
_MKT_KEY_PREFIX = "snapshot:mkt:"
_BONDS_KEY_PREFIX = "snapshot:bonds:"
_REDIS_EXPIRE = 43200  # 12小时

# Redis Hash field 名（方案A：固定field覆盖写入，避免按time_sec累积）
_LATEST_FIELD = "latest"   # 存最新快照JSON
_TIME_FIELD = "_ts"        # 存最新快照的time_sec（调试用）

# MySQL 备份表名
_BACKUP_TABLE = "snapshot_backup"

# 恢复结果缓存（按日期缓存，供多个consumer共享同一次恢复结果）
# 结构: {'date': 'YYYYMMDD', 'mkt': {...}, 'bonds': {...}}
_recovered_cache = {'date': None, 'mkt': None, 'bonds': None}

# MySQL备份表是否已确保存在
_backup_table_ready = False


def reset_recovered_flag():
    """重置恢复缓存（供测试调用）"""
    global _recovered_cache
    _recovered_cache = {'date': None, 'mkt': None, 'bonds': None}


def _ensure_backup_table(engine):
    """确保 MySQL 备份表存在（幂等，仅首次建表）"""
    global _backup_table_ready
    if _backup_table_ready or engine is None:
        return
    try:
        from sqlalchemy import text as sa_text
        ddl = sa_text(f"""
            CREATE TABLE IF NOT EXISTS {_BACKUP_TABLE} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                snapshot_type VARCHAR(16) NOT NULL,
                trading_date VARCHAR(8) NOT NULL,
                snapshot_time INT NOT NULL,
                snapshot_json LONGTEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_type_date (snapshot_type, trading_date),
                KEY idx_date (trading_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        with engine.begin() as conn:
            conn.execute(ddl)
        _backup_table_ready = True
        logger.info(f"[快照] 备份表 {_BACKUP_TABLE} 就绪")
    except Exception as e:
        logger.warning(f"[快照] 备份表创建失败(降级，仅用Redis): {e}")


def save_snapshot(date, time_sec, mkt_snapshot, bonds_snapshot, engine=None):
    """
    存储快照（异步调用，失败不影响主流程）

    Args:
        date: 交易日 'YYYYMMDD'
        time_sec: 当前tick时间（秒）
        mkt_snapshot: 大盘中间状态 dict
        bonds_snapshot: 个券中间状态 dict {code: {...}}
        engine: MySQL engine（每30秒备份用）
    """
    # ===== L2: Redis（每tick，覆盖更新）=====
    try:
        r = redis_util._get_redis_client()
        if r is not None:
            mkt_json = json.dumps(mkt_snapshot, ensure_ascii=False)
            bonds_json = json.dumps(bonds_snapshot, ensure_ascii=False)
            pipe = r.pipeline()
            mkt_key = f"{_MKT_KEY_PREFIX}{date}"
            bonds_key = f"{_BONDS_KEY_PREFIX}{date}"
            # 方案A：固定field "latest" 覆盖写入（恢复只需最新值，避免field累积到960MB）
            # 同时记录time_sec到独立field，便于日志/调试查看快照时间
            pipe.hset(mkt_key, _LATEST_FIELD, mkt_json)
            pipe.hset(mkt_key, _TIME_FIELD, str(time_sec))
            pipe.expire(mkt_key, _REDIS_EXPIRE)
            pipe.hset(bonds_key, _LATEST_FIELD, bonds_json)
            pipe.hset(bonds_key, _TIME_FIELD, str(time_sec))
            pipe.expire(bonds_key, _REDIS_EXPIRE)
            pipe.execute()
    except Exception as e:
        logger.warning(f"[快照] Redis存储失败(不影响主流程): {e}")

    # ===== L3: MySQL（每30秒备份）=====
    if time_sec % 30 == 0 and engine is not None:
        try:
            _ensure_backup_table(engine)
            _save_mysql_backup(engine, date, time_sec, mkt_snapshot, bonds_snapshot)
        except Exception as e:
            logger.warning(f"[快照] MySQL备份失败(降级): {e}")


def _save_mysql_backup(engine, date, time_sec, mkt_snapshot, bonds_snapshot):
    """MySQL稀疏备份（每类型保留最新1行，覆盖更新）"""
    from sqlalchemy import text as sa_text
    sql = sa_text(f"""
        INSERT INTO {_BACKUP_TABLE}
            (snapshot_type, trading_date, snapshot_time, snapshot_json)
        VALUES (:t, :d, :ts, :j)
        ON DUPLICATE KEY UPDATE
            snapshot_time = VALUES(snapshot_time),
            snapshot_json = VALUES(snapshot_json)
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            't': 'mkt', 'd': date, 'ts': time_sec,
            'j': json.dumps(mkt_snapshot, ensure_ascii=False)
        })
        conn.execute(sql, {
            't': 'bonds', 'd': date, 'ts': time_sec,
            'j': json.dumps(bonds_snapshot, ensure_ascii=False)
        })


def recover_snapshot(date, engine=None):
    """
    启动/日期切换时恢复快照（按日期缓存，多consumer共享同一次恢复）

    首次查询后结果缓存在 _recovered_cache，同一date的后续调用直接返回缓存，
    避免多个 compute 函数各查一次 Redis/MySQL。

    Returns:
        (mkt_snapshot, bonds_snapshot)  # 均为 dict 或 None
    """
    global _recovered_cache

    # 命中缓存（同一交易日已恢复过）→ 直接返回
    if _recovered_cache['date'] == date:
        return _recovered_cache['mkt'], _recovered_cache['bonds']

    mkt_snap, bonds_snap = None, None

    # ===== L2: Redis 恢复 =====
    try:
        r = redis_util._get_redis_client()
        if r is not None:
            mkt_key = f"{_MKT_KEY_PREFIX}{date}"
            bonds_key = f"{_BONDS_KEY_PREFIX}{date}"
            # 方案A：直接HGET固定field "latest"（无需hkeys+max）
            mkt_data = r.hget(mkt_key, _LATEST_FIELD)
            bonds_data = r.hget(bonds_key, _LATEST_FIELD)
            if mkt_data or bonds_data:
                mkt_snap = _loads(mkt_data)
                bonds_snap = _loads(bonds_data)
                ts_raw = r.hget(mkt_key, _TIME_FIELD)
                ts = ts_raw.decode() if isinstance(ts_raw, bytes) else (ts_raw or '?')
                logger.info(f"[快照] 从Redis恢复成功 date={date} time={ts} "
                            f"mkt={'OK' if mkt_snap else 'None'} "
                            f"bonds={len(bonds_snap) if bonds_snap else 0}只")
    except Exception as e:
        logger.warning(f"[快照] Redis恢复失败,尝试MySQL: {e}")

    # ===== L3: MySQL 恢复（Redis未命中时）=====
    if mkt_snap is None and bonds_snap is None and engine is not None:
        try:
            mkt_snap, bonds_snap = _recover_mysql_backup(engine, date)
            if mkt_snap or bonds_snap:
                logger.info(f"[快照] 从MySQL备份恢复成功 date={date}")
        except Exception as e:
            logger.warning(f"[快照] MySQL恢复失败(从0开始): {e}")

    # ===== L4: 都无 → 从0开始（原行为）=====
    if mkt_snap is None and bonds_snap is None:
        logger.info(f"[快照] 无可用快照 date={date}, 从0开始累积")

    # 写入缓存（无论成功与否都记录date，避免重复查询）
    _recovered_cache = {'date': date, 'mkt': mkt_snap, 'bonds': bonds_snap}
    return mkt_snap, bonds_snap


def _recover_mysql_backup(engine, date):
    """从 MySQL 备份恢复"""
    from sqlalchemy import text as sa_text
    sql = sa_text(f"""
        SELECT snapshot_type, snapshot_json
        FROM {_BACKUP_TABLE}
        WHERE trading_date = :d
    """)
    mkt_snap, bonds_snap = None, None
    with engine.connect() as conn:
        rows = conn.execute(sql, {'d': date}).fetchall()
        for row in rows:
            stype, sjson = row[0], row[1]
            if stype == 'mkt':
                mkt_snap = json.loads(sjson)
            elif stype == 'bonds':
                bonds_snap = json.loads(sjson)
    return mkt_snap, bonds_snap


def _loads(data):
    """安全解析 Redis 返回的 JSON（兼容 bytes/str）"""
    if data is None:
        return None
    if isinstance(data, bytes):
        data = data.decode()
    return json.loads(data)
