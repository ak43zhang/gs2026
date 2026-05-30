"""
免费代理IP池 - 多源聚合 + Redis存储 + SOCKS5/HTTP支持
"""
import json
import random
import re
import socket
import time
import threading
from typing import Optional, List, Dict
from dataclasses import dataclass, field

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class ProxyInfo:
    """代理信息"""
    url: str           # http://ip:port 或 socks5://ip:port
    protocol: str      # http / https / socks5
    ip: str
    port: str
    score: float = 60.0   # 可用性评分 0-100
    fail_count: int = 0
    success_count: int = 0
    last_check: float = 0
    latency_ms: float = 9999

    def to_dict(self) -> dict:
        return {
            'url': self.url, 'protocol': self.protocol,
            'ip': self.ip, 'port': self.port,
            'score': self.score, 'fail_count': self.fail_count,
            'success_count': self.success_count,
            'last_check': self.last_check, 'latency_ms': self.latency_ms
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ProxyInfo':
        return cls(**d)


class ProxyPool:
    """免费代理IP池 - Redis 存储"""

    REDIS_KEY = 'proxy_pool:proxies'
    REDIS_KEY_SET = 'proxy_pool:all_proxies'
    MIN_SCORE = 20
    MAX_SCORE = 100
    VALIDATE_TIMEOUT = 8  # 验证超时秒数
    VALIDATE_URL = 'https://httpbin.org/ip'  # 验证目标

    def __init__(self, redis_url: str = 'redis://localhost:6379/0'):
        self._redis_url = redis_url
        self._redis_client = None
        self._lock = threading.Lock()
        self._refreshing = False

    def _get_redis(self):
        """获取 Redis 连接（懒初始化）"""
        if self._redis_client is None and REDIS_AVAILABLE:
            try:
                self._redis_client = redis.Redis.from_url(
                    self._redis_url, decode_responses=True, socket_timeout=5
                )
                self._redis_client.ping()
            except Exception as e:
                print(f"[ProxyPool] Redis连接失败: {e}")
                self._redis_client = None
        return self._redis_client

    # ==================== 采集 ====================

    def fetch_proxies(self) -> List[ProxyInfo]:
        """从多个免费源抓取代理"""
        proxies = []
        sources = [
            self._fetch_geonode,
            self._fetch_proxyscrape_http,
            self._fetch_proxyscrape_socks5,
            self._fetch_speedx_http,
            self._fetch_freeproxylist,
        ]
        for source in sources:
            try:
                result = source()
                if result:
                    proxies.extend(result)
                    print(f"[ProxyPool] {source.__name__}: +{len(result)}个代理")
            except Exception as e:
                print(f"[ProxyPool] {source.__name__}: 失败 - {e}")

        # 去重
        seen = set()
        unique = []
        for p in proxies:
            if p.url not in seen:
                seen.add(p.url)
                unique.append(p)
        print(f"[ProxyPool] 去重后共 {len(unique)} 个代理")
        return unique

    def _fetch_geonode(self) -> List[ProxyInfo]:
        """geonode API - HTTP/HTTPS/SOCKS5"""
        proxies = []
        url = 'https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc'
        if not REQUESTS_AVAILABLE:
            return proxies
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        for item in data.get('data', []):
            ip = item.get('ip')
            port = item.get('port')
            proto = item.get('protocols', ['http'])[0]
            if ip and port:
                proxy_url = f"{proto}://{ip}:{port}"
                proxies.append(ProxyInfo(
                    url=proxy_url, protocol=proto,
                    ip=ip, port=str(port)
                ))
        return proxies

    def _fetch_proxyscrape_http(self) -> List[ProxyInfo]:
        """proxyscrape HTTP 代理"""
        proxies = []
        url = 'https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all&limit=500'
        if not REQUESTS_AVAILABLE:
            return proxies
        resp = requests.get(url, timeout=15)
        for line in resp.text.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                parts = line.rsplit(':', 1)
                if len(parts) == 2:
                    ip, port = parts
                    proxy_url = f"http://{ip}:{port}"
                    proxies.append(ProxyInfo(url=proxy_url, protocol='http', ip=ip, port=port))
        return proxies

    def _fetch_proxyscrape_socks5(self) -> List[ProxyInfo]:
        """proxyscrape SOCKS5 代理"""
        proxies = []
        url = 'https://api.proxyscrape.com/v2/?request=get&protocol=socks5&timeout=10000&country=all'
        if not REQUESTS_AVAILABLE:
            return proxies
        resp = requests.get(url, timeout=15)
        for line in resp.text.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                parts = line.rsplit(':', 1)
                if len(parts) == 2:
                    ip, port = parts
                    proxy_url = f"socks5://{ip}:{port}"
                    proxies.append(ProxyInfo(url=proxy_url, protocol='socks5', ip=ip, port=port))
        return proxies

    def _fetch_speedx_http(self) -> List[ProxyInfo]:
        """github TheSpeedX HTTP 代理"""
        proxies = []
        url = 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'
        if not REQUESTS_AVAILABLE:
            return proxies
        resp = requests.get(url, timeout=15)
        for line in resp.text.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                parts = line.rsplit(':', 1)
                if len(parts) == 2:
                    ip, port = parts
                    proxy_url = f"http://{ip}:{port}"
                    proxies.append(ProxyInfo(url=proxy_url, protocol='http', ip=ip, port=port))
        return proxies

    def _fetch_freeproxylist(self) -> List[ProxyInfo]:
        """free-proxy-list.net HTML 解析"""
        proxies = []
        url = 'https://free-proxy-list.net/'
        if not REQUESTS_AVAILABLE:
            return proxies
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        # 正则提取HTML中的代理
        pattern = r'<tr>\s*<td>(\d+\.\d+\.\d+\.\d+)</td>\s*<td>(\d+)</td>'
        matches = re.findall(pattern, resp.text)
        for ip, port in matches:
            proxy_url = f"http://{ip}:{port}"
            proxies.append(ProxyInfo(url=proxy_url, protocol='http', ip=ip, port=port))
        return proxies

    # ==================== 验证 ====================

    def validate_proxy(self, proxy: ProxyInfo, target_url: str = None) -> bool:
        """验证单个代理是否可用"""
        if target_url is None:
            target_url = self.VALIDATE_URL
        start = time.time()
        try:
            proxies_dict = {}
            if proxy.protocol in ('http', 'https'):
                proxies_dict = {'http': proxy.url, 'https': proxy.url}
            elif proxy.protocol == 'socks5':
                proxies_dict = {'http': proxy.url, 'https': proxy.url}

            if not REQUESTS_AVAILABLE:
                return False

            resp = requests.get(target_url, proxies=proxies_dict,
                              timeout=self.VALIDATE_TIMEOUT)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                proxy.latency_ms = round(elapsed, 0)
                proxy.last_check = time.time()
                proxy.success_count += 1
                proxy.fail_count = 0
                # 根据延迟调整分数
                if elapsed < 500:
                    proxy.score = min(self.MAX_SCORE, proxy.score + 2)
                elif elapsed < 2000:
                    proxy.score = min(self.MAX_SCORE, proxy.score + 1)
                else:
                    proxy.score = max(self.MIN_SCORE, proxy.score - 1)
                return True
        except Exception:
            proxy.last_check = time.time()
            proxy.fail_count += 1
            proxy.score = max(0, proxy.score - 10)
            proxy.latency_ms = 9999
        return False

    def validate_batch(self, proxies: List[ProxyInfo],
                       workers: int = 10) -> List[ProxyInfo]:
        """并发验证一批代理"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        valid = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self.validate_proxy, p): p for p in proxies}
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    if future.result():
                        valid.append(proxy)
                except Exception:
                    pass
        # 按分数排序
        valid.sort(key=lambda x: (-x.score, x.latency_ms))
        return valid

    # ==================== Redis 持久化 ====================

    def _save_to_redis(self, proxy: ProxyInfo):
        """保存单个代理到 Redis"""
        r = self._get_redis()
        if r is None:
            return
        try:
            r.hset(self.REDIS_KEY, proxy.url, json.dumps(proxy.to_dict()))
            r.zadd(self.REDIS_KEY_SET, {proxy.url: proxy.score})
        except Exception as e:
            print(f"[ProxyPool] Redis保存失败: {e}")

    def _load_from_redis(self) -> List[ProxyInfo]:
        """从 Redis 加载所有代理"""
        r = self._get_redis()
        if r is None:
            return []
        try:
            all_data = r.hgetall(self.REDIS_KEY)
            proxies = []
            for url, data_str in all_data.items():
                try:
                    d = json.loads(data_str)
                    proxies.append(ProxyInfo.from_dict(d))
                except Exception:
                    pass
            return proxies
        except Exception as e:
            print(f"[ProxyPool] Redis加载失败: {e}")
            return []

    def _remove_from_redis(self, proxy_url: str):
        """从 Redis 移除代理"""
        r = self._get_redis()
        if r is None:
            return
        try:
            r.hdel(self.REDIS_KEY, proxy_url)
            r.zrem(self.REDIS_KEY_SET, proxy_url)
        except Exception:
            pass

    # ==================== 对外接口 ====================

    def refresh(self, verify: bool = True) -> int:
        """刷新代理池：采集 + 验证 + 存储"""
        with self._lock:
            if self._refreshing:
                return 0
            self._refreshing = True

        try:
            print("[ProxyPool] === 开始刷新代理池 ===")
            t0 = time.time()

            # 1. 采集
            new_proxies = self.fetch_proxies()
            print(f"[ProxyPool] 采集耗时: {time.time()-t0:.1f}s")

            # 2. 验证
            if verify and new_proxies:
                t1 = time.time()
                valid = self.validate_batch(new_proxies, workers=15)
                print(f"[ProxyPool] 验证: {len(valid)}/{len(new_proxies)} 通过, 耗时: {time.time()-t1:.1f}s")
                new_proxies = valid

            # 3. 合并到 Redis（保留旧的高分代理）
            r = self._get_redis()
            if r is not None:
                existing = self._load_from_redis()
                existing_map = {p.url: p for p in existing}
                for p in new_proxies:
                    if p.url in existing_map:
                        # 合并：保留已有分数，更新字段
                        old = existing_map[p.url]
                        p.score = max(p.score, old.score)
                        p.success_count += old.success_count
                        p.fail_count = max(0, old.fail_count - 1)
                    self._save_to_redis(p)

            elapsed = time.time() - t0
            count = self.count()
            print(f"[ProxyPool] === 刷新完成: {count}个可用代理, 总耗时: {elapsed:.1f}s ===")
            return count
        finally:
            with self._lock:
                self._refreshing = False

    def get_proxy(self) -> Optional[str]:
        """获取一个最佳代理URL（按分数排序）"""
        r = self._get_redis()
        if r is None:
            return None
        try:
            # 取分数最高的前10个中随机选1个
            top = r.zrevrange(self.REDIS_KEY_SET, 0, 9)
            if not top:
                return None
            return random.choice(top)
        except Exception:
            return None

    def get_proxy_info(self) -> Optional[ProxyInfo]:
        """获取代理详细信息对象"""
        url = self.get_proxy()
        if url is None:
            return None
        r = self._get_redis()
        if r is None:
            return ProxyInfo(url=url, protocol='http', ip=url.split('://')[-1].split(':')[0],
                            port=url.split(':')[-1])
        try:
            data = r.hget(self.REDIS_KEY, url)
            if data:
                return ProxyInfo.from_dict(json.loads(data))
        except Exception:
            pass
        return ProxyInfo(url=url, protocol='http', ip='', port='')

    def report_success(self, proxy_url: str):
        """报告使用成功"""
        r = self._get_redis()
        if r is None:
            return
        try:
            data = r.hget(self.REDIS_KEY, proxy_url)
            if data:
                p = ProxyInfo.from_dict(json.loads(data))
                p.score = min(self.MAX_SCORE, p.score + 5)
                p.success_count += 1
                r.hset(self.REDIS_KEY, proxy_url, json.dumps(p.to_dict()))
                r.zadd(self.REDIS_KEY_SET, {proxy_url: p.score})
        except Exception:
            pass

    def report_fail(self, proxy_url: str):
        """报告使用失败"""
        r = self._get_redis()
        if r is None:
            return
        try:
            data = r.hget(self.REDIS_KEY, proxy_url)
            if data:
                p = ProxyInfo.from_dict(json.loads(data))
                p.score = max(0, p.score - 15)
                p.fail_count += 1
                r.hset(self.REDIS_KEY, proxy_url, json.dumps(p.to_dict()))
                r.zadd(self.REDIS_KEY_SET, {proxy_url: p.score})
                # 分数过低移除
                if p.score < self.MIN_SCORE:
                    self._remove_from_redis(proxy_url)
                    print(f"[ProxyPool] 移除低分代理: {proxy_url} (score={p.score:.0f})")
        except Exception:
            pass

    def count(self) -> int:
        """可用代理数量"""
        r = self._get_redis()
        if r is None:
            return 0
        try:
            return r.zcard(self.REDIS_KEY_SET)
        except Exception:
            return 0

    def get_top(self, n: int = 10) -> List[ProxyInfo]:
        """获取分数最高的N个代理详情"""
        r = self._get_redis()
        if r is None:
            return []
        try:
            urls = r.zrevrange(self.REDIS_KEY_SET, 0, n - 1)
            result = []
            for url in urls:
                data = r.hget(self.REDIS_KEY, url)
                if data:
                    result.append(ProxyInfo.from_dict(json.loads(data)))
            return result
        except Exception:
            return []

    def clear(self):
        """清空代理池"""
        r = self._get_redis()
        if r is None:
            return
        try:
            r.delete(self.REDIS_KEY)
            r.delete(self.REDIS_KEY_SET)
            print("[ProxyPool] 已清空")
        except Exception:
            pass


# ==================== 全局单例 ====================

_pool_instance: Optional[ProxyPool] = None
_pool_lock = threading.Lock()

def get_pool(redis_url: str = 'redis://localhost:6379/0') -> ProxyPool:
    """获取全局代理池单例"""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = ProxyPool(redis_url)
    return _pool_instance
