# Redis连接超时问题修复方案

> 问题: `redis.exceptions.TimeoutError: Timeout reading from socket`
> 位置: `save_dataframe_to_redis` 函数

---

## 问题分析

### 错误堆栈
```
monitor_stock.py:611 → save_dataframe_to_redis
redis_util.py:170 → client.setex(key, expire_seconds, data_json)
```

### 可能原因

1. **Redis服务器负载高**: 数据量大时写入慢
2. **网络延迟**: 连接Redis服务器超时
3. **数据过大**: 单条数据超过Redis限制或写入时间过长
4. **连接池耗尽**: 并发连接过多
5. **Redis配置问题**: 超时时间设置过短

---

## 修复方案

### 方案A: 增加超时时间和重试机制（推荐）

修改 `redis_util.py` 中的连接配置和保存函数。

**1. 修改Redis连接配置**

```python
# redis_util.py 中 get_redis_client 函数

def get_redis_client():
    """获取Redis客户端（带连接池和超时配置）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_CONFIG['host'],
            port=REDIS_CONFIG['port'],
            db=REDIS_CONFIG['db'],
            password=REDIS_CONFIG.get('password'),
            decode_responses=True,
            # 新增超时配置
            socket_connect_timeout=10,      # 连接超时10秒
            socket_timeout=30,               # 操作超时30秒
            health_check_interval=30,        # 健康检查间隔
            # 连接池配置
            connection_pool_class_kwargs={
                'max_connections': 50,       # 最大连接数
                'retry_on_timeout': True,     # 超时重试
            }
        )
    return _redis_client
```

**2. 修改 save_dataframe_to_redis 函数**

```python
def save_dataframe_to_redis(df: pd.DataFrame, table_name: str, time_str: str, 
                            expire_seconds: int = 86400, use_compression: bool = True,
                            max_retries: int = 3) -> bool:
    """
    保存DataFrame到Redis（带重试机制）
    
    Args:
        df: DataFrame数据
        table_name: 表名
        time_str: 时间字符串
        expire_seconds: 过期时间（秒）
        use_compression: 是否使用压缩
        max_retries: 最大重试次数
    """
    if df is None or df.empty:
        logger.warning(f"DataFrame为空，跳过保存: {table_name}")
        return False
    
    key = f"{table_name}:{time_str}"
    
    for attempt in range(max_retries):
        try:
            client = get_redis_client()
            
            # 数据序列化
            if use_compression:
                # 使用压缩减少数据大小
                json_str = df.to_json(orient='records', date_format='iso')
                data_bytes = json_str.encode('utf-8')
                
                # 如果数据过大，使用压缩
                if len(data_bytes) > 1024 * 1024:  # 超过1MB使用压缩
                    import zlib
                    compressed = zlib.compress(data_bytes, level=6)
                    data_json = base64.b64encode(compressed).decode('utf-8')
                    key = f"{key}:compressed"
                    logger.debug(f"数据压缩: {len(data_bytes)} -> {len(compressed)} bytes")
                else:
                    data_json = json_str
            else:
                data_json = df.to_json(orient='records', date_format='iso')
            
            # 保存到Redis
            client.setex(key, expire_seconds, data_json)
            
            logger.debug(f"DataFrame已保存到Redis: {key}, 行数: {len(df)}, 大小: {len(data_json)} bytes")
            return True
            
        except redis.exceptions.TimeoutError as e:
            logger.warning(f"Redis写入超时 (尝试 {attempt + 1}/{max_retries}): {key}, 错误: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                # 重置连接
                global _redis_client
                _redis_client = None
            else:
                logger.error(f"Redis写入失败，已达最大重试次数: {key}")
                raise
                
        except Exception as e:
            logger.error(f"Redis写入失败: {key}, 错误: {e}")
            raise
    
    return False
```

**3. 修改 load_dataframe_by_key 函数支持压缩数据**

```python
def load_dataframe_by_key(key: str) -> Optional[pd.DataFrame]:
    """
    从Redis加载DataFrame（支持压缩数据）
    """
    try:
        client = get_redis_client()
        data_json = client.get(key)
        
        if data_json is None:
            return None
        
        # 检查是否是压缩数据
        if key.endswith(':compressed'):
            import zlib
            compressed = base64.b64decode(data_json)
            data_bytes = zlib.decompress(compressed)
            data_json = data_bytes.decode('utf-8')
        
        # 解析JSON
        data = json.loads(data_json)
        df = pd.DataFrame(data)
        
        return df
        
    except Exception as e:
        logger.error(f"从Redis加载DataFrame失败: {key}, 错误: {e}")
        return None
```

---

### 方案B: 分批次写入（大数据量）

如果数据量特别大，可以分批次写入：

```python
def save_dataframe_to_redis_chunked(df: pd.DataFrame, table_name: str, time_str: str,
                                     expire_seconds: int = 86400, chunk_size: int = 1000) -> bool:
    """分批次保存DataFrame到Redis"""
    if df is None or df.empty:
        return False
    
    total_rows = len(df)
    chunks = (total_rows + chunk_size - 1) // chunk_size
    
    for i in range(chunks):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, total_rows)
        chunk_df = df.iloc[start_idx:end_idx]
        
        key = f"{table_name}:{time_str}:chunk:{i}"
        try:
            client = get_redis_client()
            data_json = chunk_df.to_json(orient='records')
            client.setex(key, expire_seconds, data_json)
            logger.debug(f"保存数据块 {i+1}/{chunks}: {key}, 行数: {len(chunk_df)}")
        except Exception as e:
            logger.error(f"保存数据块失败: {key}, 错误: {e}")
            raise
    
    # 保存元数据
    meta_key = f"{table_name}:{time_str}:meta"
    meta = {'chunks': chunks, 'total_rows': total_rows, 'chunk_size': chunk_size}
    client.setex(meta_key, expire_seconds, json.dumps(meta))
    
    return True
```

---

### 方案C: 检查Redis服务器状态

```python
def check_redis_health() -> dict:
    """检查Redis服务器健康状态"""
    try:
        client = get_redis_client()
        info = client.info()
        return {
            'status': 'healthy',
            'used_memory': info.get('used_memory_human', 'N/A'),
            'connected_clients': info.get('connected_clients', 0),
            'blocked_clients': info.get('blocked_clients', 0),
        }
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}
```

---

## 推荐实施方案

### 优先级

1. **立即实施**: 方案A（增加超时和重试）
2. **观察效果**: 如果仍有问题，实施方案B（分批次写入）
3. **监控**: 添加Redis健康检查

### 修改文件

- `src/gs2026/utils/redis_util.py`
  - 修改 `get_redis_client()` 增加超时配置
  - 修改 `save_dataframe_to_redis()` 增加重试机制
  - 修改 `load_dataframe_by_key()` 支持压缩数据

### 预期效果

- 减少超时错误
- 提高写入成功率
- 大数据量时自动压缩，减少传输时间

---

**方案状态**: 待审核
