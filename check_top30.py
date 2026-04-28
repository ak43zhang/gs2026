#!/usr/bin/env python3
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_top30_20260428 WHERE time = '15:00:00'")).fetchone()
    print(f'Records at 15:00:00: {result[0]}')
    
    result2 = conn.execute(text("SELECT code, name, total_score_rank FROM monitor_gp_top30_20260428 WHERE time = '15:00:00' ORDER BY total_score_rank ASC LIMIT 5")).fetchall()
    print('Top 5:')
    for row in result2:
        print(f'  {row[0]} {row[1]}: rank={row[2]}')
