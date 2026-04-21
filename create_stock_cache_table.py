#!/usr/bin/env python3
"""创建宽表"""
import sys
sys.path.insert(0, 'src')

from sqlalchemy import text
from gs2026.utils import mysql_util

mysql_tool = mysql_util.get_mysql_tool()

sql = """
CREATE TABLE IF NOT EXISTS cache_stock_industry_concept_bond (
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(20) DEFAULT NULL,
    industry_codes JSON DEFAULT NULL,
    industry_names JSON DEFAULT NULL,
    concept_codes JSON DEFAULT NULL,
    concept_names JSON DEFAULT NULL,
    bond_code VARCHAR(10) DEFAULT NULL,
    bond_name VARCHAR(50) DEFAULT NULL,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_code),
    KEY idx_update_time (update_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

try:
    with mysql_tool.engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print("OK")
except Exception as e:
    print(f"Error: {e}")
