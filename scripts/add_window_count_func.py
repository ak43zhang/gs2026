"""
添加 _get_bond_window_count_batch 函数到 monitor.py
"""

new_function = '''

def _get_bond_window_count_batch(date: str, time_str: str, bond_codes: list) -> dict:
    """
    批量获取债券的window_count（取截止时间的最新值）
    
    Args:
        date: 日期 YYYYMMDD
        time_str: 截止时间 HH:MM:SS
        bond_codes: 债券代码列表
    
    Returns:
        {bond_code: window_count} 字典
    """
    if not bond_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import create_engine, text
        from gs2026.utils import config_util
        
        url = config_util.get_config('common.url')
        engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
        table_name = f"monitor_zq_top30_{date}"
        
        # 批量查询：取每个债券截止时间的最新window_count
        codes_str = "','".join(bond_codes)
        sql = f"""
            SELECT t1.code, t1.window_count
            FROM {table_name} t1
            INNER JOIN (
                SELECT code, MAX(time) as max_time
                FROM {table_name}
                WHERE code IN ('{codes_str}') AND time <= '{time_str}'
                GROUP BY code
            ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return {row[0]: row[1] for row in result}
            
    except Exception as e:
        print(f"批量获取债券window_count失败: {e}")
        return {}

'''

# 读取文件
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到插入位置（在 _enrich_bond_data 函数之前）
insert_marker = 'def _enrich_bond_data(bonds: list, date: str, time_str: str = None) -> list:'
if insert_marker in content:
    # 在 marker 之前插入新函数
    content = content.replace(insert_marker, new_function + insert_marker)
    
    # 写入文件
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("函数添加成功")
else:
    print("未找到插入位置")
