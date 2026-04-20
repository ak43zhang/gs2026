"""
实时监控获取行业数据——同花顺
"""
import warnings
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.monitor import monitor_stock as msac
from gs2026.utils import log_util, pandas_display_config, config_util, mysql_util, redis_util

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config('common.url')
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接
try:
    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
except Exception as e:
    logger.error(f"Redis 初始化失败: {e}")
    sys.exit(1)

# ------------------------------
# 配置参数
INTERVAL = 3           # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
WINDOW_SECONDS = 15

SOURCE_INDUSTRY_FULL_COLUMNS = ['code', '板块', '涨跌幅','总成交量','总成交额','净流入','上涨家数','下跌家数','均价', '领涨股']

hy_dict_df = redis_util.get_dict("data_industry_code_ths")
if hy_dict_df is None:
    logger.error("无法获取行业字典数据(data_industry_code_ths)，程序退出")
    sys.exit(1)

"""
stock_board_industry_summary_ths 并发优化版本，用于替换akshare中分页导致数据重复和缺失的问题（行业）
"""
# def stock_board_industry_summary_ths() -> pd.DataFrame:
#     """
#     同花顺-数据中心-行业板块-同花顺行业一览表
#     通过多次请求合并去重，确保返回完整的90个行业。
#     :return: 同花顺行业一览表
#     :rtype: pandas.DataFrame
#     """
#     import time
#     js_code = py_mini_racer.MiniRacer()
#     js_content = _get_file_content_ths("ths.js")
#     js_code.eval(js_content)
#     v_code = js_code.call("v")
#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
#                       "Chrome/89.0.4389.90 Safari/537.36",
#         "Cookie": f"v={v_code}",
#     }
#
#     # 获取总页数
#     first_url = "http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/1/ajax/1/"
#     r = requests.get(first_url, headers=headers)
#     soup = BeautifulSoup(r.text, features="lxml")
#     page_info = soup.find(name="span", attrs={"class": "page_info"})
#     if page_info is None:
#         raise ValueError("无法解析页数信息，页面结构可能已变化")
#     total_pages = int(page_info.text.split("/")[1])
#
#     # 标准列名（与最终输出一致）
#     STANDARD_COLUMNS = [
#         "序号", "板块", "涨跌幅", "总成交量", "总成交额", "净流入",
#         "上涨家数", "下跌家数", "均价", "领涨股", "领涨股-最新价", "领涨股-涨跌幅"
#     ]
#
#     max_attempts = 5  # 最大尝试次数
#     all_data_dfs = []  # 存储每次尝试的完整DataFrame（两页合并）
#     final_df = pd.DataFrame()
#     tqdm = get_tqdm()
#
#     for attempt in range(max_attempts):
#         attempt_dfs = []
#         for page in tqdm(range(1, total_pages + 1), leave=False, desc=f"Attempt {attempt + 1}"):
#             url = f"http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/ajax/1/"
#
#             # 页内重试机制，最多3次
#             page_retries = 3
#             success = False
#             for retry in range(page_retries):
#                 try:
#                     r = requests.get(url, headers=headers, timeout=10)
#                     if r.status_code != 200:
#                         raise ValueError(f"HTTP状态码 {r.status_code}")
#
#                     # 尝试解析表格
#                     temp_df = pd.read_html(StringIO(r.text))[0]
#
#                     # 统一列名
#                     if temp_df.shape[1] == len(STANDARD_COLUMNS):
#                         temp_df.columns = STANDARD_COLUMNS
#                     else:
#                         raise ValueError(f"列数不匹配: {temp_df.shape[1]} ≠ {len(STANDARD_COLUMNS)}")
#
#                     attempt_dfs.append(temp_df)
#                     success = True
#                     break  # 成功则跳出重试循环
#                 except Exception as e:
#                     print(f"第{attempt + 1}次尝试的第{page}页请求失败 (重试 {retry + 1}/{page_retries}): {e}")
#                     if retry < page_retries - 1:
#                         time.sleep(1)  # 重试前等待
#                     else:
#                         print(f"第{page}页多次重试失败，跳过该页")
#
#             # 如果成功则继续，否则该页数据缺失（不添加到attempt_dfs）
#             # 此处无需额外操作，因为 success=False 时该页未被添加
#
#         if not attempt_dfs:
#             continue  # 本次尝试无任何有效页，跳过
#
#         attempt_df = pd.concat(attempt_dfs, ignore_index=True)
#         all_data_dfs.append(attempt_df)
#
#         # 合并所有尝试的数据，按“板块”去重（保留最后一次出现的记录）
#         combined = pd.concat(all_data_dfs, ignore_index=True)
#         combined = combined.drop_duplicates(subset=["板块"], keep='last')
#         final_df = combined
#
#         # 如果唯一行业数已达到90，提前结束
#         if len(final_df) >= 90:
#             break
#
#         # 若未达到且还有尝试次数，稍等片刻再试
#         if attempt < max_attempts - 1:
#             time.sleep(1)
#
#     # 若最终仍不足90，可记录警告或直接返回
#     if len(final_df) < 90:
#         print(f"警告：仅获取到 {len(final_df)} 个行业，未达到预期的90个")
#
#     # 数据类型转换
#     numeric_cols = [
#         "涨跌幅", "总成交量", "总成交额", "净流入", "上涨家数",
#         "下跌家数", "均价", "领涨股-最新价", "领涨股-涨跌幅"
#     ]
#     for col in numeric_cols:
#         final_df[col] = pd.to_numeric(final_df[col], errors="coerce")
#
#     return final_df

def get_industry_akshare():
    try:
        df = ak.stock_board_industry_summary_ths()
        df = (df.merge(hy_dict_df[['name', 'code']], left_on='板块', right_on='name', how='left')
              .drop(columns=['name', '领涨股-最新价', '领涨股-涨跌幅', '序号']))
        # 如果返回的是空 DataFrame，也视为无效数据
        if df is None or df.empty:
            df = None
    except Exception:
        df = None

    return df

def deal_hy_works(loop_start):
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        df_now = get_industry_akshare()
        if df_now.empty:
            # 数据为空，创建占位空DataFrame（包含后续计算所需的全部列）
            return
        else:
            df_now['code'] = df_now['code'].astype(str).str.zfill(6)
    except Exception as e:
        logger.error(f"获取股票数据异常: {e}")
        return

    df_now['time'] = time_full

    # 存储股票实时数据
    sssj_table = f"monitor_hy_sssj_{date_str}"
    msac.save_dataframe(df_now, sssj_table, time_full, EXPIRE_SECONDS)

    # 获取前N秒的数据（从 Redis 加载）
    # window_seconds_offset = (WINDOW_SECONDS + INTERVAL - 1) // INTERVAL
    # df_prev = redis_util.load_dataframe_by_offset(sssj_table, offset=window_seconds_offset, use_compression=False)

    # 计算并存储大盘强度
    # culculate_hy_apqd_top30(df_now, df_prev, date_str, time_full, loop_start)

def culculate_hy_apqd_top30(df_now, df_prev, date_str, time_full, loop_start):
    """
    计算大盘强度（APQD）和涨幅/涨速前30榜单，并存储。

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 30秒前数据（可能为空）。
        date_str (str): 日期字符串 YYYYMMDD。
        time_full (str): 时间字符串 HH:MM:SS。
        loop_start (datetime): 轮询开始时间。
    """
    # ---------- 列名标准化：将原始列名映射为统一名称 ----------
    rename_map = {}
    if '板块' in df_now.columns and 'name' not in df_now.columns:
        rename_map['板块'] = 'name'
    if '涨跌幅' in df_now.columns and 'change_pct' not in df_now.columns:
        rename_map['涨跌幅'] = 'change_pct'
    if '总成交量' in df_now.columns and 'volume' not in df_now.columns:
        rename_map['总成交量'] = 'volume'
    if '总成交额' in df_now.columns and 'amount' not in df_now.columns:
        rename_map['总成交额'] = 'amount'
    if '均价' in df_now.columns and 'price' not in df_now.columns:
        rename_map['均价'] = 'price'
    if rename_map:
        df_now = df_now.rename(columns=rename_map)
        if df_prev is not None and not df_prev.empty:
            df_prev = df_prev.rename(columns=rename_map)

    # ---------- 确保必要列存在 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        raise ValueError(f"df_now 缺少必要列 {required_cols}，当前列：{df_now.columns.tolist()}")

    # ---------- 计算大盘强度 ----------
    judge30 = msac.judge_market_strength(msac.get_market_stats(df_now, df_prev))
    apqd_table = f"monitor_hy_apqd_{date_str}"
    msac.save_dataframe(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    if df_prev is not None and not df_prev.empty:
        top30_df = msac.calculate_top30_v3(df_now, df_prev, loop_start)   # v3 内部已处理列名
        if not top30_df.empty:
            gp_top30_table = f"monitor_hy_top30_{date_str}"
            msac.save_dataframe(top30_df, gp_top30_table, time_full, EXPIRE_SECONDS)
            # 上攻排行
            result_df = msac.attack_conditions(top30_df, rank_name='industry')
            rank_result = redis_util.update_rank_redis(result_df, 'industry', date_str=date_str)
            # 收盘时保存到 MySQL
            if time_full == "15:00:00":
                msac.save_rank_to_mysql(rank_result, 'industry', date_str)



if __name__ == "__main__":
    msac.run_monitor_loop_synced(deal_hy_works, interval=INTERVAL)