"""查询三江转债和盛德转债的真实代码"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8')
with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT DISTINCT bond_code, bond_name FROM monitor_zq_sssj_20260717 "
        "WHERE bond_name LIKE :n1 OR bond_name LIKE :n2 LIMIT 10"
    ), {'n1': '%三江%', 'n2': '%盛德%'})
    rows = r.fetchall()
    for row in rows:
        print(f'{row[0]} = {row[1]}')
    
    if not rows:
        print('未找到，列出前10个债券:')
        r2 = conn.execute(text(
            "SELECT DISTINCT bond_code, bond_name FROM monitor_zq_sssj_20260717 LIMIT 10"
        ))
        for row in r2.fetchall():
            print(f'  {row[0]} = {row[1]}')
