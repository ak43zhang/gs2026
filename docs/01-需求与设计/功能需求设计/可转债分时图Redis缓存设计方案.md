# 可转债分时图Redis缓存设计方案

> 版本: v1.0  
> 日期: 2026-07-20  
> 关联模块: monitor_bond.py, dashboard2, Redis  
> 设计目标: 加速单债券分时数据查询，支持毫秒级响应

---

## 一、需求背景

### 1.1 当前痛点

在GS2026可转债监控系统中，用户需要查看单个债券的分时图数据时，面临以下问题：

| 痛点 | 说明 | 影响 |
|------|------|------|
| 查询效率低 | MySQL按债券查询需遍历全表 | 单次查询1-2秒 |
| 用户体验差 | 鼠标悬停显示分时图延迟高 | 交互卡顿 |
| 扩展受限 | 无法支持实时曲线、多维度分析 | 功能受限 |
| 资源浪费 | 频繁查询相同数据 | MySQL负载高 |

### 1.2 典型使用场景

1. **鼠标悬停分时图**: 用户在监控界面鼠标移动到债券代码上，即时显示当日分时走势
2. **单债券多维分析**: 查看某债券的价格、涨跌幅、成交额等多维度曲线
3. **历史回溯对比**: 对比不同日期的同一债券走势
4. **实时预警分析**: 快速获取债券全天数据进行异常检测

---

## 二、设计目标

### 2.1 核心目标

| 目标 | 指标 | 说明 |
|------|------|------|
| 查询速度 | < 100ms | 单债券全天数据查询 |
| 写入开销 | < 10ms/tick | 不显著影响实时写入性能 |
| 数据一致性 | 最终一致 | MySQL为主，Redis为缓存 |
| 可靠性 | 99.9% | Redis宕机可自动降级恢复 |

### 2.2 非功能需求

- **生命周期**: 当日有效，次日8点自动清理
- **容量规划**: 支持300+债券，全天4800+tick
- **容错能力**: Redis故障自动降级到MySQL
- **恢复机制**: 非交易时间自动从MySQL恢复

---

## 三、架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     可转债分时图缓存架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│   │   前端页面    │──────▶│  API Gateway  │──────▶│  Redis Cache │  │
│   │  (分时图展示) │      │  (优先Redis)  │      │  (内存缓存)   │  │
│   └──────────────┘      └──────┬─────────┘      └──────┬───────┘  │
│                                │                      │          │
│                                ▼                      ▼          │
│                         ┌──────────────┐      ┌──────────────┐  │
│                         │   MySQL      │◀─────│  定时恢复    │  │
│                         │  (主存储)     │      │  (交易时间外) │  │
│                         └──────────────┘      └──────────────┘  │
│                                                                  │
│   ┌──────────────┐      ┌──────────────┐                        │
│   │ monitor_bond │─────▶│  双写机制    │                        │
│   │  (实时采集)   │      │ (MySQL+Redis)│                        │
│   └──────────────┘      └──────────────┘                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流向

```
实时写入流程:
  monitor_bond.py ──▶ 解析tick数据 ──▶ 写入MySQL ──▶ 异步写入Redis
                                           │              │
                                           ▼              ▼
                                     主存储(可靠)      缓存(快速)

查询流程:
  前端请求 ──▶ API ──▶ 检查Redis ──▶ 命中? ──▶ 是 ──▶ 返回数据(10ms)
                          │           │
                          │           否
                          │           ▼
                          │      查询MySQL ──▶ 异步回填Redis
                          │           │
                          └───────────┴────▶ 返回数据(1-2s)
```

---

## 四、数据模型设计

### 4.1 Redis Key设计

| Key模式 | 类型 | 说明 | 示例 |
|---------|------|------|------|
| `bond:tick:{code}:{date}` | Hash | 单债券全天数据 | `bond:tick:110072:20260720` |
| `bond:tick:index:{date}` | Set | 当日债券索引 | `bond:tick:index:20260720` |
| `bond:tick:meta:{date}` | Hash | 元数据统计 | `bond:tick:meta:20260720` |

### 4.2 Hash字段结构

```redis
# Key: bond:tick:110072:20260720
# Field: 时间字符串 (HH:MM:SS)
# Value: JSON字符串

HSET "bond:tick:110072:20260720" "09:30:03" '{
    "time": "09:30:03",
    "price": 115.50,
    "change_pct": 2.35,
    "amount": 1250000,
    "volume": 10850,
    "high": 115.80,
    "low": 115.20,
    "open": 115.00,
    "pre_close": 112.80,
    "ext_indicators": {
        "weighted_slope_2m": 0.05,
        "weighted_slope_5m": 0.12,
        "change_1m_pct": 0.08
    }
}'
```

### 4.3 数据示例

```redis
# 索引 - 记录当日所有债券
SADD "bond:tick:index:20260720" "110072"
SADD "bond:tick:index:20260720" "110073"
SADD "bond:tick:index:20260720" "110075"
# ... 共300+个

# 元数据 - 统计信息
HSET "bond:tick:meta:20260720" "total_bonds" "320"
HSET "bond:tick:meta:20260720" "total_ticks" "4800"
HSET "bond:tick:meta:20260720" "last_update" "2026-07-20T15:00:03"
HSET "bond:tick:meta:20260720" "redis_memory_mb" "450"
```

---

## 五、核心模块设计

### 5.1 BondTickCache - 缓存管理器

```python
class BondTickCache:
    """
    可转债分时图Redis缓存管理器
    
    职责:
    1. 单条/批量写入tick数据
    2. 按债券查询全天数据
    3. 按时间范围查询
    4. 自动过期管理
    5. 故障检测与降级
    """
    
    def write_tick(self, bond_code: str, time_str: str, data: dict) -> bool
    def write_batch(self, bond_code: str, ticks: list) -> bool
    def get_all_ticks(self, bond_code: str, date: str = None) -> list
    def get_time_range(self, bond_code: str, start: str, end: str) -> list
    def check_health(self) -> bool
    def clear_expired(self, date: str = None) -> int
```

### 5.2 BondTickRecovery - 恢复管理器

```python
class BondTickRecovery:
    """
    MySQL数据恢复管理器
    
    职责:
    1. 检测Redis数据缺失
    2. 非交易时间从MySQL恢复
    3. 批量恢复优化
    4. 进度监控
    """
    
    def is_trading_hours(self) -> bool
    def recover_bond(self, bond_code: str, date: str = None) -> bool
    def recover_all(self, date: str = None, progress_callback=None) -> dict
```

### 5.3 双写集成点

```python
# monitor_bond.py 集成

def save_tick_data(bond_code: str, time_str: str, data: dict):
    """
    保存tick数据 - 双写模式
    
    流程:
    1. 写入MySQL（同步，必须成功）
    2. 异步写入Redis（失败不影响主流程）
    """
    # 1. 主存储 - MySQL
    success = write_to_mysql(bond_code, time_str, data)
    
    if success:
        # 2. 缓存 - Redis（异步，非阻塞）
        threading.Thread(
            target=_write_to_redis,
            args=(bond_code, time_str, data),
            daemon=True
        ).start()
    
    return success
```

---

## 六、性能分析

### 6.1 写入性能影响

| 场景 | 债券数 | 写入方式 | 耗时 | 说明 |
|------|--------|----------|------|------|
| 单条逐个 | 300 | 300次HSET | ~600ms | ❌ 太慢，不可接受 |
| 批量pipeline | 300 | 1次pipeline | ~5-10ms | ✅ 推荐 |
| 异步批量 | 300 | 后台线程 | ~0ms | ✅ 最佳，不阻塞 |

**结论**: 采用异步批量pipeline写入，每tick增加**<1ms**开销，可忽略。

### 6.2 查询性能对比

| 查询方式 | 首次查询 | 缓存命中 | 数据量 |
|----------|----------|----------|--------|
| MySQL全表扫描 | 1-2秒 | - | 150万行 |
| MySQL索引查询 | 200-500ms | - | 4800行 |
| Redis Hash全取 | 5-10ms | 100% | 4800字段 |
| Redis单条 | <1ms | 100% | 1字段 |

**提升效果**: 查询速度提升 **100-200倍**

### 6.3 内存占用估算

| 项目 | 数值 | 计算说明 |
|------|------|----------|
| 债券数量 | 320只 | 实际可转债数量 |
| 每债券tick数 | 4,800个 | 3秒×4小时×2（上下午） |
| 单条JSON大小 | ~200字节 | 含扩展指标 |
| 单债券数据 | ~960KB | 4800×200字节 |
| 全天总数据 | ~300MB | 320×960KB |
| Redis索引开销 | ~50MB | Set+Hash索引 |
| **总计** | **~350MB** | 可接受范围 |

### 6.4 网络开销

```
Pipeline批量写入:
  - 命令打包: 300个HSET命令
  - 单次RTT: ~5ms（本地Redis）
  - 带宽占用: ~100KB/次
  - 频率: 每3秒一次
  - 日总流量: ~100MB
```

---

## 七、容错与降级设计

### 7.1 Redis故障处理

```python
class BondTickCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.enabled = True          # 可用状态
        self.fail_count = 0          # 连续失败次数
        self.max_fail = 3            # 最大容忍失败次数
    
    def _handle_error(self, e):
        """错误处理与自动降级"""
        self.fail_count += 1
        
        if self.fail_count >= self.max_fail:
            self.enabled = False
            logger.error("[Redis] 连续失败3次，标记为不可用，降级到MySQL")
            
            # 启动恢复检测线程
            threading.Thread(target=self._recovery_check, daemon=True).start()
    
    def _recovery_check(self):
        """定期检测Redis是否恢复"""
        while not self.enabled:
            time.sleep(60)  # 每分钟检测
            try:
                self.redis.ping()
                self.enabled = True
                self.fail_count = 0
                logger.info("[Redis] 已恢复，重新启用缓存")
            except:
                pass
```

### 7.2 数据一致性保障

| 策略 | 说明 |
|------|------|
| 写顺序 | 先MySQL后Redis，MySQL为准 |
| 失败处理 | Redis写入失败不影响MySQL |
| 恢复机制 | 非交易时间自动从MySQL回填 |
| 过期清理 | 次日8点自动清理，避免脏数据 |

### 7.3 交易时间保护

```python
def is_trading_hours() -> bool:
    """
    判断是否在交易时间
    
    交易时间:
    - 上午: 09:30 - 11:30
    - 下午: 13:00 - 15:00
    - 周末: 非交易
    """
    now = datetime.now()
    
    if now.weekday() >= 5:  # 周六日
        return False
    
    current_time = now.time()
    morning = time(9, 30) <= current_time <= time(11, 30)
    afternoon = time(13, 0) <= current_time <= time(15, 0)
    
    return morning or afternoon

# 恢复策略
if not is_trading_hours():
    # 执行恢复，不影响交易
    recovery.recover_all()
else:
    # 交易时间，跳过恢复
    logger.info("[Recovery] 交易时间内，跳过恢复")
```

---

## 八、使用好处说明

### 8.1 对用户的好处

| 好处 | 说明 |
|------|------|
| **秒开分时图** | 鼠标悬停即时显示，无等待 |
| **流畅交互** | 支持快速切换查看不同债券 |
| **多维分析** | 可同时查看价格、成交量、指标等多曲线 |
| **历史对比** | 快速对比不同日期同一债券走势 |

### 8.2 对系统的好处

| 好处 | 说明 |
|------|------|
| **减轻MySQL压力** | 高频查询转移到Redis，降低90%+数据库负载 |
| **提升并发能力** | Redis支持10万+QPS，无性能瓶颈 |
| **降低响应延迟** | 从秒级降到毫秒级，提升用户体验 |
| **节省计算资源** | 避免重复查询和排序，减少CPU消耗 |

### 8.3 对开发的好处

| 好处 | 说明 |
|------|------|
| **简化查询逻辑** | 单key查询替代复杂SQL |
| **统一数据接口** | 前后端数据格式一致 |
| **易于扩展** | 支持更多实时分析功能 |
| **故障隔离** | Redis故障不影响核心业务 |

---

## 九、API设计

### 9.1 获取单债券全天数据

```http
GET /api/bond/ticks/{bond_code}?date=20260720

Response:
{
    "success": true,
    "source": "redis",           // redis 或 mysql
    "bond_code": "110072",
    "date": "20260720",
    "count": 4800,
    "data": [
        {
            "time": "09:30:03",
            "price": 115.50,
            "change_pct": 2.35,
            "amount": 1250000,
            ...
        },
        ...
    ]
}
```

### 9.2 获取时间范围数据

```http
GET /api/bond/ticks/{bond_code}?start_time=10:00:00&end_time=11:00:00

Response:
{
    "success": true,
    "source": "redis",
    "count": 1200,  // 1小时 = 1200个tick
    "data": [...]
}
```

### 9.3 缓存状态检查

```http
GET /api/bond/ticks/status

Response:
{
    "redis_connected": true,
    "total_bonds_cached": 320,
    "memory_used_mb": 450,
    "last_update": "2026-07-20T15:00:03"
}
```

---

## 十、实施步骤

### 阶段一: 核心功能开发 (1-2天)

1. [ ] 创建 `src/gs2026/redis/bond_redis_cache.py`
2. [ ] 实现 BondTickCache 核心类
3. [ ] 单元测试验证读写性能

### 阶段二: 集成与API (1-2天)

4. [ ] 修改 `monitor_bond.py` 集成双写
5. [ ] 创建 `src/gs2026/dashboard2/routes/bond_ticks.py`
6. [ ] 实现查询API（优先Redis，降级MySQL）

### 阶段三: 恢复与监控 (1天)

7. [ ] 创建 `src/gs2026/redis/bond_redis_recovery.py`
8. [ ] 实现非交易时间自动恢复
9. [ ] 添加定时任务（清理+恢复检查）

### 阶段四: 前端集成 (1-2天)

10. [ ] 前端调用新API显示分时图
11. [ ] 添加数据来源标识（Redis/MySQL）
12. [ ] 性能测试与优化

### 阶段五: 上线与监控 (持续)

13. [ ] 灰度发布（部分债券）
14. [ ] 监控Redis内存和命中率
15. [ ] 根据反馈调整参数

---

## 十一、风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| Redis内存不足 | 低 | 高 | 监控+自动过期 |
| Redis宕机 | 低 | 中 | 自动降级+恢复 |
| 写入性能下降 | 低 | 中 | 异步写入+批量 |
| 数据不一致 | 低 | 中 | MySQL为准+恢复 |

---

## 十二、附录

### 12.1 相关文件

| 文件 | 说明 |
|------|------|
| `src/gs2026/redis/bond_redis_cache.py` | 缓存核心实现 |
| `src/gs2026/redis/bond_redis_recovery.py` | 恢复管理器 |
| `src/gs2026/redis/__init__.py` | 模块初始化 |
| `src/gs2026/monitor/monitor_bond.py` | 双写集成点 |
| `src/gs2026/dashboard2/routes/bond_ticks.py` | API路由 |

### 12.2 参考文档

- Redis Hash命令: https://redis.io/commands#hash
- Redis Pipeline: https://redis.io/topics/pipelining
- Flask异步处理: https://flask.palletsprojects.com/

---

**设计完成，等待审核确认后实施。**
