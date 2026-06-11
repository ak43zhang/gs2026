"""修复 at-time 路由绿名单查询逻辑"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', encoding='utf-8') as f:
    content = f.read()

old_text = """            # 【新增】标记绿名单

            try:

                from gs2026.dashboard2.routes.green_bond_list_cache import get_green_bond_list

                green_bond_list = get_green_bond_list()

                for item in data:

                    item['is_green'] = item.get('code', '') in green_bond_list

            except Exception:

                for item in data:

                    item['is_green'] = False"""

new_text = """            # 【修复】标记绿名单（根据日期选择数据源：当天Redis/历史MySQL）

            try:

                from gs2026.dashboard2.routes.green_bond_list_cache import (

                    get_green_bond_list, get_green_bond_list_cache_date

                )

                cache_date = get_green_bond_list_cache_date()

                if cache_date == actual_date:

                    green_bond_list = get_green_bond_list()

                else:

                    from gs2026.utils.mysql_util import get_mysql_tool

                    mysql_tool = get_mysql_tool()

                    date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"

                    df = pd.read_sql(

                        f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'",

                        con=mysql_tool.engine

                    )

                    green_bond_list = set(df['code'].astype(str).str.zfill(6).tolist()) if not df.empty else set()

                for item in data:

                    item['is_green'] = item.get('code', '') in green_bond_list

            except Exception as e:

                logger.warning(f"at-time绿名单标记失败: {e}")

                for item in data:

                    item['is_green'] = False"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK')
else:
    print('NOT FOUND')
