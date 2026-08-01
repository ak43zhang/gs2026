# TDX债券行情采集IP失效不切换问题-完整排查与粘性连接方案

> 文档路径：`docs/60-实施与变更/问题修复/TDX债券行情采集IP失效不切换问题-完整排查与粘性连接方案.md`
> 目标文件：`src/gs2026/monitor/monitor_bond.py`
> 关联函数：`_get_next_server` / `_get_tdx_api` / `get_bond_tdx`

---

## 版本控制记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-08-01 | 助手 | 初稿：问题现象、根因分析、粘性连接方案设计 |
| v1.1 | 2026-08-01 | 助手 | 用户澄清需求（纯TDX机制，不用adata降级），重构方案为"粘性连接+失效换IP" |
| v1.2 | 2026-08-01 | 助手 | 文档定稿，进入实施阶段 |
| v1.3 | 2026-08-01 | 助手 | 实施完成，4项自测全部通过，已提交 |

> **本问题仅维护此单一文档，所有排查逻辑、方案迭代、实施记录、验证结果均在此文件内按版本追加，不另建文件。**

---

## 一、问题现象

用户反馈 `monitor_bond.py` 采集 TDX 行情数据时存在两个现象：

1. **现象1（为空一直空）**：采集数据为空后就一直为空，怀疑程序只使用了一个 IP，没有"IP 无数据/失效则切换 IP"的行为。
2. **现象2（下午突然变空，重启恢复）**：程序早上启动后正常采集，运行到中午；下午开盘后采集数据又变为空；但**重启程序后又能正常采集**。

### 用户明确的期望（v1.1 澄清）

- **只考虑纯 TDX 采集机制，不引入 adata/akshare 降级**（实际 TDX 数据已能满足采集需求）。
- 期望的连接机制为：**在众多有效 IP 中，如果第一个可用就一直使用它（粘性）；直到采集出现问题时，才初始化连接或切换到其他可用 IP**。

---

## 二、代码现状梳理

`monitor_bond.py` 的 TDX 采集链路已具备 IP 池与健康检查骨架：

- **IP 池来源**：`_load_tdx_servers()` 从 `configs/tdx_ips.json` 加载，失败则回退硬编码 `TDX_SERVERS`（约 17 个）。
- **健康检查**：`_tdx_server_status` 记录每个 server 的 `{healthy, fail_count, last_check}`；`_tdx_max_fail_count=3`（连续失败 3 次标记不健康）；`_tdx_health_check_interval=300`（不健康 IP 300 秒后临时恢复重试）。
- **选择服务器**：`_get_next_server()` 从健康列表中选择。
- **连接管理**：`_get_tdx_api()` 缓存连接（`_tdx_api`/`_tdx_connected`/`_tdx_last_used`），复用前做心跳检查。
- **采集主体**：`get_bond_tdx()` 拿连接 → 取债券代码（1 小时缓存）→ 每 80 只批量 `get_security_quotes` → 组装 DataFrame。

**结论**：并非"完全没有切换机制"，而是现有实现方式与用户期望相反，且存在关键状态缺失与判断缺陷。

---

## 三、根因分析

### 缺陷1：连接选择是"每次轮询换 IP"，而非"粘性复用"（与期望冲突）

`_get_next_server()`（约行 145-159）：

```python
server = healthy[_tdx_server_index % len(healthy)]
_tdx_server_index = (_tdx_server_index + 1) % len(healthy)   # 每次取完就 +1
```

每次调用都推进索引，即使当前连接完全正常，下次重连也会跳到**下一个 IP**。这与用户"第一个能用就一直用"的粘性期望**正好相反**。

### 缺陷2：没有全局变量记录"当前正在使用哪个 IP"

`_get_tdx_api()` 中 `server` 是**局部变量**，连接成功后没有保存到全局。由此导致：

- 采集失败时（`get_bond_tdx` 约行 1577-1578）只设 `_tdx_connected = False`，**不知道是哪个 IP 坏了**，无法调用 `_update_server_status(server, False)` 计入失败次数、无法把坏 IP 标记为不健康。
- 无法实现"优先复用当前好 IP"。

### 缺陷3：心跳检查不判返回值，半死连接被当作有效（现象2核心根因）

`_get_tdx_api()` 复用连接时（约行 168-173）：

```python
if _tdx_api and _tdx_connected:
    try:
        _ = _tdx_api.get_security_count(0)   # ← 未检查返回值
        _tdx_last_used = time.time()
        return _tdx_api                       # ← 直接返回可能已死的连接
    except Exception:
        ...
```

**pytdx 经典坑**：TDX 服务器对空闲连接会静默断开（尤其**午休 11:30-13:00 约 1.5 小时空闲**之后）。连接半死时，`get_security_count` **不抛异常，而是返回 None 或空**。此段代码只捕获异常、不判断返回值 → 认定"连接有效" → 返回**已死连接**。

后续 `get_security_quotes` 全部返回空 → **数据一直为空**；又因未抛异常，`_tdx_connected` 始终为 True、`_update_server_status` 从不标记该 IP → **永远不切换 IP**。重启程序后 `_tdx_api=None` 触发全新连接，故又恢复正常。

**这完整解释了"下午开盘采集变空、重启即恢复"的现象2。**

### 缺陷4：采集到空数据（非异常）不触发连接失效与换 IP（现象1核心根因）

`get_bond_tdx()` 中批量取行情（约行 1509-1519）：

```python
quotes = api.get_security_quotes(params)
if quotes:
    all_quotes.extend(quotes)
# else: 静默跳过
```

`get_security_quotes` 返回空时仅 `continue`，最终 `all_quotes` 为空 → 返回空 DataFrame。**只有抛异常**才会走到 `_tdx_connected = False`（行 1578）。半死连接返回空但不抛异常 → 连接状态永不重置 → 下一 tick 继续复用死连接 → **为空就一直为空、不换 IP**。

### 附加缺陷5：`get_bond_tdx` 无重试

对比 `get_bond_jsl` / `get_bond_adata` / `get_bond_akshare` 均有 `max_retries=3`，唯独 `get_bond_tdx` 只调用一次，单次为空即返回空，不重连、不换 IP。

---

## 四、解决方案设计（粘性连接 + 失效换 IP，纯 TDX）

### 设计核心

> **粘住当前 IP → 心跳与采集正常就一直复用 → 一旦失效（含"返回空数据"）：标记坏 IP + 关闭连接 + 从池中顺序找下一个可用 IP。**

完全不引入 adata/akshare 降级；保留现有健康检查、fail_count、300 秒恢复机制。

### 改动1：新增全局变量记录当前 IP

```python
_tdx_current_server = None   # 当前正在使用的 (host, port)
```

### 改动2：`_get_next_server` 改为"粘性 + 顺序找下一个"

```python
def _get_next_server(exclude_current=False):
    """粘性选择：优先复用当前IP；仅当排除或当前IP不健康时，顺序取下一个健康IP"""
    global _tdx_server_index
    _init_server_status()
    healthy = _get_healthy_servers()
    if not healthy:
        logger.warning("[tdx] 无健康服务器，重置全部状态")
        for s in _tdx_server_status.values():
            s['healthy'] = True
            s['fail_count'] = 0
        healthy = list(TDX_SERVERS)
    # 粘性：当前IP仍健康且不强制排除 → 继续用
    if not exclude_current and _tdx_current_server in healthy:
        return _tdx_current_server
    # 否则顺序取下一个健康IP
    if _tdx_current_server in healthy:
        idx = (healthy.index(_tdx_current_server) + 1) % len(healthy)
    else:
        idx = 0
    return healthy[idx]
```

### 改动3：`_get_tdx_api` 心跳判空 + 记录当前 IP + 失败顺序换 IP

```python
def _get_tdx_api(max_retries=None, timeout=3):
    global _tdx_api, _tdx_connected, _tdx_last_used, _tdx_current_server
    if max_retries is None:
        max_retries = len(TDX_SERVERS)   # 最多把所有IP试一遍

    # 复用：心跳必须判返回值
    if _tdx_api and _tdx_connected:
        try:
            cnt = _tdx_api.get_security_count(0)
            if cnt is None or cnt <= 0:
                raise Exception("心跳返回空，连接已死")
            _tdx_last_used = time.time()
            return _tdx_api                       # 粘性：好连接一直复用
        except Exception:
            logger.warning(f"[tdx] 当前连接失效 {_tdx_current_server}，将换IP")
            if _tdx_current_server:
                _update_server_status(_tdx_current_server, False)
            _tdx_connected = False
            try: _tdx_api.close()
            except: pass
            _tdx_api = None

    # 重连：第一次沿用粘性IP，失败后 exclude_current 顺序换下一个
    for attempt in range(max_retries):
        server = _get_next_server(exclude_current=(attempt > 0))
        host, port = server
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            api.connect(host, port, time_out=timeout)
            cnt = api.get_security_count(0)
            if cnt is None or cnt <= 0:
                raise Exception("连接后返回空")
            _tdx_api = api
            _tdx_connected = True
            _tdx_last_used = time.time()
            _tdx_current_server = server          # ← 记录当前IP
            _update_server_status(server, True)
            logger.info(f"[tdx] 连接成功: {host}:{port}" + (f"（第{attempt+1}次尝试）" if attempt > 0 else ""))
            return api
        except Exception as e:
            logger.warning(f"[tdx] 连接失败 {host}:{port}: {e}")
            _update_server_status(server, False)
            try: api.close()
            except: pass
            time.sleep(0.2)

    logger.error(f"[tdx] 全部{max_retries}个IP均连接失败")
    _tdx_current_server = None
    return None
```

### 改动4：`get_bond_tdx` 抽出主体 + 空数据判失效 + 重试换 IP

将现有 `get_bond_tdx` 函数体原样改名为 `_get_bond_tdx_once(filter_valid=True)`，新增外壳：

```python
def get_bond_tdx(filter_valid=True, max_retries=3):
    """粘性采集：正常则一直用当前IP；空数据视为当前IP失效→标记坏+换IP重试"""
    global _tdx_connected, _tdx_api, _tdx_current_server
    for attempt in range(max_retries):
        df = _get_bond_tdx_once(filter_valid)
        if not df.empty:
            return df
        # 空数据 = 当前IP有问题 → 标记坏 + 废连接换IP
        logger.warning(f"[tdx] 第{attempt+1}/{max_retries}次采集为空，换IP重试")
        if _tdx_current_server:
            _update_server_status(_tdx_current_server, False)
        _tdx_connected = False
        try:
            if _tdx_api:
                _tdx_api.close()
        except: pass
        _tdx_api = None
        time.sleep(0.3 * (attempt + 1))
    logger.error("[tdx] 连续采集为空，所有重试耗尽")
    return pd.DataFrame()
```

> `_get_bond_tdx_once` 内部保留原有 `except` 分支中的 `_tdx_connected = False`（异常路径也会触发换 IP）。

---

## 五、行为对照表

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 第一个 IP 就能用 | 每次重连都换下一个 IP | **粘住第一个，一直复用** ✅ |
| 采集正常 | 心跳可能误判 | 心跳判空，正常则复用 |
| 午休后连接死（返回空/None） | 一直空到重启 | 心跳判空 → 标记坏 → 顺序换下一个可用 IP ✅ |
| 采集返回空数据（非异常） | 一直空，不换 IP | 标记坏 IP → 换下一个重试 ✅ |
| 某 IP 彻底失效 | 可能卡住 | 连续 3 次失败标记不健康并跳过 ✅ |
| 所有 IP 都坏 | 卡死 | 重置全部状态，重试一轮 |

---

## 六、影响范围与风险

- **仅修改** `src/gs2026/monitor/monitor_bond.py`：新增 1 个全局变量、改 `_get_next_server` / `_get_tdx_api` / `get_bond_tdx`（抽出 `_get_bond_tdx_once`）。
- **不修改** adata/akshare/jsl 数据源与降级链、不动 Redis/MySQL 写入、不动其他采集逻辑。
- **保留** 现有健康检查、fail_count、300 秒恢复机制。
- **生效方式**：改完需**重启 monitor_bond.py**。
- **风险**：低。核心是"判空 + 记录当前 IP + 粘性选择"，逻辑增量清晰，无破坏性删除。

---

## 七、实施记录

> 实施进度、Git 提交哈希、自测结果在此追加。

- [x] 新增全局变量 `_tdx_current_server`
- [x] 改造 `_get_next_server`（粘性 + 顺序换 IP）
- [x] 改造 `_get_tdx_api`（心跳判空 + 记录当前 IP + 失败顺序换 IP）
- [x] 抽出 `_get_bond_tdx_once`，新增 `get_bond_tdx` 重试外壳
- [x] 语法检查通过（`py_compile`）
- [x] AST 校验：四个函数均单一定义，无重复定义
- [x] 模拟测试：心跳返回 None → 触发标记坏 IP + 换 IP
- [x] 模拟测试：采集返回空 → 触发换 IP 重试
- [x] Git 提交

### 实施后关键行号（供追溯）

| 函数 | 行号 |
|------|------|
| `_get_next_server` | 146 |
| `_get_tdx_api` | 177 |
| `get_bond_tdx`（重试外壳） | 1500 |
| `_get_bond_tdx_once`（原采集主体） | 1531 |

### 自测结果（`_test_tdx_sticky.py`）

```
[PASS] 粘性验证通过        —— 连接正常时连续返回同一IP
[PASS] 顺序换IP通过        —— exclude_current 后取列表下一个健康IP
[PASS] 不健康IP跳过通过    —— 当前IP连续失败3次标记不健康后自动跳过
[PASS] 采集空换IP重试通过  —— get_bond_tdx 空数据3次重试，每次标记坏IP并换IP
```

### 生效方式

需重启 `monitor_bond.py` 后生效。建议盘中观察日志：正常时段应稳定复用单一 IP（无频繁切换）；仅在心跳判空/采集为空时才出现 `换IP` 日志。

---

## 八、验证方案

1. **粘性验证**：连续多次调用 `_get_tdx_api()`，确认返回同一 IP（`_tdx_current_server` 不变）。
2. **心跳判空验证**：Mock `get_security_count` 返回 None，确认触发重连并 `_update_server_status(坏IP, False)`。
3. **采集空验证**：Mock `_get_bond_tdx_once` 返回空 DataFrame，确认 `get_bond_tdx` 标记坏 IP、换 IP 并重试。
4. **换 IP 顺序验证**：当前 IP 标记不健康后，确认 `_get_next_server(exclude_current=True)` 返回列表中的下一个健康 IP。
5. **盘中实测**：重启后观察日志，确认正常时段稳定复用单一 IP，无频繁切换。
