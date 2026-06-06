"""涨停板数据AI分析模块 —— 火山方舟版本。

完全对齐 DeepSeek 版逻辑，仅替换 AI 调用层：
  - 不调用浏览器，走火山方舟 HTTP API
  - 删除敏感词替换
  - 删除 JSON 清理（直接 json.loads）
  - 其余逻辑（逐只分析、幂等入库、拆分、轮询）完全一致
"""

import json
import time
import warnings
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import List, Tuple, Any

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (mysql_util, config_util, email_util,
                          pandas_display_config, log_util, string_util)
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
from gs2026.analysis.worker.message.deepseek.result_processor import process_ztb
from gs2026.utils.task_runner import run_daemon_task

warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url: str = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)
email_util_inst = email_util.EmailUtil()


def volcengine_ai(
    query_list: List[Tuple[str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool = True
) -> None:
    """火山方舟AI涨停板分析（接口与 deepseek_ai 完全一致）"""

    for i in query_list:
        start = time.time()
        stock_name: str = i[0]
        sj: str = i[1]
        stock_sj_id: str = string_util.generate_md5(stock_name + sj)

        # 构建涨停分析Prompt（与DeepSeek版完全一致）
        query = sj + stock_name + """涨停受到哪些消息影响，这些消息分别最早出现在哪天，以及未来可能影响涨停的预期消息，预期消息是否有延续性（是，否）,
        只给出涨停前后5天的消息，请将结果简练成时间，消息简化到能准确知道是什么事件即可，消息简化在20个字以内，
        股性分析（该股票的股性做超短是否会套人）。
        龙虎榜分析（如果当日有龙虎榜则给出龙虎榜分析，如果没有则设置为无）。
        该涨停受到什么板块消息刺激而涨停,板块使用同花顺对应的板块名称。
        该涨停受到什么概念消息刺激而涨停,板块使用同花顺对应的板块或者概念名称。
        该涨停受到哪个龙头股的消息刺激而涨停。
        板块消息（板块字典：""" + bk_dic_str + """）。
        概念消息（概念字典：""" + gn_dic_str + """）。
        深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该股票今日为何涨停,深度分析结果按照前面的维度+详细分析原因组成)
        后面括号中的数据是深度分析结果格式样例：(政策支持： 一线城市限购优化、房企化债进展等政策密集出台，精准刺激公司核心市场。)
        返回结果为json对象，json 结构为：
        {
            "股票名称"："",
            "股票代码"："",
            "涨停时间":"",
            "股性分析":"",
            "龙虎榜分析":"",
            "板块消息":["板块":"","板块刺激消息":[""]],
            "概念消息":["概念":"","概念刺激消息":[""]],
            "龙头股消息":["龙头股":"","龙头股刺激消息":[""]],
            "消息":["影响消息":"","最早出现时间":""],
            "预期涨停消息":["预期消息":"","最早出现时间":""，"延续性":""],
            "深度分析":[""]
        }
        
        结果返回能直接复制的完整的json数据。
        """

        # 调用火山方舟API（无敏感词替换）
        logger.info(f"[火山方舟-涨停] 开始分析: {sj} {stock_name}")
        try:
            analysis: str = volcengine_analysis(query)
        except Exception as e:
            logger.error(f"[火山方舟-涨停] API调用异常: {e}")
            continue

        if not analysis or analysis.strip() in ('', '{}'):
            logger.error(f"[火山方舟-涨停] 返回空结果: {sj} {stock_name}")
            continue

        # 直接解析JSON（无清理步骤）
        json_data = analysis.strip()

        try:
            if json_data and json_data != '{}':
                # 幂等更新：先删旧记录再插入
                delete_sql = f"delete from {analysis_table_name} where gpjc_sj_id='{stock_sj_id}'"
                mysql_tool.delete_data(delete_sql)

                update_sql1 = (
                    f"INSERT INTO {analysis_table_name} (gpjc_sj_id,gpjc,sj,json_data) "
                    f"VALUES ('{stock_sj_id}','{stock_name}','{sj}',"
                    f"'{json_data.replace(chr(39), chr(39)+chr(39))}')"
                )
                mysql_tool.update_data(update_sql1)

                # 标记source表已分析
                update_sql2 = f"UPDATE {table_name} SET analysis='1' WHERE `股票简称`='{stock_name}' and `trade_date`='{sj}'"
                mysql_tool.update_data(update_sql2)
                logger.info(f"[火山方舟-涨停] 更新{table_name}表1条: {stock_sj_id}")

                # 拆分入库
                try:
                    json_obj = json.loads(json_data)
                    stock_code = json_obj.get('股票代码', '')
                    stats = process_ztb(json_data, stock_name, sj, stock_code, version='volcengine-1.0.0')
                    logger.info(f"[火山方舟-涨停] 拆分入库完成: {stats}")
                except Exception as e:
                    logger.error(f"[火山方舟-涨停] 拆分入库失败: {e}")
            else:
                logger.error(f"[火山方舟-涨停] 分析失败: {table_name} {stock_name} {sj}")

        except JSONDecodeError:
            logger.error(f"[火山方舟-涨停] JSON解析失败,JSONDecodeError: {stock_name} {sj}")
        except KeyError:
            logger.error(f"[火山方舟-涨停] JSON解析失败,KeyError: {stock_name} {sj}")
        except Exception as e:
            logger.error(f"[火山方舟-涨停] 处理异常: {type(e).__name__}: {e}")

        elapsed = time.time() - start
        logger.info(f"[火山方舟-涨停] {table_name}分析耗时: {elapsed:.2f}秒")


def get_news_ztb_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date_: str,
    end_date_: str,
    _headless: bool = True
) -> bool:
    """查询未分析的涨停板数据并触发AI分析"""
    sql = f"""(select SQL_NO_CACHE `股票简称`,`trade_date` from {table_name}
                    where (analysis is null or analysis='')
                    and trade_date between '{start_date_}' and '{end_date_}' )
                union
                (select SQL_NO_CACHE gpjc as `股票简称`,sj as `trade_date` from {analysis_table_name}
                    where (json_data is null or json_data='')
                    and sj between '{start_date_}' and '{end_date_}' )
                order by RAND() limit 1"""
    bk_dic_sql = "select name from data_industry_code_ths"
    gn_dic_sql = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        bk_dic_str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))
        if len(lists) != 0:
            volcengine_ai(lists, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
            return True
        else:
            return False


def time_task_do_ztb(date_param: str, start_date_: str, end_date_: str, polling_time: int) -> None:
    """轮询执行涨停板AI分析，直到无数据退出"""
    while True:
        year = date_param[0:4]
        has_more = get_news_ztb_analysis("ztb_day", "analysis_ztb" + year, start_date_, end_date_, True)
        if not has_more:
            logger.info(f"[火山方舟-涨停] {date_param} 所有数据已分析完成，任务结束")
            break
        time.sleep(polling_time)


def analysis_ztb(date_list_: List[str]) -> None:
    """批量执行涨停板AI分析入口"""
    for area_date in date_list_:
        logger.info('=' * 30 + area_date + '=' * 30)
        time_task_do_ztb(area_date, area_date, area_date, 10)


if __name__ == "__main__":
    import argparse
    import json as json_lib
    from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_date_list

    parser = argparse.ArgumentParser(description='涨停板数据分析-火山方舟版')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()

    date_list = get_date_list()  # 默认：上一交易日到下一交易日

    if args.params:
        try:
            params = json_lib.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json_lib.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')

    run_daemon_task(target=analysis_ztb, args=(date_list,))
