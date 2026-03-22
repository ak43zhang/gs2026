from typing import Optional, Tuple, List, Set

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Table, MetaData
import sqlalchemy.exc
import pandas as pd
import mysql.connector
from loguru import logger

from gs2026.utils.config_util import get_config

mysql_ip = get_config("mysql.host")
mysql_port = get_config("mysql.port", 3306)
mysql_user = get_config("mysql.user", "root")
mysql_password = get_config("mysql.password", "")
mysql_db = get_config("mysql.database", "gs")
logger.debug(f"MySQL配置: host={mysql_ip}, port={mysql_port}, user={mysql_user}, db={mysql_db}")


class MysqlTool:
    """MySQL 数据库工具类"""

    def __init__(self, url: str) -> None:
        """
        初始化方法，接收数据库连接的URL参数，创建数据库引擎和会话工厂

        Args:
            url: 数据库连接字符串，格式类似'mysql+pymysql://username:password@192.168.0.109:3306/database_name'
                 添加 pool_pre_ping=True 参数。这样每次从连接池获取连接时，SQLAlchemy 都会先执行一个轻量的 SELECT 1 来验证连接是否有效，
                 如果无效则自动丢弃并新建一个连接。
        """
        self.engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)

    def drop_mysql_table(self, table_name: str) -> None:
        """
        用于删除指定MySQL表的方法

        Args:
            table_name: 要删除的表名
        """
        metadata = MetaData()
        metadata.reflect(bind=self.engine)
        session = self.Session()
        try:
            if table_name in metadata.tables:
                table_to_delete = Table(table_name, metadata, autoload_with=self.engine)
                table_to_delete.drop(self.engine)
                session.commit()
                logger.info(f"{table_name} 表删除成功")
            else:
                logger.info(f"{table_name} 表不存在，无需删除")
        except sqlalchemy.exc.SQLAlchemyError as e:
            session.rollback()
            logger.error(f"删除 {table_name} 表时出现异常: {e}")
        finally:
            session.close()

    def delete_data(self, query: Optional[str] = None) -> int:
        """
        删除数据

        Args:
            query: 删除SQL语句

        Returns:
            影响的行数
        """
        connect: Optional[mysql.connector.MySQLConnection] = None
        cursor: Optional[mysql.connector.cursor.MySQLCursor] = None
        affected_rows: int = 0

        try:
            connect = mysql.connector.connect(
                host=mysql_ip,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                charset="utf8"
            )

            cursor = connect.cursor()
            cursor.execute(query)
            connect.commit()
            affected_rows = cursor.rowcount
            logger.info(f"删除成功，影响行数: {affected_rows}")

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            if connect:
                connect.rollback()

        except Exception as e:
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

        return affected_rows

    def update_data(self, query: Optional[str] = None) -> int:
        """
        更新数据

        Args:
            query: 更新SQL语句

        Returns:
            影响的行数
        """
        connect: Optional[mysql.connector.MySQLConnection] = None
        cursor: Optional[mysql.connector.cursor.MySQLCursor] = None
        update_count: int = 0

        try:
            connect = mysql.connector.connect(
                host=mysql_ip,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                charset="utf8"
            )

            cursor = connect.cursor()
            cursor.execute(query)
            connect.commit()
            update_count = cursor.rowcount
            logger.info(f"更新成功，影响行数: {update_count}")

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            if connect:
                connect.rollback()

        except Exception as e:
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

        return update_count

    def update_transactions_data(self, update_sql1: Optional[str] = None, update_sql2: Optional[str] = None) -> Tuple[int, int]:
        """
        执行两条更新SQL，并返回各自影响的行数
        如果有一条更新行数为0或-1，则回滚整个事务

        Args:
            update_sql1: 第一条更新SQL
            update_sql2: 第二条更新SQL

        Returns:
            tuple: (update_count1, update_count2)，分别为两条SQL影响的行数
        """
        connect: Optional[mysql.connector.MySQLConnection] = None
        cursor: Optional[mysql.connector.cursor.MySQLCursor] = None
        update_count1: int = 0
        update_count2: int = 0

        try:
            connect = mysql.connector.connect(
                host=mysql_ip,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                charset="utf8"
            )

            connect.autocommit = False
            cursor = connect.cursor()

            cursor.execute(update_sql1)
            update_count1 = cursor.rowcount
            logger.info(f"第一条SQL更新了 {update_count1} 行数据")

            if update_count1 <= 0:
                logger.warning("第一条SQL更新失败，将回滚事务")
                connect.rollback()
                return 0, 0

            cursor.execute(update_sql2)
            update_count2 = cursor.rowcount
            logger.info(f"第二条SQL更新了 {update_count2} 行数据")

            if update_count2 <= 0:
                logger.warning("第二条SQL更新失败，将回滚事务")
                connect.rollback()
                return 0, 0

            connect.commit()
            logger.info("两条更新都成功，事务已提交")

            return update_count1, update_count2

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            if connect:
                connect.rollback()
            return 0, 0

        except Exception as e:
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()
            return 0, 0

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

    def update_multiple_transactions(self, *sql_statements: str) -> List[int]:
        """
        执行多条更新SQL，并返回每条SQL影响的行数
        如果任何一条SQL影响行数为0或-1，则整个事务回滚

        Args:
            *sql_statements: 可变数量的SQL语句

        Returns:
            list: 每条SQL影响的行数列表，如果有任何失败则返回全0列表
        """
        connect: Optional[mysql.connector.MySQLConnection] = None
        cursor: Optional[mysql.connector.cursor.MySQLCursor] = None
        results: List[int] = []

        try:
            connect = mysql.connector.connect(
                host=mysql_ip,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                charset="utf8"
            )

            connect.autocommit = False
            cursor = connect.cursor()

            for i, sql in enumerate(sql_statements, 1):
                if not sql or not sql.strip():
                    logger.warning(f"第{i}条SQL为空，视为失败，将回滚事务")
                    connect.rollback()
                    return [0] * len(sql_statements)

                cursor.execute(sql)
                affected_rows = cursor.rowcount
                logger.info(f"第{i}条SQL更新了 {affected_rows} 行数据")

                if affected_rows <= 0:
                    logger.warning(f"第{i}条SQL更新失败，将回滚整个事务")
                    connect.rollback()
                    return [0] * len(sql_statements)

                results.append(affected_rows)

            connect.commit()
            logger.info(f"所有更新成功，共执行{len(sql_statements)}条SQL")

            return results

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            if connect:
                connect.rollback()
            return [0] * len(sql_statements)

        except Exception as e:
            logger.error(f"发生错误: {e}")
            if connect:
                connect.rollback()
            return [0] * len(sql_statements)

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

    def check_table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在

        Args:
            table_name: 表名

        Returns:
            是否存在
        """
        connect: Optional[mysql.connector.MySQLConnection] = None
        cursor: Optional[mysql.connector.cursor.MySQLCursor] = None
        exists: bool = False

        try:
            connect = mysql.connector.connect(
                host=mysql_ip,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                charset="utf8"
            )

            cursor = connect.cursor()

            query = f"""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'gs'
                AND table_name =  '{table_name}'
            """

            cursor.execute(query)

            result = cursor.fetchone()
            exists = result[0] == 1

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            exists = False

        except Exception as e:
            logger.error(f"发生未知错误: {e}")
            exists = False

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

        return exists

    def get_existing_keys(self, table_name: str, key_column: str, where_condition: str) -> Set:
        """
        获取目标表中已存在的关键字段值集合

        Args:
            table_name: 表名
            key_column: 关键字段
            where_condition: 条件

        Returns:
            关键字段值集合
        """
        with self.engine.connect() as conn:
            query = f"SELECT SQL_NO_CACHE {key_column} FROM {table_name} {where_condition}"
            existing_df = pd.read_sql(query, conn).values.tolist()

        set1 = []
        for date in existing_df:
            set1.append(date[0])

        return set(set1)
