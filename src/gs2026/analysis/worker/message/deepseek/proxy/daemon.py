"""代理池后台刷新守护线程"""
import threading
import time

from gs2026.utils import log_util, config_util
from gs2026.analysis.worker.message.deepseek.proxy.pool import get_pool
from pathlib import Path

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 代理/直连模式配置
PROXY_MODE: str = config_util.get_config("common.deepseek_proxy_mode") or "direct"

_daemon_started = False
_daemon_lock = threading.Lock()


def _refresh_loop():
    """后台定时刷新代理池（每10分钟采集验证新代理）"""
    _pool = get_pool()

    # ① 启动时重验证已有代理（清除过期/死掉的）
    try:
        count = _pool.revalidate_existing()
        if count >= _pool._min_ready:
            _pool._ready_event.set()
            logger.info(f"[ProxyPool] 重验证后池已就绪: {count}个可用")
        else:
            logger.info(f"[ProxyPool] 重验证后仅{count}个, 需补充刷新...")
    except Exception as e:
        logger.warning(f"[ProxyPool] 重验证失败: {e}")

    # ② 如果不够，全量采集补充
    if _pool.count() < _pool._min_ready:
        try:
            _pool.refresh(verify=True)
            logger.info(f"[ProxyPool] 首次刷新完成, 可用代理: {_pool.count()}")
        except Exception as e:
            logger.warning(f"[ProxyPool] 首次刷新失败: {e}")

    # ③ 持续补充循环
    while True:
        time.sleep(600)  # 10分钟刷新一次
        try:
            available = _pool.count()
            if available < 20:
                logger.info(f"[ProxyPool] 可用代理不足({available}), 紧急刷新")
            _pool.refresh(verify=True)
            logger.info(f"[ProxyPool] 定时刷新完成, 可用代理: {_pool.count()}")
        except Exception as e:
            logger.warning(f"[ProxyPool] 定时刷新失败: {e}")


def ensure_proxy_daemon():
    """启动代理池后台刷新（幂等，重复调用不会多启线程）
    
    仅在 proxy 模式下启动。直连模式下为空操作。
    """
    global _daemon_started
    
    if PROXY_MODE != "proxy":
        logger.info("[DeepSeek] 直连模式，不启动代理刷新线程")
        return
    
    with _daemon_lock:
        if _daemon_started:
            return
        t = threading.Thread(target=_refresh_loop, daemon=True, name="proxy-pool-refresh")
        t.start()
        _daemon_started = True
        logger.info("[ProxyPool] 后台刷新线程已启动")
