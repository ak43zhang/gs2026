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
    use_counts: Dict = field(default_factory=dict)  # 分服务计数 {"deepseek": 1, "oneaiplus": 2}

    def to_dict(self) -> dict:
        return {
            'url': self.url, 'protocol': self.protocol,
            'ip': self.ip, 'port': self.port,
            'score': self.score, 'fail_count': self.fail_count,
            'success_count': self.success_count,
            'last_check': self.last_check, 'latency_ms': self.latency_ms,
            'use_counts': self.use_counts
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ProxyInfo':
        # 兼容旧数据
        use_counts = d.get('use_counts', {})
        # 兼容旧 use_count (int) 格式
        if 'use_count' in d and isinstance(d['use_count'], int):
            use_counts = {'default': d['use_count']}
        return cls(
            url=d['url'], protocol=d['protocol'],
            ip=d['ip'], port=d['port'],
            score=d.get('score', 60.0),
            fail_count=d.get('fail_count', 0),
            success_count=d.get('success_count', 0),
            last_check=d.get('last_check', 0),
            latency_ms=d.get('latency_ms', 9999),
            use_counts=use_counts
        )

    def get_use_count(self, service: str = 'default') -> int:
        """获取指定服务的使用次数"""
        return self.use_counts.get(service, 0)

    def increment_use(self, service: str = 'default'):
        """增加指定服务的使用次数"""
        self.use_counts[service] = self.use_counts.get(service, 0) + 1


class ProxyPool:
    """免费代理IP池 - Redis 存储 + 分服务计数"""

    REDIS_KEY = 'proxy_pool:proxies'
    REDIS_KEY_SET = 'proxy_pool:all_proxies'
    MIN_SCORE = 20
    MAX_SCORE = 100
    VALIDATE_TIMEOUT = 8  # 验证超时秒数
    VALIDATE_URL = 'https://chat.deepseek.com/'  # 直接验证能否访问DeepSeek

    def __init__(self, redis_url: str = 'redis://localhost:6379/0'):
        self._redis_url = redis_url
        self._redis_client = None
        self._lock = threading.Lock()
        self._refreshing = False
        self._service_config = self._load_service_config()
        self._ready_event = threading.Event()  # 池就绪信号
        self._min_ready = 10  # 最少需要10个优质代理

    def wait_ready(self, min_count: int = 10, timeout: float = 120) -> bool:
        """阻塞等待池中有足够可用代理。返回True=就绪，False=超时"""
        if self.count() >= min_count:
            return True
        print(f"[ProxyPool] 等待池就绪(需≥{min_count}个代理, 超时{timeout}s)...")
        return self._ready_event.wait(timeout=timeout)

    def _load_service_config(self) -> dict:
        """加载服务配置（从 JSON 文件）"""
        import os
        config_path = os.path.join(os.path.dirname(__file__), 'proxy_services.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('services', {'default': {'max_uses': 10}})
        except Exception:
            return {'default': {'max_uses': 10}, 'deepseek': {'max_uses': 5}, 'oneaiplus': {'max_uses': 2}}

    def get_max_uses(self, service: str = 'default') -> int:
        """获取指定服务的最大使用次数"""
        svc = self._service_config.get(service, self._service_config.get('default', {}))
        return svc.get('max_uses', 10)

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
            self._fetch_speedx_socks5,
            self._fetch_monosans_http,
            self._fetch_monosans_socks5,
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

    def _fetch_speedx_socks5(self) -> List[ProxyInfo]:
        """github TheSpeedX SOCKS5 代理"""
        proxies = []
        url = 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt'
        if not REQUESTS_AVAILABLE:
            return proxies
        try:
            resp = requests.get(url, timeout=15)
            for line in resp.text.strip().split('\n'):
                line = line.strip()
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        ip, port = parts
                        proxies.append(ProxyInfo(url=f"socks5://{ip}:{port}", protocol='socks5', ip=ip, port=port))
        except Exception:
            pass
        return proxies

    def _fetch_monosans_http(self) -> List[ProxyInfo]:
        """github monosans HTTP 代理"""
        proxies = []
        url = 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt'
        if not REQUESTS_AVAILABLE:
            return proxies
        try:
            resp = requests.get(url, timeout=15)
            for line in resp.text.strip().split('\n'):
                line = line.strip()
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        ip, port = parts
                        proxies.append(ProxyInfo(url=f"http://{ip}:{port}", protocol='http', ip=ip, port=port))
        except Exception:
            pass
        return proxies

    def _fetch_monosans_socks5(self) -> List[ProxyInfo]:
        """github monosans SOCKS5 代理"""
        proxies = []
        url = 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt'
        if not REQUESTS_AVAILABLE:
            return proxies
        try:
            resp = requests.get(url, timeout=15)
            for line in resp.text.strip().split('\n'):
                line = line.strip()
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        ip, port = parts
                        proxies.append(ProxyInfo(url=f"socks5://{ip}:{port}", protocol='socks5', ip=ip, port=port))
        except Exception:
            pass
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
        """验证单个代理是否可用（能访问 DeepSeek）"""
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
                              timeout=self.VALIDATE_TIMEOUT,
                              headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            elapsed = (time.time() - start) * 1000

            # 验证条件：HTTP 200 且响应含 deepseek（防止拦截页面）
            if resp.status_code == 200 and 'deepseek' in resp.text.lower():
                proxy.latency_ms = round(elapsed, 0)
                proxy.last_check = time.time()
                proxy.success_count += 1
                proxy.fail_count = 0
                # 根据延迟调整分数
                if elapsed < 2000:
                    proxy.score = min(self.MAX_SCORE, proxy.score + 2)
                elif elapsed < 5000:
                    proxy.score = min(self.MAX_SCORE, proxy.score + 1)
                else:
                    proxy.score = max(self.MIN_SCORE, proxy.score - 1)
                return True
        except Exception:
            pass
        proxy.last_check = time.time()
        proxy.fail_count += 1
        proxy.score = max(0, proxy.score - 10)
        proxy.latency_ms = 9999
        return False

    def validate_proxy_quality(self, proxy: ProxyInfo, rounds: int = 5) -> str:
        """多轮验证代理质量，返回质量等级: excellent/good/reject"""
        passes = 0
        total_latency = 0
        for i in range(rounds):
            start = time.time()
            if self.validate_proxy(proxy):
                passes += 1
                total_latency += proxy.latency_ms
            if i < rounds - 1:
                time.sleep(0.5)  # 间隔0.5秒

        if passes == rounds:  # 5/5
            proxy.score = 90
            proxy.latency_ms = round(total_latency / passes, 0)
            return 'excellent'
        elif passes >= rounds - 1:  # 4/5
            proxy.score = 75
            proxy.latency_ms = round(total_latency / max(passes, 1), 0)
            return 'good'
        else:  # ≤3/5
            proxy.score = 0
            return 'reject'

    def validate_batch(self, proxies: List[ProxyInfo],
                       workers: int = 30, quality_mode: bool = True) -> List[ProxyInfo]:
        """并发验证一批代理。quality_mode=True 时进行5轮质量验证"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        valid = []

        if quality_mode:
            # 第一轮快筛：单次验证，过滤明显不可用的
            quick_pass = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(self.validate_proxy, p): p for p in proxies}
                for future in as_completed(futures):
                    proxy = futures[future]
                    try:
                        if future.result():
                            quick_pass.append(proxy)
                    except Exception:
                        pass
            print(f"[ProxyPool] 快筛: {len(quick_pass)}/{len(proxies)} 通过")

            # 第二轮质量验证：对快筛通过的做5轮验证
            if quick_pass:
                with ThreadPoolExecutor(max_workers=min(workers, 15)) as executor:
                    futures = {executor.submit(self.validate_proxy_quality, p, 5): p for p in quick_pass}
                    for future in as_completed(futures):
                        proxy = futures[future]
                        try:
                            quality = future.result()
                            if quality in ('excellent', 'good'):
                                valid.append(proxy)
                        except Exception:
                            pass
                print(f"[ProxyPool] 质量验证: {len(valid)}/{len(quick_pass)} 优质/良好")
        else:
            # 简单模式：单次验证
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
        """刷新代理池：采集 + 验证 + 存储（高频补充模式）"""
        with self._lock:
            if self._refreshing:
                return 0
            self._refreshing = True

        try:
            print("[ProxyPool] === 开始刷新代理池 ===")
            t0 = time.time()

            # 1. 采集
            new_proxies = self.fetch_proxies()
            print(f"[ProxyPool] 采集: {len(new_proxies)}个, 耗时: {time.time()-t0:.1f}s")

            # 排除已在池中的（避免重复验证）
            r = self._get_redis()
            if r is not None:
                existing_urls = set(r.zrange(self.REDIS_KEY_SET, 0, -1))
                new_proxies = [p for p in new_proxies if p.url not in existing_urls]
                print(f"[ProxyPool] 去除已有后: {len(new_proxies)}个新代理待验证")

            # 2. 验证（增大并发到30，加速补充）
            if verify and new_proxies:
                t1 = time.time()
                # 随机打乱，避免总是验证同一批
                random.shuffle(new_proxies)
                # 每次最多验证500个
                batch = new_proxies[:500]
                valid = self.validate_batch(batch, workers=30)
                print(f"[ProxyPool] 验证: {len(valid)}/{len(batch)} 通过, 耗时: {time.time()-t1:.1f}s")
                new_proxies = valid

            # 3. 存入 Redis（新代理 use_count=0）
            if r is not None:
                for p in new_proxies:
                    p.use_counts = {}  # 新代理所有服务未使用
                    self._save_to_redis(p)

            elapsed = time.time() - t0
            count = self.count()
            print(f"[ProxyPool] === 刷新完成: {count}个可用代理, 新增{len(new_proxies)}个, 耗时: {elapsed:.1f}s ===")
            
            # 检查是否达到就绪阈值
            if count >= self._min_ready and not self._ready_event.is_set():
                self._ready_event.set()
                print(f"[ProxyPool] ✓ 池已就绪! ({count}个优质代理)")
            
            return count
        finally:
            with self._lock:
                self._refreshing = False

    def get_proxy(self, service: str = 'default') -> Optional[str]:
        """获取一个未用完的最佳代理URL（按分数排序，跳过指定服务已达上限的）"""
        r = self._get_redis()
        if r is None:
            return None
        try:
            max_uses = self.get_max_uses(service)
            # 取分数最高的前30个，找到未用完的
            top = r.zrevrange(self.REDIS_KEY_SET, 0, 29)
            if not top:
                return None
            # 筛选未达上限的
            available = []
            for url in top:
                data = r.hget(self.REDIS_KEY, url)
                if data:
                    p = ProxyInfo.from_dict(json.loads(data))
                    if p.get_use_count(service) < max_uses:
                        available.append(url)
                else:
                    available.append(url)
            if not available:
                return None
            # 从前5个中随机选（兼顾分数和随机性）
            return random.choice(available[:min(5, len(available))])
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

    def report_success(self, proxy_url: str, service: str = 'default'):
        """报告使用成功 - 分服务计数+全服务用完移除"""
        r = self._get_redis()
        if r is None:
            return
        try:
            data = r.hget(self.REDIS_KEY, proxy_url)
            if data:
                p = ProxyInfo.from_dict(json.loads(data))
                p.score = min(self.MAX_SCORE, p.score + 5)
                p.success_count += 1
                p.increment_use(service)
                
                # 检查是否所有服务都达上限 → 移除
                all_exhausted = all(
                    p.get_use_count(svc) >= self.get_max_uses(svc)
                    for svc in self._service_config.keys()
                )
                if all_exhausted:
                    self._remove_from_redis(proxy_url)
                    print(f"[ProxyPool] 代理所有服务已用完, 移除: {proxy_url}")
                else:
                    max_uses = self.get_max_uses(service)
                    if p.get_use_count(service) >= max_uses:
                        print(f"[ProxyPool] 代理 {service} 已达上限({max_uses}次): {proxy_url}")
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
