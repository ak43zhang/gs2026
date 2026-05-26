import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Replace bond MySQL query
old = '''def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:
    """从MySQL批量查询债券涨跌幅"""
    try:
        from sqlalchemy import create_engine, text
        from ..config import Config

        engine = create_engine(Config.MYSQL_URI)
        table_name = f"monitor_zq_sssj_{date}"

        # 批量查询（使用IN语句）
        codes_str = ','.join([f"'{code}'" for code in bond_codes])
        sql = text(f"""
            SELECT bond_code, change_pct
            FROM {table_name}
            WHERE time = :time_str AND bond_code IN ({codes_str})
        """)'''

new = '''def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:
    """从MySQL批量查询债券涨跌幅和价格"""
    try:
        from sqlalchemy import create_engine, text
        from ..config import Config

        engine = create_engine(Config.MYSQL_URI)
        table_name = f"monitor_zq_sssj_{date}"

        # 批量查询（使用IN语句）
        codes_str = ','.join([f"'{code}'" for code in bond_codes])
        sql = text(f"""
            SELECT bond_code, change_pct, price
            FROM {table_name}
            WHERE time = :time_str AND bond_code IN ({codes_str})
        """)'''

if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print('OK: bond MySQL query updated')
else:
    print('SKIP: not found')
