"""
为今日(20260527) apqd 表填充 market_phase 数据。
读取已有数据，逐行计算阶段，批量 UPDATE 回去。
"""
from sqlalchemy import create_engine, text
import time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs',
                       pool_size=2, connect_args={'connect_timeout': 10})

DATE = '20260527'
TABLES = [f'monitor_gp_apqd_{DATE}', f'monitor_zq_apqd_{DATE}']


def safe_ratio(up, down):
    total = up + down
    return up / total if total > 0 else None


def avg_ratio(data, i_up, i_down):
    vals = [safe_ratio(r[i_up], r[i_down]) for r in data]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.5


def compute_phase(all_ticks):
    """给定按时间倒序的 tick 列表 [(body_up, body_down, min_up, min_down), ...] 计算阶段"""
    if len(all_ticks) < 20:
        return 'neutral', 'weak', 0.0

    recent = all_ticks[:60]
    ref = all_ticks[60:160]

    recent_body = avg_ratio(recent, 0, 1)
    ref_body = avg_ratio(ref, 0, 1) if ref else recent_body
    recent_tick = avg_ratio(recent, 2, 3)
    ref_tick = avg_ratio(ref, 2, 3) if ref else recent_tick
    current_body = safe_ratio(all_ticks[0][0], all_ticks[0][1]) or 0.5

    momentum = (recent_body - ref_body) * 0.6 + (recent_tick - ref_tick) * 0.4
    abs_m = abs(momentum)

    state = 'bull' if current_body > 0.5 else 'bear'
    trend = 'improving' if momentum > 0 else 'weakening'

    PHASES = {
        ('bull', 'improving'): 'rising',
        ('bull', 'weakening'): 'pullback',
        ('bear', 'improving'): 'rebound',
        ('bear', 'weakening'): 'falling',
    }
    phase = PHASES[(state, trend)]
    if abs_m < 0.005:
        phase = 'neutral'

    strength = 'strong' if abs_m > 0.05 else ('medium' if abs_m > 0.02 else 'weak')
    return phase, strength, round(momentum, 6)


for table in TABLES:
    print(f"\n=== 处理 {table} ===")
    t0 = time.time()

    with engine.connect() as conn:
        # 检查表是否存在
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='gs' AND table_name=:t"
        ), {'t': table}).fetchone()
        if not exists:
            print(f"  表不存在，跳过")
            continue

        # 检查是否已有 market_phase 列
        cols = [r[0] for r in conn.execute(text(f"SHOW COLUMNS FROM `{table}`")).fetchall()]
        if 'market_phase' not in cols:
            print(f"  添加 market_phase/phase_strength/phase_momentum 列...")
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN market_phase VARCHAR(10) DEFAULT NULL"))
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN phase_strength VARCHAR(10) DEFAULT NULL"))
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN phase_momentum DECIMAL(10,6) DEFAULT NULL"))
            conn.commit()

        # 读取所有数据（按时间正序）
        rows = conn.execute(text(
            f"SELECT time, body_up, body_down, min_up, min_down FROM `{table}` ORDER BY time ASC"
        )).fetchall()
        print(f"  总行数: {len(rows)}")

    # 计算每行的阶段（需要按时间倒序的窗口）
    updates = []
    for i in range(len(rows)):
        # 构建当前行及之前所有行（倒序）
        window = [(rows[j][1], rows[j][2], rows[j][3], rows[j][4]) for j in range(i, -1, -1)]
        phase, strength, momentum = compute_phase(window)
        updates.append((phase, strength, momentum, rows[i][0]))

    # 批量 UPDATE
    print(f"  计算完成，批量更新...")
    with engine.connect() as conn:
        batch_size = 500
        for start in range(0, len(updates), batch_size):
            batch = updates[start:start + batch_size]
            for phase, strength, momentum, t in batch:
                conn.execute(text(
                    f"UPDATE `{table}` SET market_phase=:p, phase_strength=:s, phase_momentum=:m WHERE time=:t"
                ), {'p': phase, 's': strength, 'm': momentum, 't': t})
            conn.commit()

    elapsed = time.time() - t0
    print(f"  完成! 更新 {len(updates)} 行, 耗时 {elapsed:.1f}s")

    # 验证
    with engine.connect() as conn:
        sample = conn.execute(text(
            f"SELECT time, market_phase, phase_strength, phase_momentum "
            f"FROM `{table}` WHERE market_phase IS NOT NULL ORDER BY time DESC LIMIT 5"
        )).fetchall()
        print(f"  最近5条:")
        for r in sample:
            print(f"    {r[0]} → {r[1]}({r[2]}) momentum={r[3]}")

print("\n✅ 全部完成!")
