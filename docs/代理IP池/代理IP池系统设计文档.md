# 代理IP池系统设计文档

**版本**: v2.0  
**日期**: 2026-06-01  
**文件**: `docs/代理IP池/代理IP池系统设计文档.md`

---

## 一、系统概述

### 1.1 背景

DeepSeek AI 分析程序通过 Playwright 自动化浏览器操作，同一 IP 频繁访问会被风控拦截。代理 IP 池系统通过采集、验证、管理免费代理 IP，为分析程序提供稳定的出口 IP。

### 1.2 核心目标

| 目标 | 指标 |
|------|------|
| 稳定性 | 代理验证通过率 ≥ 70%（对 DeepSeek 可达） |
| 速度 | 登录前就绪等待 ≤ 180 秒 |
| 质量 | 5轮验证通过率 ≥ 80%（优质/良好代理） |
| 可用性 | 池中常备 ≥ 10 个可用代理 |
| 防封 | 本机 IP 永不通 DeepSeek |
| **IP归属** | **100% 国内IP（CN）** |

### 1.3 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    代理IP池系统                           │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐   │
│  │ 采集器    │ → │ 验证器    │ → │  Redis 代理池     │   │
│  │ (7个源)  │   │ (5轮质量) │   │  score + use_count │   │
│  └──────────┘   └──────────┘   └──────────────────┘   │
│       ↓               ↓                    ↓            │
│   ~3000个候选    5轮验证DeepSeek    分数/服务/锁管理    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  后台刷新线程 (每5分钟)                              │  │
│  │  ① 重验证已有代理(清过期+死掉的)                       │  │
│  │  ② 采集新代理 → 验证 → 入池                          │  │
│  │  ③ 池<20个紧急刷新                                    │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│              deepseek_analysis_event_driven.py            │
│                                                          │
│  ① wait_ready(min=10)  ← 阻塞等待池就绪                  │
│  ② get_proxy(service='deepseek')  ← 获取代理             │
│  ③ 预验证: 打开DS首页确认可达                             │
│  ④ 登录 DeepSeek                                         │
│  ⑤ report_success/fail  ← 反馈计数                       │
│  ⑥ usage_logger.log()  ← 异步记录MySQL                   │
└──────────────────────────────────────────────────────────┘
```

---

## 二、数据存储

### 2.1 Redis 数据结构

| Key | 类型 | 说明 |
|-----|------|------|
| `proxy_pool:proxies` | Hash | `{url: json_info}` 存储代理详情 |
| `proxy_pool:all_proxies` | ZSet | `{url: score}` 按分数排序的代理列表 |
| `proxy_pool:lock:{url}` | String | 并发锁，90秒过期 |

### 2.2 代理信息结构（ProxyInfo）

```python
@dataclass
class ProxyInfo:
    url: str           # http://1.2.3.4:8080
    protocol: str      # http / https / socks5
    ip: str            # 1.2.3.4
    port: str          # 8080
    score: float       # 可用性评分 0-100
    fail_count: int    # 连续失败次数
    success_count: int # 累计成功次数
    last_check: float  # 上次验证时间戳
    latency_ms: float  # 上次验证延迟(ms)
    use_counts: Dict   # 分服务计数 {"deepseek": 1, "oneaiplus": 2}
    last_used: float   # 上次被使用的时间戳
    country: str       # IP归属地 (CN/US/JP/...)
    region: str        # 地区 (Beijing/Shanghai/...)
    ip_check_time: float  # 归属地查询时间戳
```
    fail_count: int    # 连续失败次数
    success_count: int # 累计成功次数
    last_check: float  # 上次验证时间戳
    latency_ms: float  # 上次验证延迟(ms)
    use_counts: Dict   # 分服务计数 {"deepseek": 2}
    last_used: float   # 上次被使用的时间戳
```

### 2.3 MySQL 使用记录表

```sql
CREATE TABLE proxy_usage_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    service VARCHAR(32) NOT NULL DEFAULT 'deepseek',
    proxy_url VARCHAR(128),
    proxy_ip VARCHAR(45),
    proxy_port VARCHAR(10),
    proxy_protocol VARCHAR(10),
    account VARCHAR(128),
    result ENUM('success','fail','timeout','blocked'),
    duration_ms INT,
    error_msg VARCHAR(500),
    INDEX idx_created (created_at),
    INDEX idx_service_result (service, result),
    INDEX idx_proxy (proxy_ip),
    INDEX idx_account (account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 三、核心逻辑

### 3.1 代理生命周期

```
  采集(7个GitHub源)
         ↓
  去重 (URL去重)
         ↓
  第一轮快筛 (单次验证DeepSeek)
         ↓
  第二轮质量验证 (5轮×DeepSeek)
    - 5/5 通过 → 优质  score=90  → 入池
    - 4/5 通过 → 良好  score=75  → 入池
    - ≤3/5 通过 → 拒绝 score=0   → 丢弃
         ↓
  入池(Redis ZSet, use_counts={})
         ↓
  ┌──────────────────────────────────────┐
  │                                     │
  │  get_proxy()                         │
  │                                     │
  │  五重筛选:                             │
  │  ① 分服务计数 < max_uses              │
  │  ② last_check < 24h (TTL)            │
  │  ③ 冷却间隔 > 60s (P2)              │
  │  ④ 有效分 = score × 时间衰减 (P3)    │
  │  ⑤ 并发锁 (SETNX 90s) (P1)         │
  │                                     │
  │  → 返回最高有效分的代理                 │
  └──────────────────────────────────────┘
         ↓
  使用代理完成任务
         ↓
  report_success/fail
    - 使用次数+1 (分服务)
    - 释放并发锁
    - 全服务用完 → 从池移除
         ↓
  24h后 → 自动过期移除
```

### 3.2 质量验证机制

| 环节 | 参数 | 说明 |
|------|------|------|
| 验证目标 | `https://chat.deepseek.com/` | 直接验证能访问DeepSeek |
| 验证条件 | HTTP 200 + 内容含"deepseek" | 防止返回拦截页面 |
| 验证轮次 | 5轮 | 第1轮间隔0.5s，第2-5轮随机1-3s |
| 最快超时 | 8秒/轮 | 失败直接判死 |
| 优质标准 | 5/5 通过 | score=90 |
| 良好标准 | 4/5 通过 | score=75 |

**为什么5轮？**免费代理波动大，单次验证通过的代理可能在实际使用时被封。5轮验证确保选出真正稳定的IP。

### 3.3 分数体系

| 事件 | 分数变化 |
|------|----------|
| 5轮验证全部通过（优质） | → 90 |
| 5轮验证4轮通过（良好） | → 75 |
| 验证通过（非质量验证） | +2 (延迟<2s) / +1 (延迟<5s) / -1 (慢) |
| 使用成功 | +5 |
| 使用失败 | -15 |
| 时间衰减 | 每小时 -5%，最低 30% |

**有效分 = 基础分 × 衰减系数**

```python
age_hours = (now - last_check) / 3600
decay = max(0.3, 1.0 - age_hours * 0.05)  # 每小时-5%, 最低30%
effective_score = score * decay
```

### 3.4 分服务计数

| 服务 | 最大次数 | 说明 |
|------|----------|------|
| deepseek | 5次 | DeepSeek AI 分析 |
| oneaiplus | 2次 | OneAIPlus 代理服务 |
| default | 10次 | 通用服务 |

**移除规则**：所有服务都达到上限时才移除（不浪费可用IP）

```
示例:
  IP_A: {"deepseek": 5/5, "oneaiplus": 0/2} → 保留(oneaiplus还能用)
  IP_B: {"deepseek": 5/5, "oneaiplus": 2/2} → 移除(全部用完)
```

### 3.5 代理有效期

| 概念 | 值 | 说明 |
|------|-----|------|
| PROXY_TTL | 24h | 代理最大存活时间，超时视为过期 |
| 并发锁 | 90s | 获取代理时的锁过期时间 |
| 使用冷却 | 60s | 同一代理两次使用的最小间隔 |
| 刷新周期 | 5min | 后台刷新间隔 |
| 紧急刷新 | <20个时 | 立即全量补充 |

### 3.6 并发安全（P1）

```python
# Redis SETNX 分布式锁
lock_key = f'proxy_pool:lock:{proxy_url}'
if redis.set(lock_key, '1', nx=True, ex=90):
    return proxy_url  # 锁定成功，独占使用
# 其他任务无法获取同一代理
```

**锁的释放**：`report_success` 或 `report_fail` 时自动释放。  
**降级策略**：如果所有候选都被锁定，返回最高分的代理（无锁降级，极少发生）。

---

## 四、数据源

### 4.1 采集源（9个）

| 序号 | 源 | 协议 | 类型 | 状态 |
|------|-----|------|------|------|
| 1 | proxyscrape.com HTTP | HTTP | API | 可能被墙 |
| 2 | proxyscrape.com SOCKS5 | SOCKS5 | API | 可能被墙 |
| 3 | TheSpeedX HTTP | HTTP | GitHub | ✅ 可达 |
| 4 | TheSpeedX SOCKS5 | SOCKS5 | GitHub | ✅ 可达 |
| 5 | monosans HTTP | HTTP | GitHub | ✅ 可达 |
| 6 | monosans SOCKS5 | SOCKS5 | GitHub | ✅ 可达 |
| 7 | hookzof SOCKS5 | SOCKS5 | GitHub | ✅ 可达 |
| 8 | MuRongPIG HTTP | HTTP | GitHub | ✅ 可达 |
| 9 | free-proxy-list.net | HTTP | HTML | 可能被墙 |

### 4.2 去重

```python
# URL 级别去重（同一IP:Port只保留一个）
seen = set()
for p in proxies:
    if p.url not in seen:
        seen.add(p.url)
        unique.append(p)
```

---

## 五、后端刷新流程

### 5.1 启动流程

```python
def _refresh_loop():
    _pool = get_pool()
    
    # ① 重验证已有代理
    _pool.revalidate_existing()
    #   - 移除 >24h 过期
    #   - 单次验证剩余代理
    #   - 移除不通过的
    #   - count >= 10 → set(ready_event)
    
    # ② 如果不够，全量采集补充
    if _pool.count() < 10:
        _pool.refresh(verify=True)
    
    # ③ 持续循环
    while True:
        sleep(300)  # 5分钟
        if _pool.count() < 20:
            _pool.refresh(verify=True)
```

### 5.2 refresh() 流程

```
采集(7个源，去重) → 过滤已有 → 快筛(单次) → 质量验证(5轮) → 入池 → 检查就绪
```

**耗时估算**：
- 采集：~10秒（-github raw速度）
- 快筛500个 ÷ 30并发：~20秒
- 质量验证（通过~30个）= 30 × 5轮 × 8s ÷ 15并发：~30秒
- 总计：~60秒（远快于最初的3-5分钟，因为分批验证）

---

## 六、使用流程（deepseek_analysis）

### 6.1 完整流程

```python
# ① 等待池就绪（阻塞）
pool_ready = get_pool().wait_ready(min_count=10, timeout=180)
if not pool_ready:
    raise Exception("代理池未就绪，拒绝执行")

# ② 预验证循环（最多3次换代理）
for attempt in range(3):
    proxy_url = get_pool().get_proxy(service='deepseek')
    browser = p.firefox.launch(proxy={"server": proxy_url})
    page = browser.new_page()
    
    # 预验证：能否打开DeepSeek首页
    page.goto('https://chat.deepseek.com/', timeout=20000)
    if 'deepseek' in page.content().lower():
        break  # ✅ 通过
    
    # ❌ 失败，换代理
    report_fail(proxy_url)
    browser.close()
    time.sleep(1)

# ③ 登录流程（使用步骤②成功打开的page）
FingerprintRandomizer.apply(page)
BehaviorMime.idle_look(page)
# ... 正常登录流程 ...

# ④ 使用成功反馈
report_success(proxy_url, service='deepseek')
usage_logger.log(service='deepseek', proxy_url=proxy_url, 
                 account=username, result='success')
```

### 6.2 日志输出

```
[ProxyPool] 后台刷新线程已启动
[ProxyPool] 重验证 20 个已有代理...
[ProxyPool] 移除过期代理: 3个 (>24h)
[ProxyPool] 重验证完成: 14/20 存活, 移除6个, 池剩14个
[ProxyPool] 重验证后池已就绪: 14个可用

[DeepSeek] 尝试代理(1/3): http://47.52.223.161:5872 | 账号: user@test.com
[DeepSeek] 代理验证通过: http://47.52.223.161:5872

[ProxyPool] 代理使用成功: http://47.52.223.161:5872
[ProxyPool] 代理 deepseek 已达上限(5次): http://47.52.223.161:5872
```

---

## 七、配置文件

### 7.1 proxy_services.json

```json
{
  "services": {
    "deepseek": {
      "max_uses": 5,
      "description": "DeepSeek AI 分析"
    },
    "oneaiplus": {
      "max_uses": 2,
      "description": "OneAIPlus 代理服务"
    },
    "default": {
      "max_uses": 10,
      "description": "通用服务"
    }
  }
}
```

### 7.2 关键常量

| 常量 | 值 | 可调 |
|------|-----|------|
| VALIDATE_TIMEOUT | 8秒 | ✅ |
| VALIDATE_URL | chat.deepseek.com | ✅ |
| PROXY_TTL | 86400秒(24h) | ✅ |
| PROXY_COOLDOWN | 60秒 | ✅ |
| SCORE_DECAY_PER_HOUR | 0.05 | ✅ |
| QUALITY_ROUNDS | 5轮 | ⚠️ 影响验证时间 |
| MIN_READY | 10个 | ✅ |
| MAX_USES_ROUND1 | 500个 | ✅ |
| REFRESH_INTERVAL | 300秒(5min) | ✅ |

---

## 八、优化点总结（P1-P5）

| 优化 | 解决什么问题 | 实现方式 |
|------|-------------|---------|
| P1: Redis 并发锁 | 防止同一IP同时被多任务使用 | SETNX 90s |
| P2: 冷却间隔60s | 同一代理短时间内多次使用 | last_used 时间检查 |
| P3: 分数时间衰减 | 旧代理分数虚高 | 每小时-5%，最低30% |
| P4: 新增代理源 | 采集源不足 | +hookzof + MuRongPIG |
| P5: 验证间隔随机化 | 固定间隔被检测 | random.uniform(1.0, 3.0) |

---

## 九、文件清单

| 文件 | 说明 |
|------|------|
| `proxy_pool.py` | 代理池核心（采集/验证/管理） |
| `proxy_usage_logger.py` | 使用记录（异步MySQL写入） |
| `proxy_services.json` | 服务配置（max_uses） |
| `deepseek_analysis_event_driven.py` | 集成代理池（获取/验证/反馈） |
| `deepseek_anti_block.py` | 反封模块（指纹/行为模拟） |
| `verify_proxy_browser.py` | 手动验证脚本（打开浏览器测试） |

---

## 十、故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 池长时间不就绪 | 采集源全被墙 | 检查网络/换源 |
| 验证通过率低 | DeepSeek 风控升级 | 增加验证源/调整超时 |
| 同IP频繁被封 | 并发锁失效 | check Redis SETNX逻辑 |
| 代理耗尽 | 使用频率太高 | 降低use_count或增加源 |
| 日志无输出 | 缓冲区卡住 | 加 `sys.stdout.reconfigure(line_buffering=True)` |
| 国内IP不足 | 免费代理中国IP占比低 | 延长采集时间(10分钟)/多轮补充 |
| 归属地API限流 | 免费API有请求限制 | 多源轮询/缓存24小时 |

---

## 十一、国内IP筛选（v2.1新增）

### 11.1 设计约束

| 约束 | 说明 |
|------|------|
| 绝不降级 | 国内IP不足时等待，不使用海外IP |
| 不付费 | 只使用免费API和开源IP段 |
| 延长采集 | 10分钟刷新周期，给足筛选时间 |

### 11.2 IP归属地查询

```python
class IPGeoChecker:
    """IP归属地查询（多源轮询）"""
    
    API_SOURCES = [
        {"url": "http://ip-api.com/json/{ip}?fields=countryCode", "field": "countryCode"},
        {"url": "https://ipapi.co/{ip}/json/", "field": "country_code"},
    ]
    
    def get_country(self, ip: str) -> str:
        # 缓存24小时
        # 轮询多个API源
        # 返回国家代码（CN/US/...）
```

### 11.3 筛选流程

```
代理验证通过（能访问DeepSeek）
         ↓
    IP归属地查询
         ↓
    country == 'CN' ?
      → 是 → 正常入池（score正常）
      → 否 → 判0分 → 拒绝入池
         ↓
    get_proxy() 时再次检查
      → country != 'CN' → 跳过
```

### 11.4 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| REFRESH_INTERVAL | 600秒(10分钟) | 延长采集时间 |
| REQUIRE_CN_IP | True | 强制国内IP（绝不降级） |
| IP_CACHE_TTL | 86400秒(24小时) | 归属地缓存时间 |

### 11.5 预期效果

| 指标 | 目标 |
|------|------|
| 国内IP占比 | 100% |
| 池规模 | 保持 ≥10 个（通过延长采集） |
| 采集耗时 | 10-30分钟/轮（含归属地查询） |

---

*文档创建时间: 2026-06-01 04:33*  
*最后更新: 2026-06-01 05:40*
