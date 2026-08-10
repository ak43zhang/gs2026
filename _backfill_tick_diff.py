#!/usr/bin/env python3
"""
回填 tick_diff 字段到 APQD 表（历史数据）

逻辑：按时间正序遍历每行
  cur_up > cur_down → tick_diff += 1
  cur_down > cur_up → tick_diff -= 1
  cur_up == cur_down → 不变

用法：修改下面的 CONFIG 参数，然后直接运行
  python _backfill_tick_diff.py
"""
import sys
sys.path.insert(0, 'src')

from sqlalchemy import create_engine, text

# ============ 修改这里的参数 ============
TABLE_NAME = 'monitor_zq_apqd_20260810'   # 表名
DRY_RUN = False                            # True=只预览不写入, False=实际写入
# ========================================

DB_URL = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'


def main():
    engine = create_engine(DB_URL)

    # 1. Check column exists
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME=:t AND COLUMN_NAME='tick_diff'"
        ), {'t': TABLE_NAME})
        if not result.fetchall():
            print(f'ERROR: tick_diff column not found in {TABLE_NAME}')
            sys.exit(1)

    # 2. Load all rows ordered by time ASC
    with engine.connect() as conn:
        result = conn.execute(text(
            f"SELECT time, cur_up, cur_down, cur_flat, tick_diff "
            f"FROM {TABLE_NAME} ORDER BY time ASC"
        ))
        rows = result.fetchall()

    total = len(rows)
    print(f'Table: {TABLE_NAME}, total rows: {total}')

    if total == 0:
        print('No data to process.')
        sys.exit(0)

    # 3. Compute tick_diff
    tick_diff = 0
    updates = []
    for row in rows:
        time_val, cur_up, cur_down, cur_flat, old_td = row
        if cur_up > cur_down:
            tick_diff += 1
        elif cur_down > cur_up:
            tick_diff -= 1
        updates.append((time_val, tick_diff, cur_up, cur_down))

    # 4. Dry run or write
    if DRY_RUN:
        print('\n=== DRY RUN (first 10 rows) ===')
        for i, (tval, td, up, dn) in enumerate(updates[:10]):
            print(f'  time={tval}, up={up}, down={dn} → tick_diff={td}')
        print(f'\n... total {total} rows would be updated')
        print('Set DRY_RUN = False to actually write.')
        sys.exit(0)

    # 5. Write to DB
    print(f'\nWriting {total} rows...')
    updated = 0
    with engine.connect() as conn:
        for tval, td, up, dn in updates:
            conn.execute(text(
                f"UPDATE {TABLE_NAME} SET tick_diff=:td WHERE time=:t"
            ), {'td': td, 't': tval})
            updated += 1
            if updated % 500 == 0:
                print(f'  {updated}/{total}...')
        conn.commit()

    print(f'Done! Updated {updated} rows.')

    # 6. Verify
    with engine.connect() as conn:
        result = conn.execute(text(
            f'SELECT time, tick_diff, cur_up, cur_down FROM {TABLE_NAME} ORDER BY time DESC LIMIT 5'
        ))
        print('\n=== Latest 5 rows ===')
        for r in result.fetchall():
            print(f'  time={r[0]}, tick_diff={r[1]}, up={r[2]}, down={r[3]}')


if __name__ == '__main__':
    main()
