import sys
sys.path.insert(0, 'src')
import yinhedata as yh
import pandas as pd

# 测试银河数据返回的字段
try:
    # 测试几个可转债代码
    bond_codes = ["SH.113034", "SH.113561"]
    df = yh.realtime_kzz_data(bond_codes)
    print("Columns:", df.columns.tolist())
    print("\nData shape:", df.shape)
    print("\nData:")
    print(df.to_string())
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
