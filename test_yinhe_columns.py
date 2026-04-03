import sys
sys.path.insert(0, 'src')
import yinhedata as yh
import pandas as pd

# 测试银河数据返回的字段
try:
    # 不传参数获取所有可转债
    df = yh.realtime_kzz_data()
    print("Columns:", df.columns.tolist())
    print("\nData sample:")
    print(df.head(2).to_string())
    print("\nData types:")
    print(df.dtypes)
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
