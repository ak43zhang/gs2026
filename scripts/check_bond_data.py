import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 查看 data_bond_qs_jsl 完整字段
    result = conn.execute(text('SHOW COLUMNS FROM data_bond_qs_jsl'))
    cols = result.fetchall()
    print('=== data_bond_qs_jsl 完整字段 ===')
    for c in cols:
        print(f'  {c[0]:30s} {c[1]}')
    
    # 查看数据量
    result2 = conn.execute(text('SELECT COUNT(*) FROM data_bond_qs_jsl'))
    print(f'\n总记录数: {result2.fetchone()[0]}')
    
    # 样例数据
    result3 = conn.execute(text(
        "SELECT `代码`,`名称`,`现价`,`正股代码`,`正股名称`,`转股价`,`正股价`,"
        "`剩余规模`,`转股起始日`,`强赎状态` "
        "FROM data_bond_qs_jsl "
        "WHERE `现价` IS NOT NULL AND `现价` > 0 "
        "LIMIT 5"
    ))
    print('\n=== 样例数据 ===')
    for r in result3.fetchall():
        print(f'  {r[0]} {r[1]} | 现价:{r[2]} | 正股:{r[3]} {r[4]} | 转股价:{r[5]} | 正股价:{r[6]} | 剩余:{r[7]}亿 | 强赎:{r[9]}')
    
    # 统计正股代码格式
    result4 = conn.execute(text(
        "SELECT `正股代码`, `正股名称` FROM data_bond_qs_jsl WHERE `正股代码` IS NOT NULL LIMIT 10"
    ))
    print('\n=== 正股代码格式 ===')
    for r in result4.fetchall():
        print(f'  {r[0]} → {r[1]}')
