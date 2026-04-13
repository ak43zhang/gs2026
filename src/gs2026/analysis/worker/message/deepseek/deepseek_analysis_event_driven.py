"""事件驱动分析——DeepSeek 版本。

本模块实现基于 DeepSeek 大语言模型的全球事件驱动分析流程，核心功能包括：
    1. 构造多维度评分 prompt（重要程度、业务影响、综合评分等）
    2. 通过 Playwright 自动化操作 DeepSeek 网页端获取 AI 分析结果
    3. 解析返回的 JSON 数据并持久化到 MySQL
    4. 使用 Redis 分布式锁实现多进程任务调度，避免重复分析
    5. 定时检查与轮询机制，支持批量日期分析

依赖:
    - Playwright (Firefox): 浏览器自动化与 DeepSeek 网页交互
    - Redis: 分布式锁，防止并发重复处理
    - SQLAlchemy + MySQL: 数据持久化
    - pandas: SQL 查询结果处理
    - gs2026.utils: 配置、日志、邮件、字符串处理等工具集

Typical usage::

    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import analysis_event_driven
    analysis_event_driven(['2026-03-20', '2026-03-21'])
"""

import os
import random
import time
import warnings
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Callable, Any, List, Tuple, Optional

import pandas as pd
import redis
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright, Error
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SAWarning

from gs2026.utils import mysql_util, config_util, email_util, display_config, pandas_display_config
from gs2026.utils import log_util, string_enum, string_util
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.account_pool_util import DistributedAccountPool
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.deepseek.result_processor import process_domain

# 忽略 SQLAlchemy 的 SAWarning，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)

# ===== 模块级初始化 =====

# 日志器，以当前文件绝对路径作为 logger 名称
logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 设置 pandas 全局显示选项（列宽、行数等）
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接 URL 和 Redis 连接信息
url: str = config_util.get_config("common.url")
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = config_util.get_int('common.redis.port')

# 创建 SQLAlchemy 引擎，启用连接池回收和预检测
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()

# Firefox 浏览器可执行文件路径
browser_path: str = string_enum.FIREFOX_PATH_1509

# MySQL 工具类实例
mysql_util = mysql_util.MysqlTool(url)

# 邮件工具类实例（用于异常告警）
email_util = email_util.EmailUtil()

# Playwright 页面超时时间（毫秒），15 分钟
page_timeout: int = 900000

# Redis 客户端，用于分布式锁
redis_client: redis.Redis = redis.Redis(
    host=redis_host,
    port=redis_port,
    decode_responses=True
)


def deepseek_ai(
    query_list: List[Tuple[str, str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """对指定的领域-日期组合列表执行 DeepSeek AI 分析。

    遍历 query_list 中的每条记录，构造分析 prompt 并调用 DeepSeek
    获取 JSON 格式的分析结果，最后将结果插入到分析结果表中。

    Args:
        query_list: 待分析记录列表，每个元素为 (日期, 主领域, 子领域) 的元组。
        bk_dic_str: 板块字典字符串，以英文逗号分隔的板块名称列表。
        gn_dic_str: 概念字典字符串，以英文逗号分隔的概念名称列表。
        table_name: 源数据表名称，用于日志标识。
        analysis_table_name: 分析结果存储表名称。
        _headless: 是否以无头模式运行浏览器。

    Returns:
        None

    Raises:
        Exception: 当 deepseek_analysis 调用失败且超过重试次数时抛出。

    Example::

        deepseek_ai(
            [('2026-03-20', '科技', 'AI')],
            '半导体,新能源',
            'ChatGPT,大模型',
            'news_area',
            'analysis_area2026',
            True
        )
    """
    start = time.time()

    for i in query_list:
        t_date: str = i[0]
        main_area: str = i[1]
        child_area: str = i[2]

        # 构造 DeepSeek 分析 prompt，包含多维度评分体系和返回 JSON 格式要求
        query = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息，" + """
                    重要程度评分：按照 权威性与级别 角度评估程度分为 国家级政策（5分）、部委/地方政策（4分）、行业会议（3分）、公司公告（2分）、市场传闻（1分）。按照 新颖性与想象力 角度评估程度分为 新技术/新政策（5分）、现有产业数据向好（3分）。按照 相关性与纯度 角度评估程度分为 直接受益（核心业务高度相关）（5分）、间接受益（产业链上下游）（3分）、情绪相关（概念沾边）（1分），最终由三者分数相加，总分范围0至15分。
                    业务影响维度评分：（每个维度-5至5分，总分范围-60至60）
                        从12个关键经营维度评估消息的实质性影响，正面影响为正分，负面影响为负分，无影响为0分。评分时需结合消息内容具体分析。
                        按照 成本控制 维度评估程度分为	显著降低成本（5）、一定程度降低成本（3）、略有影响（1）	显著提高成本（-5）、一定程度提高（-3）、略有提高（-1），
                        按照 运营效率 维度评估程度分为	大幅提升效率（5）、有所提升（3）、轻微提升（1）	大幅降低效率（-5）、有所降低（-3）、轻微降低（-1），
                        按照 资金与财务 维度评估程度分为	极大改善现金流/利润（5）、明显改善（3）、略有改善（1）	极大恶化（-5）、明显恶化（-3）、略有恶化（-1），
                        按照 技术或工艺突破 维度评估程度分为	重大突破（5）、明显进步（3）、小幅改进（1）	技术落后（-5）、竞争力下降（-3）、小幅退步（-1），
                        按照 产品定价权 维度评估程度分为	显著增强定价能力（5）、有所增强（3）、轻微增强（1）	显著削弱（-5）、有所削弱（-3）、轻微削弱（-1），
                        按照 市场份额扩张 维度评估程度分为	大幅提升市占率（5）、明显提升（3）、小幅提升（1）	大幅下降（-5）、明显下降（-3）、小幅下降（-1），
                        按照 产业链地位 维度评估程度分为	大幅提升话语权（5）、有所提升（3）、轻微提升（1）	大幅降低（-5）、有所降低（-3）、轻微降低（-1），
                        按照 产品结构升级 维度评估程度分为	推动高端化/高附加值（5）、明显优化（3）、小幅调整（1）	导致低端化（-5）、明显劣化（-3）、小幅劣化（-1），
                        按照 成功拓展新业务 维度评估程度分为	开辟全新业务领域（5）、进入新市场（3）、尝试新方向（1）	退出核心业务（-5）、收缩业务（-3）、暂停拓展（-1），
                        按照 政策支持 维度评估程度分为	获得强力政策扶持（5）、一般性支持（3）、间接利好（1）	遭遇政策打压（-5）、限制（-3）、间接利空（-1），
                        按照 行业趋势红利 维度评估程度分为	处于爆发风口（5）、明显受益（3）、略有受益（1）	逆势而行（-5）、明显受损（-3）、略有受损（-1），
                        按照 输入成本下降 维度评估程度分为	大幅降低原材料/能源成本（5）、明显降低（3）、小幅降低（1）	大幅上升（-5）、明显上升（-3）、小幅上升（-1），
                        最终综合分析算出。
                    综合评分：（通过重要程度评分×4+业务影响维度评分）。
                    利空利好（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
                    消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30,字典值有重大，大，中，小四个）。
                    涉及板块（板块字典："""+bk_dic_str+"""，以英文逗号分隔）。
                    涉及概念（概念字典："""+gn_dic_str+"""，以英文逗号分隔）。
                    股票代码（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码），
                    时间（事件发表最早的时间，时间格式为yyyy-MM-dd HH:mm:ss），
                    事件来源（事件最早时间的来源）
                    原因分析（该字段主要根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息对a股具体股票代码直接受益或者受损的原因）,
                    深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)
                    返回结果为json对象，json 结构为       
			        {"消息集合": [
						"主领域": "",
						"子领域": "",
						"时间":"",
						"事件来源":"",
                        "关键事件": "",
                        "简要描述": "",
						"利空利好":"",
						"消息大小":"",
						"涉及板块": "",
						"涉及概念": "",
                        "股票代码": "",
                        "原因分析":"",
                        "重要程度评分":"",
                        "业务影响维度评分":"",
                        "综合评分":"",
                        "深度分析":[""]
					]}  
					请返回json结果。
        """
        # 对 prompt 进行敏感词替换，避免触发平台过滤
        query = string_util.sensitive_word_replacement(query)

        # 调用 DeepSeek 获取 AI 分析结果
        analysis: str = deepseek_analysis(query, _headless)

        # 清理返回结果中的非 JSON 前缀和注释
        analysis = string_util.remove_json_prefix(analysis, 'json')
        analysis = string_util.remove_json_prefix(analysis, 'Copy')
        analysis = string_util.remove_json_prefix(analysis, 'Code')
        analysis = string_util.remove_json_comments(analysis)
        analysis = analysis.lstrip()

        # 从字符串中提取合法的 JSON 数据
        json_data, remaining_text = string_util.extract_json_from_string(analysis)

        if string_util.is_valid_json(json_data) and json_data != '{}':
            # JSON 合法且非空，插入分析结果到数据库（兼容旧表）
            update_sql = f"INSERT INTO  {analysis_table_name} (news_date,main_area,child_area,json_data) VALUES  ('{t_date}','{main_area}','{child_area}','{json_data}') "
            mysql_util.update_data(update_sql)
            
            # 拆分入库到新表（analysis_domain_detail_2026）
            try:
                stats = process_domain(json_data, main_area, child_area, t_date, version='1.0.0')
                logger.info(f"领域分析拆分入库: {stats}")
            except Exception as e:
                logger.error(f"领域分析拆分入库失败: {e}")
        else:
            # JSON 解析失败，记录错误日志
            logger.error(table_name + "该数据ai分析失败，请重试")

    end = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}AI分析耗时: {execution_time} 秒")


@db_retry(max_retries=30, initial_delay=1, max_delay=60,
          retriable_errors=(OperationalError, PlaywrightTimeoutError, JSONDecodeError, KeyError, Error))
def deepseek_analysis(query: str, _headless: bool) -> str | None:
    """通过 Playwright 自动化操作 DeepSeek 网页端获取 AI 分析结果。

    使用分布式账号池获取 DeepSeek 账号，启动 Firefox 浏览器登录
    DeepSeek 网页端，发送 query 并等待 AI 返回分析结果。

    Args:
        query: 发送给 DeepSeek 的分析 prompt 文本。
        _headless: 是否以无头模式运行浏览器。True 为无头模式。

    Returns:
        DeepSeek 返回的 AI 分析结果字符串（通常为 JSON 格式）。
        如果获取失败则返回 '{}'。

    Raises:
        OperationalError: 数据库操作失败。
        PlaywrightTimeoutError: 页面加载或元素等待超时。
        JSONDecodeError: JSON 解析异常。
        KeyError: 账号信息字段缺失。
        Error: Playwright 通用错误。

    Note:
        该函数使用 @db_retry 装饰器，最多重试 30 次，
        初始延迟 1 秒，最大延迟 60 秒。
    """
    # 记录启动时间
    logger.info(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
    pool: Optional[DistributedAccountPool] = None
    try:
        # 初始化分布式账号池，用于获取可用的 DeepSeek 账号
        pool = DistributedAccountPool(
            database_url=url,
            service_type="deepseek",
            default_lease_time=300,
            pool_size=3,       # 每个进程 2 个基础连接
            max_overflow=5     # 每个进程最大 3 个溢出连接
        )
        with pool.account(timeout=page_timeout / 1000) as account_info:
            if account_info is not None:
                deepseek_username: str = account_info['username']
                deepseek_password: str = account_info['password']
                logger.info("当前使用账号：" + deepseek_username + ",当前使用密码：" + deepseek_password)
                with sync_playwright() as p:
                    # 启动 Firefox 浏览器
                    browser = p.firefox.launch(headless=_headless, executable_path=browser_path)

                    # 设置页面显示参数（视口大小、UA 等）
                    page = display_config.set_page_display_options_chrome(browser)

                    # 访问 DeepSeek 聊天页面
                    page.goto('https://chat.deepseek.com/', timeout=page_timeout)

                    # 执行登录流程
                    page.get_by_role("button").nth(2).click()
                    page.get_by_placeholder("Phone number / email address").click()
                    page.get_by_placeholder("Phone number / email address").fill(deepseek_username)
                    page.get_by_placeholder("Password").click()
                    page.get_by_placeholder("Password").fill(deepseek_password)
                    page.get_by_role("button", name="Log in").click()

                    # 启用 DeepThink 深度思考模式和搜索功能
                    page.get_by_role("button", name="DeepThink").click()
                    page.get_by_role("button", name="Search").click()

                    # 填入分析 prompt 并提交
                    page.get_by_placeholder("Message DeepSeek").fill(query)
                    page.click("._52c986b > div:nth-child(1)")

                    # 随机短暂等待，模拟人工操作节奏
                    time.sleep(random.randint(1, 2))

                    # 等待 AI 回复区域出现（最长等待 page_timeout 毫秒）
                    page.wait_for_selector('._965abe9 > div:nth-child(1) > div:nth-child(1)', timeout=page_timeout)

                    # 获取最新回复内容，按优先级尝试多个 CSS 选择器
                    response_selectors: List[str] = [
                        '.md-code-block > pre:nth-child(2)',
                        'div.ds-markdown:nth-child(2) > p:nth-child(1)'
                    ]
                    result: str = '{}'
                    try:
                        responses_text: str = '{}'  # 默认值，避免分支遗漏
                        for selector in response_selectors:
                            responses = page.query_selector(selector)
                            if responses is not None:
                                responses_text = responses.inner_text()
                                break
                        # 清理引用标记并替换特殊引号字符
                        result = string_util.remove_citation(responses_text).replace("'", "(").replace("\u2019", "）").replace("'", "")

                    except AttributeError as e:
                        logger.error(f"解析 DeepSeek 回复时发生属性错误: {e}")

                    # 随机睡眠，降低反爬检测风险
                    time.sleep(random.randint(1, 3))
                    # 关闭浏览器释放资源
                    browser.close()
            else:
                logger.warning("account_info 为空，请重试！")
    finally:
        # 确保账号池资源被正确释放
        if pool is not None:
            pool.close()

    return result


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool
) -> bool | None:
    """从数据库获取待分析记录，使用 Redis 分布式锁进行单条分析。

    查询最多 10 条尚未分析的领域记录作为候选，遍历候选列表
    尝试获取 Redis 分布式锁，成功后调用 deepseek_ai 进行分析。

    Args:
        table_name: 领域配置源表名称（如 'news_area'）。
        analysis_table_name: 分析结果目标表名称（如 'analysis_area2026'）。
        start_date: 目标分析日期，格式为 'YYYY-MM-DD'。
        _headless: 是否以无头模式运行浏览器。

    Returns:
        bool: True 表示仍有待处理任务（需继续轮询），
              False 表示所有任务已完成。

    Raises:
        Exception: 单条记录处理失败时记录日志并继续尝试下一条。
    """
    # 查询尚未分析的候选记录（通过 LEFT JOIN 排除已分析的记录）
    sql = f"""
        select SQL_NO_CACHE '{start_date}' as t_date,
               {table_name}.main_area,
               {table_name}.child_area
        from {table_name}
        left join (select * from {analysis_table_name} where news_date='{start_date}') as analysis_area2
            on {table_name}.child_area = analysis_area2.child_area
        where is_use='1' and analysis_area2.news_date is null
        order by rand()
        limit 10
    """
    # 板块字典查询
    bk_dic_sql: str = "select name from data_industry_code_ths"
    # 概念字典查询（仅启用的概念）
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        candidates: List[dict] = pd.read_sql(sql, con=conn).to_dict('records')
        if not candidates:
            return False  # 无待处理任务，彻底结束

        # 将板块和概念名称拼接为逗号分隔的字符串，供 prompt 使用
        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

    # 遍历候选记录，尝试获取 Redis 分布式锁
    for cand in candidates:
        t_date: str = cand['t_date']
        main_area: str = cand['main_area']
        child_area: str = cand['child_area']

        # 构造分布式锁的 key，确保同一记录不被多进程重复处理
        lock_key: str = f"area_ai_lock:{table_name}:{t_date}:{main_area}:{child_area}"
        lock = redis_client.lock(lock_key, timeout=900, blocking_timeout=0)  # 15分钟超时，不阻塞

        if lock.acquire(blocking=False):
            try:
                # 成功获取锁，执行 AI 分析
                deepseek_ai([(t_date, main_area, child_area)], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
                return True  # 成功处理一条，本次调用结束
            except Exception as e:
                logger.error(f"处理记录 {t_date} {main_area} {child_area} 失败: {e}")
                # 处理失败，释放锁后继续尝试下一个候选
            finally:
                # 安全释放锁（可能因超时已自动释放）
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    # 锁已自动过期，无需处理
                    pass
        # 获取锁失败则跳过该候选，继续下一个

    # 所有候选均被锁定或处理失败，仍有任务待处理，返回 True 让外层重试
    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """对指定日期执行领域 AI 分析的轮询循环。

    持续调用 area_ai_analysis 直到所有领域记录分析完毕。
    每次分析完成后休眠 polling_time 秒再进行下一轮。

    Args:
        area_ai_date: 目标分析日期，格式为 'YYYY-MM-DD'。
        polling_time: 每轮分析之间的休眠时间（秒）。

    Returns:
        None
    """
    flag: bool = True
    # 从日期字符串中提取年份，用于确定分析结果表名
    year: str = area_ai_date[0:4]
    table: str = "news_area"
    analysis_table: str = "analysis_area" + year

    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, True)
        time.sleep(polling_time)


def check_time_and_execute(
        target_date: datetime,
        check_interval: int,
        execute_func: Callable[..., Any],
        *func_args: Any,
        **func_kwargs: Any
) -> Any:
    """定时检查并在目标时间到达后执行指定函数。

    以 check_interval 为间隔循环检查当前时间，当当前时间
    超过 target_date 时执行 execute_func 并返回其结果。

    Args:
        target_date: 目标执行时间。
        check_interval: 检查间隔（秒）。
        execute_func: 需要执行的回调函数。
        *func_args: 传递给 execute_func 的位置参数。
        **func_kwargs: 传递给 execute_func 的关键字参数。

    Returns:
        execute_func 的返回值。

    Example::

        result = check_time_and_execute(
            target_date=datetime(2026, 3, 20, 9, 30),
            check_interval=60,
            execute_func=area_ai,
            '2026-03-20', 1
        )
    """
    logger.info(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("开始循环检查，每隔1分钟检查一次...")

    while True:
        current_time: datetime = datetime.now()

        if current_time > target_date:
            # 目标时间已到，执行任务
            logger.info(f"\n✅ 时间已到！当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"开始执行函数: {execute_func.__name__}...")

            # 执行传入的函数
            result = execute_func(*func_args, **func_kwargs)

            logger.info("任务执行完成，程序继续运行...")
            return result

        else:
            # 计算剩余等待时间并周期性输出日志
            remaining = target_date - current_time
            days: int = remaining.days
            seconds: int = remaining.seconds
            hours: int = seconds // 3600
            minutes: int = (seconds % 3600) // 60

            current_minute: int = current_time.minute
            # 每 10 分钟或剩余不足 1 小时时输出等待状态
            if current_minute % 10 == 0 or remaining.total_seconds() < 3600:
                logger.info(f"当前时间: {current_time.strftime('%H:%M:%S')}, "
                            f"剩余: {days}天{hours}小时{minutes}分钟")

        time.sleep(check_interval)


def analysis_event_driven(date_list_: List[str]) -> None:
    """事件驱动分析主入口，按日期列表依次执行全领域 AI 分析。

    遍历日期列表，对每个日期调用 area_ai 完成所有领域的分析。
    发生异常时通过邮件发送告警通知。

    Args:
        date_list_: 待分析日期列表，每个元素格式为 'YYYY-MM-DD'。

    Returns:
        None

    """
    # 主线程保持运行

    for area_date in date_list_:
        logger.info('=============================' + area_date + '=============================')
        area_ai(area_date, 1)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='领域事件分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()
    
    # 默认日期列表
    date_list = ['2026-04-01','2026-04-02','2026-04-03','2026-04-04','2026-04-05','2026-04-06']
    
    # 解析命令行参数
    if args.params:
        try:
            params = json.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=analysis_event_driven, args=(date_list,))

