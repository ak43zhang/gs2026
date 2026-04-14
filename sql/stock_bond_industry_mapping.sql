-- 股票、债券、行业 1对1对1 关联查询
-- 表: data_industry_code_component_ths (行业成分股) 和 data_bond_ths (债券数据)

-- 方法1: 使用 INNER JOIN 保持 1对1对1 关系
-- 假设关联字段: stock_code (股票代码)
SELECT 
    ic.stock_code,                          -- 股票代码
    ic.short_name,                          -- 股票简称
    b.bond_code,                            -- 债券代码
    b.bond_name,                            -- 债券简称
    ic.name AS industry_name                -- 行业名称
FROM data_industry_code_component_ths ic
INNER JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code         -- 通过股票代码关联
ORDER BY ic.stock_code;

-- 方法2: 如果债券表中没有 stock_code 字段，使用债券代码关联
-- 假设债券代码中包含股票代码（如: 128XXX 对应股票代码）
SELECT 
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name AS industry_name
FROM data_industry_code_component_ths ic
INNER JOIN data_bond_ths b 
    ON SUBSTRING(b.bond_code, 1, 6) = ic.stock_code  -- 债券代码前6位匹配股票代码
ORDER BY ic.stock_code;

-- 方法3: 如果有关联表，使用关联表连接
-- 假设有 bond_stock_relation 关联表
SELECT 
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name AS industry_name
FROM data_industry_code_component_ths ic
INNER JOIN bond_stock_relation rel 
    ON ic.stock_code = rel.stock_code
INNER JOIN data_bond_ths b 
    ON rel.bond_code = b.bond_code
ORDER BY ic.stock_code;

-- 方法4: 使用 LEFT JOIN 确保所有股票都有记录（即使无对应债券）
SELECT 
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name AS industry_name
FROM data_industry_code_component_ths ic
LEFT JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
ORDER BY ic.stock_code;

-- Python pandas 实现
"""
import pandas as pd
from gs2026.utils.mysql_util import mysql_tool

# 读取行业成分股数据
df_industry = mysql_tool.query_to_dataframe('''
    SELECT stock_code, short_name, name AS industry_name 
    FROM data_industry_code_component_ths
''')

# 读取债券数据
df_bond = mysql_tool.query_to_dataframe('''
    SELECT bond_code, bond_name, stock_code 
    FROM data_bond_ths
''')

# 合并数据（1对1对1关系）
df_result = pd.merge(
    df_industry, 
    df_bond, 
    on='stock_code', 
    how='inner'  # 只保留两边都有的记录
)

# 重命名列
df_result = df_result.rename(columns={
    'name': 'industry_name'
})

# 选择需要的列
df_result = df_result[['stock_code', 'short_name', 'bond_code', 'bond_name', 'industry_name']]

print(df_result)
"""
