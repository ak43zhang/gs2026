# -*- coding: utf-8 -*-
"""
回填工具：monitor_gp_sssj 表的 min1_change_pct / min1_amount 字段

算法完全复刻 monitor_stock.compute_stock_min1_fields：
  按 time 升序，每分钟内某 code 首次出现设为基准(min1=0)，
  同分钟后续 = 当前值 - 基准值。

特点：
  - 幂等可重跑（临时表方案，整体覆盖写）
  - 快速（临时表 + JOIN 批量 UPDATE，268万行约几分钟）
  - 自动加列（若 min1 列不存在）

用法：
  python fill_stock_min1.py <table> [end_time] [mode]
    table    : 表名，如 monitor_gp_sssj_20260810
    end_time : 只回填 time < end_time 的数据，默认 '10:00:00'；传 'all' 表示全表
    mode     : dryrun(默认,只算不写) | run(写库)

示例：
  python fill_stock_min1.py monitor_gp_sssj_20260810 10:00:00 dryrun
  python fill_stock_min1.py monitor_gp_sssj_20260810 10:00:00 run
  python fill_stock_min1.py monitor_gp_sssj_20260810 all run
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
import warnings
warnings.filterwarnings('ignore')
from gs2026.utils.config_util import get_engine
from sqlalchemy import text


def add_columns_if_missing(conn, tb):
    cols = {r[0] for r in conn.execute(text(f"SHOW COLUMNS FROM {tb}")).fetchall()}
    for col in ('min1_change_pct', 'min1_amount'):
        if col not in cols:
            conn.execute(text(f"ALTER TABLE {tb} ADD COLUMN {col} DOUBLE NULL"))
            conn.commit()
            print(f'  [+] 添加列 {col}')
    return 'min1_change_pct' in cols and 'min1_amount' in cols


def compute(rows):
    """rows: [(stock_code, time, change_pct, amount)] 已按 time 升序。
    返回 [(min1_change_pct, min1_amount, stock_code, time)]"""
    base_minute = None
    base_pct = {}
    base_amt = {}
    out = []
    for code, tm, cpct, amt in rows:
        minute = str(tm)[:5]
        if minute != base_minute:
            base_minute = minute
            base_pct = {}
            base_amt = {}
        cpct = float(cpct) if cpct is not None else 0.0
        amt = float(amt) if amt is not None else 0.0
        if code not in base_pct:
            base_pct[code] = cpct
            base_amt[code] = amt
            out.append((0.0, 0.0, code, str(tm)))
        else:
            out.append((round(cpct - base_pct[code], 4),
                        round(amt - base_amt[code], 0),
                        code, str(tm)))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tb = sys.argv[1]
    end_time = sys.argv[2] if len(sys.argv) > 2 else '10:00:00'
    mode = sys.argv[3] if len(sys.argv) > 3 else 'dryrun'

    eng = get_engine()
    where = "" if end_time == 'all' else "WHERE time < :et"
    params = {} if end_time == 'all' else {'et': end_time}

    print(f'[{mode}] 表={tb} 范围={"全表" if end_time=="all" else "time<"+end_time}')

    with eng.connect() as c:
        add_columns_if_missing(c, tb)
        print('拉取数据...')
        rows = c.execute(text(
            f"SELECT stock_code, time, change_pct, amount FROM {tb} {where} ORDER BY time ASC"
        ), params).fetchall()
        print(f'共 {len(rows)} 行')

        updates = compute(rows)
        print(f'计算完成 {len(updates)} 条')
        # 样例：找一个同分钟有多个时间点的 code 展示差值
        smp = [u for u in updates if u[0] != 0.0 or u[1] != 0.0][:8]
        print('--- 非零样例(min1_chg, min1_amt, code, time) ---')
        for s in smp:
            print('  ', s)

        if mode != 'run':
            print('\n[dryrun] 未写库。加 run 参数执行写入。')
            return

        # 临时表方案：建临时表 -> 批量插入计算结果 -> JOIN UPDATE
        print('\n[run] 建临时表并写入...')
        tmp = f"_tmp_min1_{tb}"
        c.execute(text(f"DROP TEMPORARY TABLE IF EXISTS {tmp}"))
        c.execute(text(
            f"CREATE TEMPORARY TABLE {tmp} ("
            f"stock_code VARCHAR(16), time VARCHAR(16), "
            f"m1c DOUBLE, m1a DOUBLE, "
            f"PRIMARY KEY(stock_code, time))"
        ))
        c.commit()

        INS = text(f"INSERT INTO {tmp}(stock_code, time, m1c, m1a) VALUES(:code,:tm,:c,:a)")
        BATCH = 10000
        for i in range(0, len(updates), BATCH):
            chunk = updates[i:i+BATCH]
            c.execute(INS, [{'code': u[2], 'tm': u[3], 'c': u[0], 'a': u[1]} for u in chunk])
            if (i // BATCH) % 10 == 0:
                c.commit()
        c.commit()
        print(f'  临时表写入 {len(updates)} 条')

        print('  JOIN 批量 UPDATE 主表...')
        c.execute(text(
            f"UPDATE {tb} t JOIN {tmp} m "
            f"ON t.stock_code=m.stock_code AND t.time=m.time "
            f"SET t.min1_change_pct=m.m1c, t.min1_amount=m.m1a"
        ))
        c.commit()
        c.execute(text(f"DROP TEMPORARY TABLE IF EXISTS {tmp}"))
        c.commit()

        # 复核
        chk = "" if end_time == 'all' else "WHERE time < :et"
        r = c.execute(text(f"SELECT COUNT(*) FROM {tb} {chk} AND min1_amount IS NOT NULL" if chk else f"SELECT COUNT(*) FROM {tb} WHERE min1_amount IS NOT NULL"), params).fetchone()
        print(f'写库完成，已回填 min1_amount 非空行数: {r[0]}')


if __name__ == '__main__':
    main()
