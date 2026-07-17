# monitor_bond.py 中 get_bond_tdx 连接策略分析

## 一、两种方案对比

### 方案A：每次调用新建连接（当前实现）

```python
def get_bond_tdx():
    api = TdxHq_API()
    api.connect(host, port)  # 每次新建连接
    try:
        # 获取数据...
    finally:
        api.disconnect()  # 用完即关
```

**优点**：
- 简单，无状态，每次调用独立
- 连接断开后自动重连，容错性好
- 无连接池管理复杂度

**缺点**：
- 每3秒新建一次TCP连接（开销约20-50ms）
- 频繁connect/disconnect增加服务器压力
- 高并发时可能触发服务器连接限制

---

### 方案B：启动时连接一次，全局复用（建议方案）

```python
# 全局连接（模块级）
_tdx_api = None
_tdx_connected = False

def _init_tdx_connection():
    """初始化TDX连接（只执行一次）"""
    global _tdx_api, _tdx_connected
    if _tdx_connected and _tdx_api:
        return True
    
    _tdx_api = TdxHq_API()
    for host, port in TDX_SERVERS:
        try:
            _tdx_api.connect(host, port, time_out=5)
            _tdx_connected = True
            logger.info(f"[tdx] 连接成功: {host}:{port}")
            return True
        except Exception as e:
            logger.warning(f"[tdx] 连接失败 {host}:{port}: {e}")
    return False

def get_bond_tdx():
    """获取行情，复用已有连接"""
    global _tdx_connected
    
    # 确保连接
    if not _init_tdx_connection():
        return pd.DataFrame()
    
    try:
        # 获取数据...
        quotes = _tdx_api.get_security_quotes(...)
        return df
    except Exception as e:
        logger.error(f"[tdx] 获取失败: {e}")
        _tdx_connected = False  # 标记断开，下次重连
        return pd.DataFrame()
```

**优点**：
- 只连接一次，节省20-50ms/次
- 减少服务器连接压力
- 长连接下TCP性能更稳定

**缺点**：
- 需要处理连接断开重连
- 长时间运行可能遇到服务器踢人（空闲超时）
- 需要心跳检测机制

---

## 二、推荐方案：连接池 + 自动重连

### 2.1 设计

```python
class TdxConnectionPool:
    """
    TDX连接管理器
    - 启动时连接
    - 自动重连
    - 心跳检测
    """
    
    _instance = None
    _api = None
    _connected = False
    _last_used = 0
    _lock = threading.Lock()
    
    # 配置
    HEARTBEAT_INTERVAL = 30  # 30秒心跳
    RECONNECT_DELAY = 5      # 重连间隔5秒
    
    @classmethod
    def get_api(cls):
        """获取API实例（自动连接/重连）"""
        with cls._lock:
            # 检查是否需要重连
            if cls._api and not cls._is_alive():
                cls._disconnect()
            
            # 连接
            if not cls._connected:
                cls._connect()
            
            cls._last_used = time.time()
            return cls._api if cls._connected else None
    
    @classmethod
    def _connect(cls):
        """建立连接"""
        cls._api = TdxHq_API()
        for host, port in TDX_SERVERS:
            try:
                cls._api.connect(host, port, time_out=5)
                cls._connected = True
                logger.info(f"[tdx] 连接成功: {host}:{port}")
                return
            except Exception as e:
                logger.warning(f"[tdx] 连接失败 {host}:{port}: {e}")
        cls._connected = False
    
    @classmethod
    def _disconnect(cls):
        """断开连接"""
        if cls._api:
            try:
                cls._api.disconnect()
            except:
                pass
            cls._api = None
        cls._connected = False
    
    @classmethod
    def _is_alive(cls):
        """检测连接是否存活（简单ping）"""
        if not cls._api:
            return False
        try:
            # 简单查询测试
            cls._api.get_security_count(0)
            return True
        except:
            return False
    
    @classmethod
    def heartbeat(cls):
        """心跳检测（由monitor_bond主循环定期调用）"""
        if time.time() - cls._last_used > cls.HEARTBEAT_INTERVAL:
            cls.get_api()  # 触发连接检查


# 使用方式
def get_bond_tdx():
    api = TdxConnectionPool.get_api()
    if not api:
        return pd.DataFrame()
    
    try:
        # 获取行情...
        quotes = api.get_security_quotes(...)
        return df
    except Exception as e:
        logger.error(f"[tdx] 请求失败: {e}")
        # 下次调用会自动重连
        return pd.DataFrame()
```

### 2.2 集成到 monitor_bond.py

```python
# 在 monitor_bond.py 顶部初始化
from gs2026.utils.tdx_pool import TdxConnectionPool

# 主循环中定期心跳
while True:
    # 心跳检测（每30秒）
    TdxConnectionPool.heartbeat()
    
    # 获取数据
    df = get_bond_tdx()  # 内部自动处理连接
    
    # 处理...
    time.sleep(3)
```

---

## 三、性能对比

| 指标 | 方案A（每次新建） | 方案B（连接池） | 提升 |
|------|------------------|----------------|------|
| 单次获取延迟 | 80-120ms | 30-60ms | **2倍** |
| 连接开销 | 20-50ms/次 | 0ms（复用） | 节省100% |
| 服务器连接数 | 每3秒新建 | 1个长连接 | 压力小 |
| 稳定性 | 高（无状态） | 中（需处理重连） | - |
| 复杂度 | 低 | 中 | - |

---

## 四、建议

### 推荐：方案B（连接池）

**理由**：
1. **性能提升明显**：每次节省20-50ms连接开销
2. **服务器友好**：减少频繁connect/disconnect
3. **可管理**：自动重连、心跳检测
4. **风险可控**：重连逻辑简单，失败时降级为空DataFrame

**前提条件**：
- TDX服务器支持长连接（通常支持）
- 空闲超时 > 30秒（需验证）

### 验证步骤

1. **测试长连接稳定性**：
   ```python
   # 保持连接5分钟，每30秒查询一次
   api = TdxHq_API()
   api.connect(host, port)
   for i in range(10):
       time.sleep(30)
       quotes = api.get_security_quotes([...])  # 测试是否仍然有效
       print(f"第{i+1}次: {'成功' if quotes else '失败'}")
   ```

2. **测试空闲超时**：
   - 连接后等待1分钟不操作
   - 再查询，看是否仍然有效

3. **如果长连接稳定** → 实施连接池方案

4. **如果频繁断开** → 保持当前方案（每次新建）

---

## 五、实施计划

| 步骤 | 内容 | 验证通过后实施 |
|------|------|--------------|
| 1 | 测试长连接稳定性（5分钟） | 是 |
| 2 | 测试空闲超时（1分钟） | 是 |
| 3 | 创建 tdx_pool.py 模块 | 是 |
| 4 | 修改 get_bond_tdx() 使用连接池 | 是 |
| 5 | 主循环集成心跳检测 | 是 |
| 6 | 实盘运行验证 | 是 |

---

## 六、风险与应对

| 风险 | 应对 |
|------|------|
| 服务器踢人（空闲超时） | 心跳检测每30秒查询一次 |
| 网络闪断 | 自动重连，失败返回空DF |
| 长时间运行内存泄漏 | 定期（如每天）强制重建连接 |
| 并发问题 | 加锁保护连接状态 |

---

**结论**：建议实施连接池方案，但先验证长连接稳定性。
