"""事件驱动分析——DeepSeek 版本。

本模块实现基于 DeepSeek 大语言模型的全球事件驱动分析流程，核心功能包括：
    1. 构造多维度评分 prompt（重要程度、业务影响、综合评分等）
    2. 通过 DeepSeekSession 获取 AI 分析结果
    3. 解析返回的 JSON 数据并持久化到 MySQL
    4. 使用 Redis 分布式锁实现多进程任务调度，避免重复分析
    5. 定时检查与轮询机制，支持批量日期分析

Typical usage::

    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import analysis_event_driven
    analysis_event_driven(['2026-03-20', '2026-03-21'])
"""

import random
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Callable, Any, List, Tuple, Optional

import pandas as pd
import redis
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_date_list_until_yesterday
from gs2026.utils import mysql_util, config_util, email_util, pandas_display_config
from gs2026.utils import log_util, string_util
from gs2026.utils.account_pool_util import DistributedAccountPool
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.deepseek.browser import DeepSeekSession
from gs2026.analysis.worker.message.deepseek.proxy import ensure_proxy_daemon
from gs2026.analysis.worker.message.deepseek.processor import process_domain
from gs2026.analysis.worker.message.prompts import build_event_driven_prompt

# 忽略 SQLAlchemy 的 SAWarning
warnings.filterwarnings("ignore", category=SAWarning)

# ===== 模块级初始化 =====

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

# 数据库 & Redis 配置
url: str = config_util.get_config("common.url")
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = config_util.get_int('common.redis.port')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)
email_util = email_util.EmailUtil()

# 页面超时时间（毫秒）
page_timeout: int = 900000

# Redis 客户端
redis_client: redis.Redis = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# 启动代理池后台刷新（幂等，直连模式下为空操作）
ensure_proxy_daemon()


# ===== 通用分布式锁工具（与其他模块保持一致）=====
from typing import Callable, List, Any

class DistributedLockManager:
    """通用分布式锁管理器，支持多进程任务调度"""
    
    def __init__(self, redis_client: redis.Redis, lock_timeout: int = 900):
        self.redis = redis_client
        self.lock_timeout = lock_timeout
        self._locks: List[redis.lock.Lock] = []
    
    def is_locked(self, lock_key: str) -> bool:
        return self.redis.exists(lock_key)
    
    def try_lock(self, lock_key: str):
        lock = self.redis.lock(lock_key, timeout=self.lock_timeout, blocking_timeout=0)
        if lock.acquire(blocking=False):
            self._locks.append(lock)
            return lock
        return None
    
    def batch_try_lock(self, items: List[Any], key_func: Callable[[Any], str]) -> List[tuple]:
        locked_items = []
        for item in items:
            lock_key = key_func(item)
            lock = self.try_lock(lock_key)
            if lock:
                locked_items.append((item, lock))
        return locked_items
    
    def filter_locked(self, items: List[Any], key_func: Callable[[Any], str]) -> List[Any]:
        return [item for item in items if not self.is_locked(key_func(item))]
    
    def release_lock(self, lock) -> None:
        try:
            lock.release()
            if lock in self._locks:
                self._locks.remove(lock)
        except redis.exceptions.LockNotOwnedError:
            pass
        except Exception:
            pass
    
    def release_all(self) -> None:
        for lock in self._locks[:]:
            self.release_lock(lock)
        self._locks.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_all()
        return False


# ===== 核心业务函数 =====


def deepseek_ai(
    query_list: List[Tuple[str, str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """对指定的领域-日期组合列表执行 DeepSeek AI 分析。

    Args:
        query_list: 待分析记录列表，每个元素为 (日期, 主领域, 子领域)。
        bk_dic_str: 板块字典字符串。
        gn_dic_str: 概念字典字符串。
        table_name: 源数据表名称。
        analysis_table_name: 分析结果存储表名称。
        _headless: 是否以无头模式运行浏览器。
    """
    start = time.time()

    for i in query_list:
        t_date: str = i[0]
        main_area: str = i[1]
        child_area: str = i[2]

        # 构造 prompt
        query_data = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息"
        query = build_event_driven_prompt(query_data, bk_dic_str, gn_dic_str)
        query = string_util.sensitive_word_replacement(query)

        # 调用 DeepSeek 获取分析结果
        analysis: str = deepseek_analysis(query, _headless)

        # 提取第一个完整 JSON
        analysis = _extract_first_json(analysis)

        if string_util.is_valid_json(analysis) and analysis != '{}':
            # 入库（兼容旧表）
            update_sql = f"INSERT INTO {analysis_table_name} (news_date,main_area,child_area,json_data) VALUES ('{t_date}','{main_area}','{child_area}','{analysis}')"
            mysql_tool.update_data(update_sql)

            # 拆分入库到新表
            try:
                stats = process_domain(analysis, main_area, child_area, t_date, version='1.0.0')
                logger.info(f"领域分析拆分入库: {stats}")
            except Exception as e:
                logger.error(f"领域分析拆分入库失败: {e}")
        else:
            logger.error(f"{table_name} 该数据AI分析失败，请重试")

    execution_time = time.time() - start
    logger.info(f"{table_name} AI分析耗时: {execution_time:.1f} 秒")


def deepseek_analysis(query: str, _headless: bool) -> str:
    """通过 DeepSeek 获取 AI 分析结果。

    使用分布式账号池获取账号，通过 DeepSeekSession 完成浏览器自动化。

    Args:
        query: 分析 prompt 文本。
        _headless: 是否无头模式。

    Returns:
        AI 回复文本（通常为 JSON），失败返回 '{}'。
    """
    logger.info(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    pool: Optional[DistributedAccountPool] = None
    result: str = '{}'

    try:
        pool = DistributedAccountPool(
            database_url=url,
            service_type="deepseek",
            default_lease_time=300,
            pool_size=3,
            max_overflow=5
        )
        with pool.account(timeout=page_timeout / 1000) as account_info:
            if account_info is None:
                logger.warning("account_info 为空，请重试！")
                return result

            username: str = account_info['username']
            password: str = account_info['password']
            logger.info(f"[DeepSeek] 使用账号：{username}")

            with DeepSeekSession(headless=_headless) as session:
                session.open(username, password)
                result = session.send_query(query)

    except Exception as e:
        logger.error(f"[DeepSeek] 分析异常: {e}")
        raise
    finally:
        if pool is not None:
            pool.close()

    return result


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool
) -> bool:
    """从数据库获取待分析记录，使用 Redis 分布式锁进行单条分析（使用通用锁管理器）。

    Args:
        table_name: 领域配置源表名称。
        analysis_table_name: 分析结果目标表名称。
        start_date: 目标分析日期 'YYYY-MM-DD'。
        _headless: 是否无头模式。

    Returns:
        True 表示仍有待处理任务，False 表示所有任务已完成。
    """
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
    bk_dic_sql: str = "select name from data_industry_code_ths"
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        candidates: List[dict] = pd.read_sql(sql, con=conn).to_dict('records')
        if not candidates:
            return False

        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

    # 【修改】使用通用分布式锁管理器
    lock_mgr = DistributedLockManager(redis_client, lock_timeout=900)
    
    # 1. 过滤已锁定记录
    available = lock_mgr.filter_locked(
        candidates,
        key_func=lambda cand: f"area_ai_lock:{table_name}:{start_date}:{cand['main_area']}:{cand['child_area']}"
    )
    
    if not available:
        logger.info(f"所有记录已被锁定，暂不处理: {start_date}")
        return True  # 仍有任务，只是被锁定了
    
    # 2. 批量加锁
    locked = lock_mgr.batch_try_lock(
        available,
        key_func=lambda cand: f"area_ai_lock:{table_name}:{start_date}:{cand['main_area']}:{cand['child_area']}"
    )
    
    if not locked:
        logger.info(f"加锁失败，暂不处理: {start_date}")
        lock_mgr.release_all()
        return True
    
    logger.info(f"候选{candidates}条，可用{len(available)}条，成功加锁{len(locked)}条")
    
    # 3. 处理加锁成功的记录
    for cand, lock in locked:
        t_date: str = cand['t_date']
        main_area: str = cand['main_area']
        child_area: str = cand['child_area']
        
        try:
            deepseek_ai([(t_date, main_area, child_area)], bk_dic_str, gn_dic_str, 
                       table_name, analysis_table_name, _headless)
            # 成功处理一条后返回True，让外层循环继续
            lock_mgr.release_lock(lock)
            return True
        except Exception as e:
            logger.error(f"处理记录 {t_date} {main_area} {child_area} 失败: {e}")
            lock_mgr.release_lock(lock)
            continue
    
    # 所有加锁记录都处理失败，但仍有未锁定记录
    lock_mgr.release_all()
    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """对指定日期执行领域 AI 分析的轮询循环。"""
    year: str = area_ai_date[0:4]
    table: str = "news_area"
    analysis_table: str = "analysis_area" + year

    flag: bool = True
    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, True)
        wait = random.randint(10, 30)
        time.sleep(wait)


def check_time_and_execute(
        target_date: datetime,
        check_interval: int,
        execute_func: Callable[..., Any],
        *func_args: Any,
        **func_kwargs: Any
) -> Any:
    """定时检查并在目标时间到达后执行指定函数。"""
    logger.info(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        current_time: datetime = datetime.now()
        if current_time > target_date:
            logger.info(f"✅ 时间已到！开始执行: {execute_func.__name__}")
            result = execute_func(*func_args, **func_kwargs)
            logger.info("任务执行完成")
            return result
        else:
            remaining = target_date - current_time
            if current_time.minute % 10 == 0 or remaining.total_seconds() < 3600:
                logger.info(f"等待中... 剩余: {remaining}")
        time.sleep(check_interval)


def analysis_event_driven(date_list_: List[str]) -> None:
    """事件驱动分析主入口，按日期列表依次执行全领域 AI 分析。"""
    for area_date in date_list_:
        logger.info('=============================' + area_date + '=============================')
        area_ai(area_date, 1)


# ===== 工具函数 =====


def _extract_first_json(text: str) -> str:
    """从文本中提取第一个完整的 JSON 对象"""
    text = text.strip()
    start = text.find('{')
    if start == -1:
        return '{}'
    stack = []
    for i in range(start, len(text)):
        if text[i] == '{':
            stack.append('{')
        elif text[i] == '}':
            if stack:
                stack.pop()
                if not stack:
                    return text[start:i + 1]
    return '{}'


# ===== 入口 =====


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description='领域事件分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()

    date_list = get_date_list_until_yesterday()

    if args.params:
        try:
            params = json.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')

    run_daemon_task(target=analysis_event_driven, args=(date_list,))
