#!/usr/bin/env python3
"""
MySQL 长时间查询监控脚本

功能:
1. 监控MySQL中运行时间超过阈值的查询
2. 自动终止长时间运行的查询（可配置白名单）
3. 记录日志并可选发送告警

环境变量:
- gs2026_mysql_long_query_monitor_threshold: 查询时间阈值(秒), 默认 600(10分钟)
- gs2026_mysql_long_query_monitor_whitelist: 白名单进程ID(逗号分隔), 可选
- gs2026_mysql_long_query_monitor_dry_run: 是否仅监控不终止(true/false), 默认 false
- gs2026_mysql_long_query_monitor_exclude_patterns: 排除的SQL模式(逗号分隔), 如 "SELECT 1,SLEEP"

使用方式:
1. 直接运行: python -m gs2026.collection.maintenance.mysql_long_query_monitor
2. 调度中心: 配置为 function 类型任务
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, 'F:/pyworkspace2026/gs2026')

from gs2026.utils import mysql_util, log_util, email_util
from gs2026.utils.config_util import get_config

# 初始化日志
logger = log_util.setup_logger(__name__)

# 默认配置
DEFAULT_THRESHOLD = 600  # 10分钟
DEFAULT_DRY_RUN = False


def get_config_from_env() -> Dict:
    """从环境变量读取配置"""
    threshold = int(os.environ.get('gs2026_mysql_long_query_monitor_threshold', DEFAULT_THRESHOLD))
    dry_run = os.environ.get('gs2026_mysql_long_query_monitor_dry_run', 'false').lower() == 'true'

    # 白名单进程ID
    whitelist_str = os.environ.get('gs2026_mysql_long_query_monitor_whitelist', '')
    whitelist = [int(x.strip()) for x in whitelist_str.split(',') if x.strip()]

    # 排除的SQL模式
    exclude_patterns_str = os.environ.get('gs2026_mysql_long_query_monitor_exclude_patterns', '')
    exclude_patterns = [x.strip() for x in exclude_patterns_str.split(',') if x.strip()]

    return {
        'threshold': threshold,
        'dry_run': dry_run,
        'whitelist': whitelist,
        'exclude_patterns': exclude_patterns
    }


def get_long_running_queries(threshold: int) -> List[Dict]:
    """获取长时间运行的查询"""
    tool = mysql_util.get_mysql_tool()

    # 使用 f-string 直接插入参数（数字类型，安全）
    sql = f"""
    SELECT
        ID,
        USER,
        HOST,
        DB,
        COMMAND,
        TIME,
        STATE,
        INFO
    FROM information_schema.PROCESSLIST
    WHERE COMMAND != 'Sleep'
      AND TIME > {threshold}
      AND ID != CONNECTION_ID()
    ORDER BY TIME DESC
    """

    from sqlalchemy import text

    with tool.engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()

    queries = []
    for row in rows:
        queries.append({
            'id': row.ID,
            'user': row.USER,
            'host': row.HOST,
            'db': row.DB,
            'command': row.COMMAND,
            'time': row.TIME,
            'state': row.STATE,
            'info': row.INFO[:200] if row.INFO else ''  # 截断长SQL
        })

    return queries


def should_kill_query(query: Dict, whitelist: List[int], exclude_patterns: List[str]) -> bool:
    """判断是否应该终止该查询"""
    # 检查系统进程（ID < 10 或用户为 system user）
    if query['id'] < 10:
        logger.info(f"跳过系统进程: ID={query['id']}")
        return False

    if query['user'] == 'system user':
        logger.info(f"跳过系统用户进程: ID={query['id']}, USER={query['user']}")
        return False

    # 检查白名单
    if query['id'] in whitelist:
        logger.info(f"跳过白名单进程: ID={query['id']}")
        return False

    # 检查排除模式
    info = query['info'] or ''
    for pattern in exclude_patterns:
        if pattern in info:
            logger.info(f"跳过排除模式 '{pattern}': ID={query['id']}")
            return False

    return True


def kill_query(process_id: int) -> bool:
    """终止指定进程"""
    tool = mysql_util.get_mysql_tool()
    from sqlalchemy import text

    try:
        with tool.engine.connect() as conn:
            conn.execute(text("KILL :pid"), {'pid': process_id})
            conn.commit()
        logger.info(f"已终止进程 ID={process_id}")
        return True
    except Exception as e:
        logger.error(f"终止进程 ID={process_id} 失败: {e}")
        return False


def send_alert(killed_queries: List[Dict], dry_run: bool):
    """发送告警通知"""
    if not killed_queries:
        return

    subject = f"[告警] MySQL 长时间查询{'(模拟)' if dry_run else ''}"

    body_lines = [
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"模式: {'仅监控(未终止)' if dry_run else '自动终止'}",
        f"发现 {len(killed_queries)} 个长时间查询:\n",
    ]

    for q in killed_queries:
        action = "[将终止]" if dry_run else "[已终止]"
        body_lines.append(
            f"{action} ID={q['id']}, TIME={q['time']}s, STATE={q['state']}"
        )
        body_lines.append(f"  SQL: {q['info'][:100]}...")
        body_lines.append("")

    body = "\n".join(body_lines)

    try:
        email_util.send_email(subject, body)
        logger.info("告警邮件已发送")
    except Exception as e:
        logger.error(f"发送告警邮件失败: {e}")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("MySQL 长时间查询监控开始")
    logger.info("=" * 60)

    # 读取配置
    config = get_config_from_env()
    threshold = config['threshold']
    dry_run = config['dry_run']
    whitelist = config['whitelist']
    exclude_patterns = config['exclude_patterns']

    logger.info(f"配置: threshold={threshold}s, dry_run={dry_run}")
    logger.info(f"白名单: {whitelist}")
    logger.info(f"排除模式: {exclude_patterns}")

    # 获取长时间运行的查询
    queries = get_long_running_queries(threshold)
    logger.info(f"发现 {len(queries)} 个运行超过 {threshold}s 的查询")

    if not queries:
        logger.info("没有长时间运行的查询，监控结束")
        return {
            'status': 'success',
            'monitored': 0,
            'killed': 0,
            'dry_run': dry_run
        }

    # 记录所有长时间查询
    for q in queries:
        logger.info(
            f"长时间查询: ID={q['id']}, TIME={q['time']}s, "
            f"STATE={q['state']}, SQL={q['info'][:100]}..."
        )

    # 筛选需要终止的查询
    to_kill = [q for q in queries if should_kill_query(q, whitelist, exclude_patterns)]
    logger.info(f"其中 {len(to_kill)} 个查询需要终止")

    # 执行终止
    killed = []
    for q in to_kill:
        if dry_run:
            logger.info(f"[模拟] 将终止进程 ID={q['id']}")
            killed.append(q)
        else:
            if kill_query(q['id']):
                killed.append(q)

    # 发送告警
    if killed:
        send_alert(killed, dry_run)

    logger.info("=" * 60)
    logger.info(f"监控结束: 发现 {len(queries)} 个, {'模拟' if dry_run else ''}终止 {len(killed)} 个")
    logger.info("=" * 60)

    return {
        'status': 'success',
        'monitored': len(queries),
        'killed': len(killed),
        'dry_run': dry_run,
        'threshold': threshold
    }


if __name__ == "__main__":
    result = main()
    print(f"\n执行结果: {result}")
