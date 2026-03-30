#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看 data_gpsj_day_20260316 表结构"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    print("=" * 80)
    print("表结构: data_gpsj_day_20260316")
    print("=" * 80)
    
    # 查看表结构
    result = conn.execute(text("DESCRIBE data_gpsj_day_20260316"))
    print("\n字段信息:")
    print(f"{'Field':<20} {'Type':<20} {'Null':<8} {'Key':<10} {'Default':<15} {'Extra'}")
    print("-" * 80)
    
    fields = []
    for row in result:
        fields.append({
            'field': row[0],
            'type': row[1],
            'null': row[2],
            'key': row[3],
            'default': row[4],
            'extra': row[5]
        })
        print(f"{row[0]:<20} {row[1]:<20} {row[2]:<8} {row[3]:<10} {str(row[4]):<15} {row[5]}")
    
    # 查看索引
    print("\n\n索引信息:")
    result = conn.execute(text("SHOW INDEX FROM data_gpsj_day_20260316"))
    print(f"{'Key_name':<20} {'Column_name':<20} {'Non_unique':<12} {'Index_type'}")
    print("-" * 80)
    
    for row in result:
        print(f"{row[2]:<20} {row[4]:<20} {row[1]:<12} {row[10]}")
    
    # 查看样本数据
    print("\n\n样本数据 (前3条):")
    result = conn.execute(text("SELECT * FROM data_gpsj_day_20260316 LIMIT 3"))
    rows = result.fetchall()
    if rows:
        for i, row in enumerate(rows):
            print(f"\n记录 {i+1}:")
            for j, field in enumerate(fields):
                print(f"  {field['field']}: {row[j]}")
    
    print("\n" + "=" * 80)
    
    # 生成字段映射文档
    print("\n\n字段映射文档 (用于数据源适配):")
    print("-" * 80)
    for field in fields:
        print(f"{field['field']}: {field['type']}")
