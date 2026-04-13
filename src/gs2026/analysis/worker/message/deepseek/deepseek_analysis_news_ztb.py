"""涨停板数据AI分析模块 - DeepSeek版本。

本模块负责对涨停板（ZTB）股票数据进行AI深度分析，通过DeepSeek大模型
解析涨停原因、板块消息、概念消息、龙头股影响等多维度信息。

核心功能:
    - 构建涨停板分析Prompt，调用DeepSeek模型进行智能分析
    - 解析AI返回的JSON结果并持久化到数据库
    - 支持按日期范围批量轮询分析未处理的涨停数据
    - 异常时自动发送邮件告警

依赖关系:
    - gs2026.utils: MySQL工具、配置管理、邮件工具、日志工具等
    - gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven: DeepSeek分析引擎
    - pandas / sqlalchemy: 数据读取与数据库连接

"""
import os
import time
import warnings
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import List, Tuple, Any

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (mysql_util,
                          config_util,
                          email_util,
                          pandas_display_config,
                          log_util,
                          string_enum,
                          string_util)
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven
from gs2026.analysis.worker.message.deepseek.result_processor import process_ztb
from gs2026.utils.task_runner import run_daemon_task

# 忽略SQLAlchemy的SAWarning警告，避免日志干扰
warnings.filterwarnings("ignore", category=SAWarning)

# 初始化日志记录器，使用当前文件的绝对路径作为logger名称
logger = log_util.setup_logger(str(Path(__file__).absolute()))
# 设置pandas的全局显示选项（如最大列数、宽度等）
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接URL
url = config_util.get_config("common.url")

# 创建SQLAlchemy数据库引擎，启用连接池回收和预检测
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
# Firefox浏览器路径（用于无头浏览器场景）
browser_path = string_enum.FIREFOX_PATH_1509
# 初始化MySQL工具和邮件工具实例
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()

# 页面加载超时时间（毫秒）
page_timeout = 480000


def deepseek_ai(
    query_list: List[Tuple[str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """调用DeepSeek AI对涨停板数据进行逐条分析。

    遍历待分析的股票列表，为每只股票构建涨停分析Prompt，
    调用DeepSeek模型获取JSON格式的分析结果，并将结果持久化到数据库。

    Args:
        query_list: 待分析的股票列表，每个元素为 (股票简称, 交易日期) 的元组。
        bk_dic_str: 同花顺板块名称字典字符串，用逗号分隔。
        gn_dic_str: 同花顺概念名称字典字符串，用逗号分隔。
        table_name: 涨停板数据源表名（如 'ztb_day'）。
        analysis_table_name: 分析结果存储表名（如 'analysis_ztb2025'）。
        _headless: 是否使用无头浏览器模式运行DeepSeek。

    Raises:
        JSONDecodeError: AI返回的结果无法解析为合法JSON时捕获并记录日志。
        KeyError: JSON结构中缺少预期字段时捕获并记录日志。

    """

    for i in query_list:
        start = time.time()
        stock_name: str = i[0]
        sj: str = i[1]
        # 根据股票名称+日期生成唯一MD5标识
        stock_sj_id: str = string_util.generate_md5(stock_name + sj)

        # 构建DeepSeek分析Prompt，包含涨停消息分析、股性分析、龙虎榜等多维度要求
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

        # 对Prompt中的敏感词进行替换处理
        query = string_util.sensitive_word_replacement(query)
        # 调用DeepSeek模型进行分析
        analysis: str = deepseek_analysis_event_driven.deepseek_analysis(query, _headless)

        # 清洗AI返回的文本：去除json/Copy/Code前缀、注释、前导空白
        analysis = string_util.remove_json_prefix(analysis, 'json')
        analysis = string_util.remove_json_prefix(analysis, 'Copy')
        analysis = string_util.remove_json_prefix(analysis, 'Code')
        analysis = string_util.remove_json_comments(analysis)
        analysis = analysis.lstrip()
        analysis = string_util.convert_quotes_to_chinese(analysis)
        # 从混合文本中提取JSON部分
        json_data, remaining_text = string_util.extract_json_from_string(analysis)

        # 校验JSON合法性并持久化分析结果
        try:
            if string_util.is_valid_json(json_data) or json_data.strip() != '{}' and json_data != '':
                # 先删除旧的分析记录，再插入新结果（幂等更新策略）
                delete_sql = f"delete from {analysis_table_name} where gpjc_sj_id='{stock_sj_id}'"
                mysql_util.delete_data(delete_sql)

                update_sql1 = f"INSERT INTO  {analysis_table_name} (gpjc_sj_id,gpjc,sj,json_data) VALUES  ('{stock_sj_id}','{stock_name}','{sj}','{json_data}') "
                mysql_util.update_data(update_sql1)

                # 将数据源表中对应记录标记为已分析
                update_sql2 = f"UPDATE {table_name} SET analysis='1' WHERE `股票简称`='{stock_name}' and `trade_date`='{sj}'"
                mysql_util.update_data(update_sql2)
                logger.info(f"更新{table_name}表1条数据，更新id：{stock_sj_id}")
                
                # 拆分入库到新表（analysis_ztb_detail_2025）
                try:
                    stats = process_ztb(json_data, stock_name, sj, stock_code, version='1.0.0')
                    logger.info(f"涨停分析拆分入库: {stats}")
                except Exception as e:
                    logger.error(f"涨停分析拆分入库失败: {e}")
                    
            else:
                logger.error(table_name + "该数据ai分析失败，请重试")

        except JSONDecodeError:
            logger.error("json解析失败,JSONDecodeError")
        except KeyError:
            logger.error("json解析失败,KeyError")
        except Exception as e:
            # 捕获所有其他异常，记录日志但不抛出，确保继续执行
            logger.error(f"处理数据时发生异常: {type(e).__name__}: {e}")

        end = time.time()
        execution_time: float = end - start
        logger.info(f"{table_name}AI分析耗时: {execution_time} 秒")


def get_news_ztb_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date_: str,
    end_date_: str,
    _headless: bool
) -> bool:
    """查询未分析的涨停板数据并触发AI分析。

    从数据源表和分析表中联合查询尚未完成AI分析的涨停记录，
    同时加载板块和概念字典数据，调用deepseek_ai进行分析。

    Args:
        table_name: 涨停板数据源表名。
        analysis_table_name: 分析结果存储表名。
        start_date_: 查询起始日期，格式 'YYYY-MM-DD'。
        end_date_: 查询截止日期，格式 'YYYY-MM-DD'。
        _headless: 是否使用无头浏览器模式。

    Returns:
        bool: 如果存在待分析数据并已触发分析返回True，否则返回False。

    """

    # 联合查询数据源表和分析表中未完成分析的记录，随机取1条
    sql = f"""(select SQL_NO_CACHE `股票简称`,`trade_date` from {table_name} 
                    where (analysis is null or analysis='') 
                    and trade_date between '{start_date_}' and '{end_date_}' )
                union 
                (select SQL_NO_CACHE gpjc as `股票简称`,sj as `trade_date` from {analysis_table_name}
                    where (json_data is null or json_data='') 
                    and sj between '{start_date_}' and '{end_date_}' )
                order by RAND() limit 1"""
    # 加载同花顺板块字典
    bk_dic_sql = "select name from data_industry_code_ths"
    # 加载同花顺概念字典（仅启用的概念）
    gn_dic_sql = "select name from ths_gn_names_rq where flag='1'"
    flag: bool = True

    with engine.connect() as conn:
        lists: List[List[Any]] = pd.read_sql(sql, con=conn).values.tolist()
        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))
        if len(lists) != 0:
            deepseek_ai(lists, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            # 无待分析数据，返回False终止轮询
            flag = False
    return flag


def time_task_do_ztb(
    date_param: str,
    start_date_: str,
    end_date_: str,
    polling_time: int
) -> None:
    """按指定日期参数循环执行涨停板AI分析任务。

    持续轮询数据库中未分析的涨停板数据，直到所有数据分析完毕才退出。
    每轮分析后休眠指定秒数，避免过于频繁的数据库查询。

    Args:
        date_param: 日期参数字符串（格式 'YYYY-MM-DD'），用于提取年份。
        start_date_: 查询起始日期。
        end_date_: 查询截止日期。
        polling_time: 每轮分析后的休眠时间（秒）。

    """

    # 持续执行直到所有数据都分析完成
    while True:
        # 从日期参数中提取年份，用于拼接分析结果表名
        year: str = date_param[0:4]
        has_more_data: bool = get_news_ztb_analysis("ztb_day", "analysis_ztb" + year, start_date_, end_date_, True)
        
        if not has_more_data:
            # 没有更多数据需要分析，退出循环
            logger.info(f"日期 {date_param} 的所有数据已分析完成，任务结束")
            break
            
        time.sleep(polling_time)


def analysis_ztb(date_list_: List[str]) -> None:
    """批量执行涨停板AI分析的入口函数。

    遍历日期列表，对每个日期调用涨停板分析任务。
    发生异常时自动发送邮件告警，最终确保数据库连接正常关闭。

    Args:
        date_list_: 待分析的日期列表，每个元素格式为 'YYYY-MM-DD'。

    """

    for area_date in date_list_:
        logger.info('=============================' + area_date + '=============================')
        start_date: str = area_date
        end_date: str = area_date
        time_task_do_ztb(area_date, start_date, end_date, 10)



if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='涨停板数据分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()
    
    # 默认日期列表
    date_list = ['2026-04-07']
    
    # 解析命令行参数
    if args.params:
        try:
            params = json.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=analysis_ztb, args=(date_list,))
