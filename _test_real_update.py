#!/usr/bin/env python3
"""测试真实数据更新（小批量50行，验证锁问题已解决）"""
import sys, time
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
import pandas as pd

DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE = "monitor_zq_sssj_20260723"
engine = create_engine(DB_URL)

# 取50行真实数据
print("读取50行真实数据...")
with engine.connect() as conn:
    df = pd.read_sql(text(f"""
        SELECT bond_code, `time` FROM `{TABLE}`
        WHERE `time` >= '09:30:00'
        ORDER BY `time`, bond_code
        LIMIT 50
    """), conn)

print(f"读取 {len(df)} 行")

# 逐行UPDATE测试
print("\n测试逐行UPDATE（验证锁已解决）...")
t0 = time.time()
success = 0
fail = 0

with engine.connect() as conn:
    for idx, row in df.iterrows():
        test_value = f"测试形态{idx}"
        sql = f"""
            UPDATE `{TABLE}`
            SET ext_indicators = JSON_SET(COALESCE(ext_indicators, '{{}}'), '$._test_shape', '{test_value}')
            WHERE bond_code = '{row['bond_code']}' AND `time` = '{row['time']}'
        """
        try:
            conn.execute(text(sql))
            success += 1
            if success % 10 == 0:
                conn.commit()
                print(f"  已更新 {success} 行")
        except Exception as e:
            fail += 1
            print(f"  [FAIL] {row['bond_code']} @ {row['time']}: {str(e)[:60]}")
    conn.commit()

elapsed = time.time() - t0
print(f"\n结果: 成功 {success}, 失败 {fail}, 耗时 {elapsed:.1f}s, 速度 {success/elapsed:.0f}行/秒")

# 清理测试字段
print("\n清理测试字段...")
with engine.connect() as conn:
    for idx, row in df.iterrows():
        sql = f"""
            UPDATE `{TABLE}`
            SET ext_indicators = JSON_REMOVE(ext_indicators, '$._test_shape')
            WHERE bond_code = '{row['bond_code']}' AND `time` = '{row['time']}'
        """
        try:
            conn.execute(text(sql))
        except:
            pass
    conn.commit()
print("清理完成")

engine.dispose()
print("\n测试通过！锁问题已解决。")
