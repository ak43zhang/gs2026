import sys
sys.path.insert(0, 'src')

# 获取集思录代码
try:
    import akshare as ak
    df_jsl = ak.bond_cb_jsl()
    codes_jsl = set(df_jsl['代码'].tolist())
    print(f"集思录代码数量: {len(codes_jsl)}")
    print(f"集思录代码示例: {list(codes_jsl)[:10]}")
except Exception as e:
    print(f"集思录获取失败: {e}")
    codes_jsl = set()

# 获取adata代码
try:
    import adata
    df_adata = adata.bond.market.list_market_current()
    codes_adata = set(df_adata['bond_code'].tolist())
    print(f"\nadata代码数量: {len(codes_adata)}")
    print(f"adata代码示例: {list(codes_adata)[:10]}")
except Exception as e:
    print(f"adata获取失败: {e}")
    codes_adata = set()

# 检查交集
if codes_jsl and codes_adata:
    common = codes_jsl & codes_adata
    print(f"\n共同代码数量: {len(common)}")
    print(f"共同代码示例: {list(common)[:10]}")
    print(f"集思录独有: {len(codes_jsl - codes_adata)}")
    print(f"adata独有: {len(codes_adata - codes_jsl)}")
