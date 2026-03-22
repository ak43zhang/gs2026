"""
股票日数据收集
"""
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.constants import FIREFOX_1509
from gs2026.utils import mysql_util, config_util, log_util, string_enum
from gs2026.utils.config_util import get_config
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

config = get_config
url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
browser_path = FIREFOX_1509
mysql_tool = mysql_util.MysqlTool(url)


def get_stock_data(stock_code: str) -> Optional[Dict]:
    """
    获取单只A股股票的实时数据
    :param stock_code: 6位股票代码 (如: 600519)
    :return: 包含股票数据的字典 (失败返回None)
    """
    # 根据股票代码确定市场前缀
    market = "sh" if stock_code.startswith(("6", "9")) else "sz"

    # 新浪财经API URL
    url = f"http://hq.sinajs.cn/list={market}{stock_code}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "http://finance.sina.com.cn/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "gbk"

        if response.status_code != 200:
            print(f"请求失败，状态码: {response.status_code}")
            return None

        # 解析数据 (格式: var hq_str_sh600519="茅台,1799.01,1795.00,...")
        raw_data = response.text.split('"')[1]
        if not raw_data:
            print("未获取到有效数据")
            return None

        data_fields = raw_data.split(",")

        # 数据字段映射
        stock_data = {
            "stock_code": stock_code,
            "name": data_fields[0],
            "trade_time":datetime.now().strftime("%Y-%m-%d")+" 00:00:00",
            "trade_date":datetime.now().strftime("%Y-%m-%d"),
            "open": float(data_fields[1]),  # 今日开盘价
            "close": float(data_fields[3]),  # 当前价格
            "high": float(data_fields[4]),  # 今日最高价
            "low": float(data_fields[5]),  # 今日最低价
            "volume": int(data_fields[8]),  # 成交量(手)
            "amount": float(data_fields[9]),  # 成交额(元)
            "change": float(data_fields[3]) - float(data_fields[2]),  # 当前价-昨收
            "change_pct": round((float(data_fields[3]) - float(data_fields[2])) / (float(data_fields[2])), 4)*100,
            "pre_close": float(data_fields[2]),  # 昨日收盘价
        }

        # 添加换手率 (需要额外接口)
        turnover = get_turnover_rate(stock_code)
        if turnover is not None:
            stock_data["turnover_ratio"] = f"{turnover}%"

        return stock_data

    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
        return None


def get_turnover_rate(stock_code: str) -> Optional[float]:
    """
    获取换手率 (使用腾讯财经接口)
    :param stock_code: 6位股票代码
    :return: 换手率百分比 (失败返回None)
    """
    market = "sh" if stock_code.startswith("6") else "sz"
    url = f"http://qt.gtimg.cn/q={market}{stock_code}"

    try:
        response = requests.get(url, timeout=5)
        response.encoding = "gbk"
        data = response.text.split("~")

        # 换手率在腾讯接口的第38个位置
        if len(data) > 38:
            return float(data[38])  # 注意索引从0开始
    except:
        return None


def get_multiple_stocks(stock_codes: list) -> pd.DataFrame:
    """
    批量获取多只股票数据
    :param stock_codes: 股票代码列表
    :return: 包含所有股票数据的DataFrame
    """
    results = []
    for code in stock_codes:
        if len(code) != 6 or not code.isdigit():
            print(f"跳过无效代码: {code}")
            continue

        print(f"正在获取 {code} 数据...")
        data = get_stock_data(code)
        if data:
            results.append(data)

    return pd.DataFrame(results)


if __name__ == "__main__":
    table_name = f'data_gpsj_day_' + datetime.now().strftime("%Y-%m-%d").replace("-", "")
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)

    sql = string_enum.AG_STOCK_SQL1
    dm_kpsj_df = pd.read_sql(sql, con=con)
    dm_list = dm_kpsj_df.values.tolist()

    stock_codes = [x[0] for x in dm_list][1:30]
    print(stock_codes)
    # 示例股票代码 (茅台, 平安, 宁德时代)
    # stock_codes = ["600519", "000001", "300750"]

    # 获取股票数据
    df = get_multiple_stocks(stock_codes)[["stock_code","trade_time","trade_date", "open", "close", "high", "low", "volume","amount","change_pct","change","turnover_ratio","pre_close"]]

    # 打印结果
    if not df.empty:
        print("\n获取到的股票数据:")
        print(df)
    else:
        print("未获取到有效数据")

