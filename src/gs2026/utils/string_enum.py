"""
字符串常量枚举模块

定义项目中使用的各种字符串常量，包括SQL查询语句和浏览器路径。
"""
from typing import Final
import getpass

user = getpass.getuser()

# 股票sql，获取a股深圳，上海的股票代码，去掉退市，st，总市值大于300亿,去掉大市值
AG_STOCK_SQL1: Final[str] = "select stock_code,list_date from data_agdm where (stock_code like '00%' or stock_code like '60%' or stock_code like '30%') and short_name not like '%退%' and short_name not like '%ST%' and list_date is not null and stock_code not in (select `代码` from dashizhi_20250224 )"

# A股 沪股 深股 创业板的股票
AG_STOCK_SQL3: Final[str] = "select stock_code,list_date from data_agdm where (stock_code like '00%' or stock_code like '60%' or stock_code like '30%') and list_date is not null"
# 沪深 主板 没退市
AG_STOCK_SQL4: Final[str] = "select stock_code,list_date from data_agdm where (stock_code like '00%' or stock_code like '60%') and list_date is not null"

AG_STOCK_SQL5: Final[str] = "select stock_code,list_date from data_agdm where list_date is not null"

# 火狐浏览器路径 可切换版本
FIREFOX_PATH_1408 = f"C:/Users/{user}/AppData/Local/ms-playwright/firefox-1408/firefox/firefox.exe"
FIREFOX_PATH_1466 = f"C:/Users/{user}/AppData/Local/ms-playwright/firefox-1466/firefox/firefox.exe"
FIREFOX_PATH_1509 = f"C:/Users/{user}/AppData/Local/ms-playwright/firefox-1509/firefox/firefox.exe"

CHROME_PATH_1208 = f"C:/Users/{user}/AppData/Local/ms-playwright/chromium-1208/chrome-win64/chrome.exe"
