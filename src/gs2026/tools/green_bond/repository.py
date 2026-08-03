"""
绿名单数据访问层

集中所有 MySQL 读写 SQL：
  - 读日行情 data_bond_daily_ods
  - 读交易日历 data_jyrl
  - 写 green_bond_list（唯一索引幂等 upsert / 全量 / 增量）
  - 建表结构（唯一索引）
"""
from typing import Optional
import pandas as pd
from sqlalchemy import text

from gs2026.utils import config_util, log_util
from gs2026.utils.mysql_util import get_mysql_tool

logger = log_util.setup_logger(__file__)

TABLE_GREEN = "green_bond_list"
TABLE_BOND_DAILY = "data_bond_daily_ods"
TABLE_CALENDAR = "data_jyrl"


class GreenBondRepository:
    """绿名单数据访问层。"""

    def __init__(self):
        self.engine = config_util.get_engine()
        self.mysql_tool = get_mysql_tool()

    # ==================== 读 ====================

    def load_bond_daily(self, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        """读取可转债日行情。

        Args:
            start/end: 日期范围 'YYYY-MM-DD'（含端点）。为 None 时不限制该端。
                       注意：窗口指标依赖历史数据，增量计算时 start 应向前多取若干交易日
                       （由 runner 负责扩展窗口，repository 只按传入范围查询）。

        Returns:
            DataFrame[code, date, zgzf, stzf, ...]，按 code,date 升序
        """
        where = []
        if start:
            where.append(f"`date` >= '{start}'")
        if end:
            where.append(f"`date` <= '{end}'")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sql = f"""
            SELECT
                `date`                          AS trade_date,
                CAST(bond_code AS CHAR)         AS code,
                zgzf, stzf, spzf, kpzf, zdzf, qjzf, zf,
                high, low, open, close, pre_close,
                sfzt, cjzt, consecutive_up_limit
            FROM {TABLE_BOND_DAILY}
            {where_sql}
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        # 清洗：code/date 非空
        df = df[df["code"].notna() & df["trade_date"].notna()].copy()
        df["code"] = df["code"].astype(str).str.strip()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)
        logger.info(f"加载日行情: {len(df)} 条 (start={start}, end={end})")
        return df

    def load_calendar(self) -> pd.DataFrame:
        """读取交易日历（trade_status=1 的交易日），升序。

        Returns:
            DataFrame[trade_date]，升序
        """
        sql = f"""
            SELECT trade_date
            FROM {TABLE_CALENDAR}
            WHERE trade_status = 1
            ORDER BY trade_date ASC
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        logger.info(f"加载交易日历: {len(df)} 个交易日")
        return df

    def load_qs_jsl(self) -> pd.DataFrame:
        """读取集思录强赎数据(data_bond_qs_jsl)，清洗并解析关键字段。

        Returns:
            DataFrame[code, 强赎状态, 最后交易日, 到期日, 强赎进度]
            - 强赎进度: 数值0-1（如10/15=0.67），解析失败为NaN
            - 日期字段: datetime 或 NaT
        """
        import re
        sql = """
            SELECT
                CAST(`代码` AS CHAR) AS code,
                `强赎状态` AS status,
                `最后交易日` AS last_trade_date,
                `到期日` AS expiry_date,
                `强赎天计数` AS day_count_raw
            FROM data_bond_qs_jsl
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)

        # 清洗
        df["code"] = df["code"].astype(str).str.strip()
        df["status"] = df["status"].astype(str).str.strip().replace("nan", "")
        df["last_trade_date"] = pd.to_datetime(df["last_trade_date"], errors="coerce")
        df["expiry_date"] = pd.to_datetime(df["expiry_date"], errors="coerce")

        # 解析强赎天计数进度（如 "15/15 | 30" -> 1.0, "12/15 | 30" -> 0.8）
        def parse_progress(s):
            if pd.isna(s):
                return float("nan")
            s = str(s).strip()
            # 匹配 X/Y 格式
            m = re.search(r'(\d+)\s*/\s*(\d+)', s)
            if m:
                satisfied = int(m.group(1))
                threshold = int(m.group(2))
                if threshold > 0:
                    return satisfied / threshold
            return float("nan")

        df["强赎进度"] = df["day_count_raw"].apply(parse_progress)
        logger.info(f"加载强赎数据: {len(df)} 条，解析出进度: {df['强赎进度'].notna().sum()} 条")
        return df

    # ==================== 写 ====================

    def ensure_schema(self):
        """确保表结构含唯一索引（幂等，可重复执行）。

        - code/model 收窄为 varchar
        - buy_date 非空
        - 建唯一索引 uk_code_buydate (code, buy_date)
        """
        stmts = [
            f"ALTER TABLE {TABLE_GREEN} MODIFY COLUMN code VARCHAR(16) NOT NULL",
            f"ALTER TABLE {TABLE_GREEN} MODIFY COLUMN model VARCHAR(8) NOT NULL",
            f"ALTER TABLE {TABLE_GREEN} MODIFY COLUMN buy_date DATE NOT NULL",
        ]
        with self.engine.begin() as conn:
            for s in stmts:
                try:
                    conn.execute(text(s))
                    logger.info(f"执行 DDL 成功: {s}")
                except Exception as e:
                    logger.warning(f"DDL 跳过/已生效: {s} -> {e}")
            # 唯一索引：先查是否存在
            try:
                idx = conn.execute(text(
                    f"SHOW INDEX FROM {TABLE_GREEN} WHERE Key_name = 'uk_code_buydate'"
                )).fetchall()
                if not idx:
                    conn.execute(text(
                        f"ALTER TABLE {TABLE_GREEN} ADD UNIQUE KEY uk_code_buydate (code, buy_date)"
                    ))
                    logger.info("创建唯一索引 uk_code_buydate 成功")
                else:
                    logger.info("唯一索引 uk_code_buydate 已存在，跳过")
            except Exception as e:
                logger.error(f"创建唯一索引失败（可能存在重复数据，需先清理）: {e}")
                raise

    def delete_all(self):
        """清空绿名单表（full 模式用）。"""
        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {TABLE_GREEN}"))
        logger.info("已清空 green_bond_list 全部数据")

    def delete_by_buy_date_range(self, start: str, end: str):
        """删除指定 buy_date 范围数据（incremental 模式用）。"""
        with self.engine.begin() as conn:
            conn.execute(text(
                f"DELETE FROM {TABLE_GREEN} WHERE buy_date >= '{start}' AND buy_date <= '{end}'"
            ))
        logger.info(f"已删除 buy_date 范围 [{start}, {end}] 的绿名单数据")

    def upsert(self, df: pd.DataFrame) -> int:
        """幂等写入绿名单（INSERT ... ON DUPLICATE KEY UPDATE model）。

        Args:
            df: DataFrame[code, buy_date, model]

        Returns:
            影响行数
        """
        if df is None or df.empty:
            logger.info("无绿名单记录写入")
            return 0
        # 规范化
        out = df.copy()
        out["code"] = out["code"].astype(str).str.strip()
        out["model"] = out["model"].astype(str).str.strip()
        out["buy_date"] = pd.to_datetime(out["buy_date"]).dt.strftime("%Y-%m-%d")
        records = out[["code", "buy_date", "model"]].to_dict("records")
        # 复用 MysqlTool 批量 upsert：冲突时更新 model
        rowcount = self.mysql_tool.batch_insert(TABLE_GREEN, records, key_fields=["model"])
        logger.info(f"绿名单 upsert 完成: {len(records)} 条, 影响 {rowcount} 行")
        return rowcount

    def snapshot_baseline(self, baseline_table: str = "green_bond_list_baseline"):
        """将当前 green_bond_list 快照到基线表（验收对比用）。"""
        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {baseline_table}"))
            conn.execute(text(f"CREATE TABLE {baseline_table} AS SELECT * FROM {TABLE_GREEN}"))
        logger.info(f"已快照基线表: {baseline_table}")

    def load_existing(self) -> pd.DataFrame:
        """读取现有绿名单全量（验收对比用）。"""
        with self.engine.connect() as conn:
            df = pd.read_sql(text(f"SELECT code, buy_date, model FROM {TABLE_GREEN}"), conn)
        if not df.empty:
            df["code"] = df["code"].astype(str).str.strip()
            df["model"] = df["model"].astype(str).str.strip()
            df["buy_date"] = pd.to_datetime(df["buy_date"]).dt.strftime("%Y-%m-%d")
        return df
