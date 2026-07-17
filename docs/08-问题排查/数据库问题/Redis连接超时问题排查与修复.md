# Redis 连接超时问题排查与修复

**文档版本**: v1.0  
**创建日期**: 2026-04-20  
**问题类型**: Redis 连接超时  
**影响范围**: 所有使用 Redis 的模块

---

## 一、问题现象

### 错误信息
```
redis.exceptions.TimeoutError: Timeout reading from socket
```

### 发生位置
- `monitor_dp_signal.py:31` - `redis_util.get_dict("data_bond_ths")`
- 多个程序同时出现

### 问题特征
- 之前未出现，突然发生
- 多个程序同时报错
- Redis 连接超时，非特定操作

---

## 二、根因分析

### 直接原因
Redis 服务器连接超时，无法响应客户端请求。

### 可能原因

| 原因 | 可能性 | 验证方法 |
|------|--------|----------|
| Redis 服务未启动 | 高 | `redis-cli ping` |
| 网络问题 | 中 | `telnet localhost 6379` |
| 连接数耗尽 | 中 | `INFO clients` |
| 长时间连接未释放 | 高 | `CLIENT LIST` 检查 idle 时间 |
| 防火墙/安全软件 | 低 | 检查系统日志 |

### 诊断结果（2026-04-20 10:27）
- Redis 连接测试失败，超时错误
- 无法获取连接数和客户端列表
- **初步判断**: Redis 服务异常或网络问题

---

## 三、修复方案

### 3.1 紧急修复（立即实施）

即使 Redis 服务恢复，也需要增强程序的容错能力。

#### 1. 增强 `_get_redis_client` - 健康检查

```python
def _get_redis_client(check_health: bool = False) -> Optional[redis.Redis]:
    """
    获取全局 Redis 客户端，带健康检查
    
    Args:
        check_health: 是否检查连接健康
        
    Returns:
        Redis 客户端或 None（未初始化或不可用）
    """
    global _redis_client, _redis_pool
    
    if _redis_client is None:
        logger.warning("Redis 客户端未初始化")
        return None
    
    if check_health:
        try:
            # 快速健康检查（1秒超时）
            _redis_client.ping()
        except Exception as e:
            logger.error(f"Redis 健康检查失败: {e}")
            return None
    
    return _redis_client
```

#### 2. 修改 `get_dict` - 带异常处理和降级

```python
def get_dict(table_name: str) -> Optional[pd.DataFrame]:
    """
    获取字典数据，Redis 失败时返回 None
    
    调用方需要处理返回 None 的情况
    """
    # 尝试从 Redis 读取
    client = _get_redis_client(check_health=True)
    if client is None:
        logger.warning(f"Redis 不可用，跳过字典 {table_name}")
        return None
    
    try:
        data = client.get("dict:" + table_name)
        if data:
            json_str = data.decode('utf-8') if isinstance(data, bytes) else data
            df = pd.read_json(io.StringIO(json_str), orient='records')
            logger.info(f"从 Redis 加载字典 {table_name}: {len(df)} 条")
            return df
        return None
    except (redis.exceptions.TimeoutError, redis.exceptions.ConnectionError) as e:
        logger.error(f"Redis 读取超时/连接错误: {e}")
        return None
    except Exception as e:
        logger.error(f"Redis 读取异常: {e}")
        return None
```

#### 3. 修改调用方 - 异常处理

```python
# monitor_dp_signal.py 等程序
mid_df = redis_util.get_dict("data_bond_ths")
if mid_df is None:
    logger.error("无法获取字典数据，程序退出")
    sys.exit(1)  # 或采用降级方案
```

#### 4. 优化连接池配置

```python
def init_redis(
    host: str = 'localhost',
    port: int = 6379,
    max_connections: int = 100,  # 增加连接数
    socket_connect_timeout: int = 3,
    socket_timeout: int = 5,
    retry_on_timeout: bool = True,
    health_check_interval: int = 30,
    socket_keepalive: bool = True,  # 保持连接
) -> None:
    """初始化 Redis 连接池，优化配置"""
```

### 3.2 长期优化（后续）

1. **MySQL 降级方案** - Redis 失败时从 MySQL 加载
2. **统一装饰器** - 为所有 Redis 操作添加重试和降级
3. **监控告警** - Redis 异常时发送告警通知
4. **连接池监控** - 实时监控连接使用情况

---

## 四、实施步骤

### 第一步：检查 Redis 服务状态
```bash
# 检查 Redis 服务
redis-cli ping

# 检查连接数
redis-cli INFO clients

# 检查连接列表
redis-cli CLIENT LIST
```

### 第二步：实施代码修复
1. 修改 `redis_util.py`
   - 增强 `_get_redis_client`
   - 修改 `get_dict`
   - 优化 `init_redis`

2. 修改调用方程序
   - `monitor_dp_signal.py`
   - 其他使用 Redis 的程序

### 第三步：验证修复
1. 重启 Redis 服务（如需要）
2. 启动程序验证
3. 监控日志确认无超时错误

---

## 五、预防措施

1. **Redis 服务监控** - 使用 systemd 或 supervisor 守护
2. **连接池配置优化** - 根据并发量调整 max_connections
3. **定期清理空闲连接** - 设置 timeout 参数
4. **程序容错设计** - 所有外部依赖都要有降级方案

---

## 六、相关文件

- `src/gs2026/utils/redis_util.py`
- `src/gs2026/monitor/monitor_dp_signal.py`
- 其他使用 Redis 的模块

---

*创建时间: 2026-04-20 10:27*  
*问题状态: 待修复*
