from pathlib import Path

import mysql.connector
import pandas as pd
import sqlalchemy.exc
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.orm import sessionmaker

from gs2026.utils import config_util, log_decorator, log_util

# 日志器，以当前文件绝对路径作为 logger 名称
logger = log_util.setup_logger(str(Path(__file__).absolute()))

mysql_host = config_util.get_config('mysql.host')
mysql_port = config_util.get_config('mysql.port')
mysql_user = config_util.get_config('mysql.user')
mysql_password = config_util.get_config('mysql.password')
mysql_database = config_util.get_config('mysql.database')

# TODO 将mysql参数作为程序变量初始化到程序中
@log_decorator(log_level="INFO", log_args=True, log_result=True)
class MysqlTool:
    def __init__(self, url):
        """
        初始化方法，接收数据库连接的URL参数，创建数据库引擎和会话工厂
        :param url: 数据库连接字符串，格式类似'mysql+pymysql://username:password@192.168.0.109:3306/database_name'
        添加 pool_pre_ping=True 参数。这样每次从连接池获取连接时，SQLAlchemy 都会先执行一个轻量的 SELECT 1 来验证连接是否有效，如果无效则自动丢弃并新建一个连接。
        """
        self.engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)  # 关键参数
        self.Session = sessionmaker(bind=self.engine)

    def drop_mysql_table(self, table_name):
        """
        用于删除指定MySQL表的方法
        :param table_name: 要删除的表名
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


    def delete_data(self,query: str = None):
        # 在函数开头初始化变量，避免引用前赋值问题
        connect = None
        cursor = None

        try:
            # 1. 建立数据库连接
            connect = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                charset="utf8"  # MySQL 8默认字符集
            )

            # 2. 创建游标对象
            cursor = connect.cursor()

            # 4. 执行更新操作
            cursor.execute(query)

            # 5. 提交事务（重要！）
            connect.commit()

            logger.info(f"更新成功，影响行数: {cursor.rowcount}")

        except mysql.connector.Error as e:  # 明确指定异常类型
            logger.error(f"数据库错误: {e}")
            # 回滚事务（如果启用事务）
            if connect:
                connect.rollback()

        except Exception as e:  # 捕获其他可能的异常
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()

        finally:
            # 7. 关闭连接和游标
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

    def update_data(self, query: str = None):
        # 在函数开头初始化变量，避免引用前赋值问题
        connect = None
        cursor = None
        update_count: int = 0

        try:
            # 1. 建立数据库连接
            connect = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                charset="utf8"  # MySQL 8默认字符集
            )

            # 2. 创建游标对象
            cursor = connect.cursor()

            # 4. 执行更新操作
            cursor.execute(query)

            # 5. 提交事务（重要！）
            connect.commit()
            update_count = cursor.rowcount
            logger.info(f"更新成功，影响行数: {update_count}")

        except mysql.connector.Error as e:  # 明确指定异常类型
            logger.error(f"数据库错误: {e}")
            # 回滚事务（如果启用事务）
            if connect:
                connect.rollback()

        except Exception as e:  # 捕获其他可能的异常
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()

        finally:
            # 7. 关闭连接和游标
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

    def update_transactions_data(self, update_sql1: str = None, update_sql2: str = None) -> tuple:
        """
        执行两条更新SQL，并返回各自影响的行数
        如果有一条更新行数为0或-1，则回滚整个事务

        Args:
            update_sql1: 第一条更新SQL
            update_sql2: 第二条更新SQL

        Returns:
            tuple: (update_count1, update_count2)，分别为两条SQL影响的行数
        """
        # 初始化变量
        connect = None
        cursor = None
        update_count1: int = 0
        update_count2: int = 0

        try:
            # 1. 建立数据库连接
            connect = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                charset="utf8"
            )

            # 2. 关闭自动提交，开始事务
            connect.autocommit = False

            # 创建游标对象
            cursor = connect.cursor()

            # 3. 执行第一条更新
            cursor.execute(update_sql1)
            update_count1 = cursor.rowcount  # 获取第一条SQL影响的行数
            logger.info(f"第一条SQL更新了 {update_count1} 行数据")

            # 检查第一条SQL的执行结果
            if update_count1 <= 0:  # 0或-1表示没有更新或更新失败
                logger.error("第一条SQL更新失败，将回滚事务")
                connect.rollback()
                return 0, 0

            # 4. 执行第二条更新
            cursor.execute(update_sql2)
            update_count2 = cursor.rowcount  # 获取第二条SQL影响的行数
            logger.info(f"第二条SQL更新了 {update_count2} 行数据")

            # 检查第二条SQL的执行结果
            if update_count2 <= 0:  # 0或-1表示没有更新或更新失败
                logger.error("第二条SQL更新失败，将回滚事务")
                connect.rollback()
                return 0, 0

            # 5. 提交事务
            connect.commit()
            logger.info("两条更新都成功，事务已提交")

            # 返回更新行数
            return update_count1, update_count2

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            # 回滚事务
            if connect:
                connect.rollback()
            # 发生错误时返回0
            return 0, 0

        except Exception as e:
            logger.error(f"发生未知错误: {e}")
            if connect:
                connect.rollback()
            # 发生错误时返回0
            return 0, 0

        finally:
            # 7. 关闭连接和游标
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

    def update_multiple_transactions(self, *sql_statements) -> list:
        """
        执行多条更新SQL，并返回每条SQL影响的行数
        如果任何一条SQL影响行数为0或-1，则整个事务回滚

        Args:
            *sql_statements: 可变数量的SQL语句

        Returns:
            list: 每条SQL影响的行数列表，如果有任何失败则返回全0列表
        """
        connect = None
        cursor = None
        results = []

        try:
            # 建立数据库连接
            connect = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                charset="utf8"
            )

            connect.autocommit = False
            cursor = connect.cursor()

            # 执行每条SQL
            for i, sql in enumerate(sql_statements, 1):
                if not sql or not sql.strip():
                    logger.error(f"第{i}条SQL为空，视为失败，将回滚事务")
                    # 空SQL视为失败，回滚事务
                    connect.rollback()
                    # 返回与SQL数量相同的0列表
                    return [0] * len(sql_statements)

                cursor.execute(sql)
                affected_rows = cursor.rowcount
                logger.info(f"第{i}条SQL更新了 {affected_rows} 行数据")

                # 检查执行结果，0或-1表示更新失败
                if affected_rows <= 0:
                    logger.error(f"第{i}条SQL更新失败，将回滚整个事务")
                    connect.rollback()
                    # 返回与SQL数量相同的0列表
                    return [0] * len(sql_statements)

                results.append(affected_rows)

            # 所有SQL都执行成功，提交事务
            connect.commit()
            logger.info(f"所有更新成功，共执行{len(sql_statements)}条SQL")

            return results

        except mysql.connector.Error as e:
            logger.error(f"数据库错误: {e}")
            if connect:
                connect.rollback()
            # 返回与SQL数量相同的0列表
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

    # # 使用增强版本
    # def demo_enhanced():
    #     sql_list = [
    #         "UPDATE orders SET status = 'PROCESSED' WHERE order_date < '2024-01-01'",
    #         "UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 1001",
    #         "UPDATE customers SET last_purchase = NOW() WHERE customer_id IN (1, 2, 3)"
    #     ]
    #
    #     # 执行多条SQL
    #     results = update_multiple_transactions(*sql_list)
    #
    #     # 输出结果
    #     total_updated = sum(results)
    #     print(f"总共更新了 {total_updated} 行数据")
    #
    #     for i, count in enumerate(results, 1):
    #         print(f"SQL{i}: 更新了{count}行")

    def check_table_exists(self, table_name):
        # 在函数开头初始化变量，避免引用前赋值问题
        connect = None
        cursor = None

        try:
            # 1. 建立数据库连接
            connect = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                charset="utf8"  # MySQL 8默认字符集
            )

            # 2. 创建游标对象
            cursor = connect.cursor()

            # 查询表是否存在
            query = f"""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'gs'
                AND table_name =  '{table_name}'
            """

            cursor.execute(query)

            # 获取结果
            result = cursor.fetchone()
            if result[0]==1:
                exists = True
            else:
                exists = False
        except mysql.connector.Error as e:  # 明确指定异常类型
            logger.error(f"数据库错误: {e}")
            exists = False

        except Exception as e:  # 捕获其他可能的异常
            logger.error(f"发生未知错误: {e}")
            exists = False

        finally:
            # 7. 关闭连接和游标
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.error(f"关闭游标时出错: {e}")
                exists = False

            try:
                if connect and connect.is_connected():
                    connect.close()
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")
                exists = False

        return exists

    def get_existing_keys(self ,table_name: str, key_column: str, where_condition: str) -> set:
        """获取目标表中已存在的关键字段值集合"""
        with self.engine.connect() as conn:
            query = f"SELECT SQL_NO_CACHE {key_column} FROM {table_name} {where_condition}"
            existing_df = pd.read_sql(query, conn).values.tolist()

        set1 = []
        for date in existing_df:
            set1.append(date[0])

        return set(set1)



    # if __name__ == '__main__':
        # drop_mysql_table('data2024_gnzscfxx_copy1')