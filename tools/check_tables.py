"""
检查表列和数据，填充正确的今日数据
"""
import json, hashlib
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 检查可用的股票表
    result = conn.execute(text("SHOW TABLES LIKE 'monitor_gp_sssj_%' OR SHOW TABLES LIKE 'stock_info%' OR SHOW TABLES LIKE 'stock_code*' OR SHOW TABLES LIKE 'stock_bond*'"))
    for row in result:
        print(row[0])
    
    # 搜索包含股票名称的表
    result = conn.execute(text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='gs' AND TABLE_NAME LIKE '%stock%' AND TABLE_NAME NOT LIKE '%monitor%'"))
    print("\nStock-related tables:")
    for row in result:
        print(f"  {row[0]}")
    
    result = conn.execute(text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='gs' AND TABLE_NAME LIKE '%code%'"))
    print("\nCode-related tables:")
    for row in result:
        print(f"  {row[0]}")
    
    result = conn.execute(text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='gs' AND TABLE_NAME LIKE '%name*' OR TABLE_NAME LIKE '%bond%map'"))
    print("\nBond mapping tables:")
    for row in result:
        print(f"  {row[0]}")
