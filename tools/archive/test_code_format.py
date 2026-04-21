import sys
sys.path.insert(0, 'src')

# 测试集思录数据源
print("=== 测试集思录数据源 ===")
try:
    import akshare as ak
    df_jsl = ak.bond_cb_jsl()
    print(f"列名: {df_jsl.columns.tolist()}")
    print(f"代码列名: {[c for c in df_jsl.columns if 'code' in c.lower() or '代码' in c]}")
    # 找到代码列
    code_col = None
    for c in df_jsl.columns:
        if 'code' in c.lower() or '代码' in c:
            code_col = c
            break
    if code_col:
        print(f"代码示例: {df_jsl[code_col].head(5).tolist()}")
        print(f"代码类型: {df_jsl[code_col].dtype}")
except Exception as e:
    print(f"集思录获取失败: {e}")

# 测试adata数据源
print("\n=== 测试adata数据源 ===")
try:
    import adata
    df_adata = adata.bond.market.list_market_current()
    print(f"列名: {df_adata.columns.tolist()}")
    if 'bond_code' in df_adata.columns:
        print(f"代码示例: {df_adata['bond_code'].head(5).tolist()}")
        print(f"代码类型: {df_adata['bond_code'].dtype}")
except Exception as e:
    print(f"adata获取失败: {e}")
