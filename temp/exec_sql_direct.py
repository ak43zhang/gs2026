#!/usr/bin/env python3
"""直接执行SQL"""
import pymysql

conn = pymysql.connect(
    host='192.168.0.101',
    port=3306,
    user='root',
    password='123456',
    database='gs',
    charset='utf8'
)

try:
    with conn.cursor() as cursor:
        # 检查字段是否存在
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema = 'gs' 
              AND table_name = 'quant_screen_hits' 
              AND column_name = 'hit_seq_today'
        """)
        exists = cursor.fetchone()[0]
        
        if not exists:
            cursor.execute("""
                ALTER TABLE quant_screen_hits 
                ADD COLUMN hit_seq_today INT DEFAULT 1 COMMENT '当天命中序号'
            """)
            conn.commit()
            print("✓ 添加 hit_seq_today 字段成功")
        else:
            print("✓ hit_seq_today 字段已存在")
        
        # 检查索引是否存在
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.statistics 
            WHERE table_schema = 'gs' 
              AND table_name = 'quant_screen_hits' 
              AND index_name = 'idx_bond_date_time'
        """)
        index_exists = cursor.fetchone()[0]
        
        if not index_exists:
            cursor.execute("""
                CREATE INDEX idx_bond_date_time 
                ON quant_screen_hits(bond_code, trade_date, tick_time)
            """)
            conn.commit()
            print("✓ 创建索引 idx_bond_date_time 成功")
        else:
            print("✓ 索引 idx_bond_date_time 已存在")
    
    print("✓ 数据库变更完成")
finally:
    conn.close()
