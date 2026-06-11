"""验证绿名单查询逻辑"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from datetime import datetime
import pandas as pd
from gs2026.utils.mysql_util import get_mysql_tool

# 测试日期
test_dates = ['20260609', '20260610', '20260611']

mysql_tool = get_mysql_tool()

for actual_date in test_dates:
    print(f"\n=== 测试日期: {actual_date} ===")
    
    # 当前代码的查询方式（字符串）
    date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"
    print(f"字符串格式: '{date_sql}'")
    
    query_str = f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'"
    print(f"SQL: {query_str}")
    
    try:
        df = pd.read_sql(query_str, con=mysql_tool.engine)
        print(f"字符串查询结果: {len(df)} 条")
        if len(df) > 0:
            print(f"样本: {df['code'].head(3).tolist()}")
    except Exception as e:
        print(f"字符串查询错误: {e}")
    
    # 正确的查询方式（date对象）
    try:
        date_obj = datetime.strptime(actual_date, '%Y%m%d').date()
        print(f"\ndate对象格式: {date_obj} (type: {type(date_obj)})")
        
        query_param = "SELECT DISTINCT code FROM green_bond_list WHERE buy_date=%s"
        df2 = pd.read_sql(query_param, con=mysql_tool.engine, params=(date_obj,))
        print(f"参数化查询结果: {len(df2)} 条")
        if len(df2) > 0:
            print(f"样本: {df2['code'].head(3).tolist()}")
    except Exception as e:
        print(f"参数化查询错误: {e}")

print("\n=== 验证完成 ===")
