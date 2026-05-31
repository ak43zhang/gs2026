"""
代理IP和账号使用记录器 - 异步写入MySQL，不阻塞主流程
"""
import queue
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text

# 建表SQL
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS proxy_usage_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    service VARCHAR(32) NOT NULL DEFAULT 'deepseek' COMMENT '服务类型',
    proxy_url VARCHAR(128) COMMENT '代理IP地址',
    proxy_ip VARCHAR(45) COMMENT '代理IP',
    proxy_port VARCHAR(10) COMMENT '代理端口',
    proxy_protocol VARCHAR(10) COMMENT '协议(http/socks5)',
    account VARCHAR(128) COMMENT '使用的账号',
    result ENUM('success', 'fail', 'timeout', 'blocked') NOT NULL COMMENT '结果',
    duration_ms INT COMMENT '耗时(ms)',
    error_msg VARCHAR(500) COMMENT '错误信息',
    
    INDEX idx_created (created_at),
    INDEX idx_service_result (service, result),
    INDEX idx_proxy (proxy_ip),
    INDEX idx_account (account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理IP和账号使用记录';
"""


class ProxyUsageLogger:
    """代理使用记录器 - 异步队列写入"""

    def __init__(self, db_url: Optional[str] = None):
        self._db_url = db_url
        self._engine = None
        self._queue = queue.Queue(maxsize=1000)
        self._table_created = False
        self._started = False
        self._lock = threading.Lock()

    def _get_engine(self):
        """懒初始化数据库引擎"""
        if self._engine is None:
            if self._db_url is None:
                # 尝试从项目配置读取
                try:
                    import sys
                    sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
                    from gs2026.common import config_util
                    self._db_url = config_util.get_config("common.url")
                except Exception:
                    self._db_url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
            try:
                self._engine = create_engine(
                    self._db_url,
                    pool_size=2, max_overflow=3,
                    pool_recycle=3600, pool_pre_ping=True,
                    connect_args={'connect_timeout': 10}
                )
            except Exception as e:
                print(f"[ProxyUsageLogger] 引擎创建失败: {e}")
        return self._engine

    def _ensure_table(self):
        """确保表存在"""
        if self._table_created:
            return
        engine = self._get_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                conn.execute(text(_CREATE_TABLE_SQL))
                conn.commit()
            self._table_created = True
        except Exception as e:
            print(f"[ProxyUsageLogger] 建表失败: {e}")

    def _start_writer(self):
        """启动后台写入线程"""
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._started = True
            t = threading.Thread(target=self._write_loop, daemon=True, name="proxy-usage-writer")
            t.start()

    def _write_loop(self):
        """后台线程：批量写入"""
        self._ensure_table()
        batch = []
        while True:
            try:
                # 收集队列中的记录（最多等1秒，攒批写入）
                try:
                    item = self._queue.get(timeout=1)
                    batch.append(item)
                except queue.Empty:
                    pass

                # 继续取（非阻塞）
                while not self._queue.empty() and len(batch) < 50:
                    try:
                        batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        break

                # 批量写入
                if batch:
                    self._write_batch(batch)
                    batch = []

            except Exception as e:
                print(f"[ProxyUsageLogger] 写入异常: {e}")
                batch = []
                time.sleep(5)

    def _write_batch(self, records: list):
        """批量写入记录"""
        engine = self._get_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                for r in records:
                    conn.execute(text("""
                        INSERT INTO proxy_usage_log 
                        (service, proxy_url, proxy_ip, proxy_port, proxy_protocol, 
                         account, result, duration_ms, error_msg)
                        VALUES (:service, :proxy_url, :proxy_ip, :proxy_port, :proxy_protocol,
                                :account, :result, :duration_ms, :error_msg)
                    """), r)
                conn.commit()
        except Exception as e:
            print(f"[ProxyUsageLogger] 批量写入失败({len(records)}条): {e}")

    def log(self, service: str = 'deepseek', proxy_url: str = None,
            account: str = None, result: str = 'success',
            duration_ms: int = None, error_msg: str = None):
        """记录一条使用日志（异步，不阻塞主流程）"""
        # 启动写入线程（首次调用时）
        if not self._started:
            self._start_writer()

        # 解析代理信息
        proxy_ip = ''
        proxy_port = ''
        proxy_protocol = ''
        if proxy_url:
            try:
                # socks5://1.2.3.4:8080 或 http://1.2.3.4:8080
                proto_part = proxy_url.split('://')[0] if '://' in proxy_url else 'http'
                addr_part = proxy_url.split('://')[-1] if '://' in proxy_url else proxy_url
                ip_port = addr_part.rsplit(':', 1)
                proxy_ip = ip_port[0] if len(ip_port) >= 1 else ''
                proxy_port = ip_port[1] if len(ip_port) >= 2 else ''
                proxy_protocol = proto_part
            except Exception:
                pass

        # 截断错误信息
        if error_msg and len(error_msg) > 490:
            error_msg = error_msg[:490] + '...'

        record = {
            'service': service,
            'proxy_url': (proxy_url or '')[:128],
            'proxy_ip': proxy_ip[:45],
            'proxy_port': proxy_port[:10],
            'proxy_protocol': proxy_protocol[:10],
            'account': (account or '')[:128],
            'result': result,
            'duration_ms': duration_ms,
            'error_msg': error_msg
        }

        # 放入队列（满了就丢弃，不阻塞主流程）
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            pass  # 静默丢弃


# ==================== 全局单例 ====================

_logger_instance: Optional[ProxyUsageLogger] = None
_logger_lock = threading.Lock()


def get_usage_logger(db_url: str = None) -> ProxyUsageLogger:
    """获取全局使用记录器单例"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = ProxyUsageLogger(db_url)
    return _logger_instance


# 便捷别名
usage_logger = get_usage_logger()
