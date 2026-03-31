# 慢查询/慢请求/前端慢资源持久化存储 - 实施完成报告

## 实施时间
2026-03-31

## 实施内容

### 阶段1: 数据库表创建 ✓

创建了3个数据表：

1. **slow_requests** - 慢请求记录表
   - 存储API慢请求信息
   - 包含：时间、方法、路径、耗时、状态码、DB/Redis指标等
   - 索引：created_at, request_date, path, duration_ms

2. **slow_queries** - 慢查询记录表
   - 存储数据库慢查询信息
   - 包含：SQL语句、SQL哈希、SQL类型、表名、参数等
   - 索引：created_at, query_date, sql_hash, table_name, duration_ms

3. **slow_frontend_resources** - 前端慢资源加载记录表
   - 存储前端慢资源加载信息
   - 包含：资源类型、URL、耗时、传输大小、页面URL等
   - 索引：created_at, resource_date, resource_type, url_path

### 阶段2: 后端实现 ✓

#### 4. 数据模型 (models/slow_log.py)
- SlowRequest - 慢请求模型
- SlowQuery - 慢查询模型
- SlowFrontendResource - 前端慢资源模型

#### 5. 存储服务 (services/slow_log_storage.py)
- 单例模式，线程安全
- 异步存储，不阻塞主流程
- 使用线程池处理后台写入
- 提供完整的查询和统计功能

#### 6. 服务层 (services/slow_log_service.py)
- 简化版服务层，避免循环导入
- 提供便捷的API接口

#### 7. 中间件集成

**performance_monitor.py 修改：**
- 检测到慢请求时自动保存到数据库
- 异步保存，不影响响应时间

**db_profiler.py 修改：**
- 检测到慢查询时自动保存到数据库
- 异步保存，不影响查询执行

**data_service.py 修改：**
- 修复了DBProfiler禁用问题
- 自动附加数据库分析器（如果配置启用）

#### 8. 路由 (routes/performance.py)
提供以下API端点：
- `POST /api/performance/slow-frontend` - 接收前端慢资源上报
- `GET /api/performance/slow-stats` - 获取慢日志统计
- `GET /api/performance/slow-requests` - 获取慢请求列表
- `GET /api/performance/slow-queries` - 获取慢查询列表
- `GET /api/performance/slow-frontend` - 获取前端慢资源列表
- `GET /api/performance/hotspot` - 获取热点分析

#### 9. 应用集成 (app.py)
- 注册性能监控蓝图

### 阶段3: 前端增强 ✓

#### 10. performance.js 修改
- 添加上报慢资源功能（>1000ms的XHR/Fetch请求）
- 添加 `reportSlowFrontend()` 方法
- 添加 `loadHistoryStats()` 方法加载历史统计
- 前端资源监控自动上报

#### 11. performance.html 修改
- 添加今日慢日志统计卡片
- 显示慢请求、慢查询、慢前端资源数量
- 显示平均耗时

#### 12. performance.css 修改
- 添加历史统计卡片样式
- 添加资源类型徽章样式

### 阶段4: 测试验证 ✓

所有测试通过：
- ✓ 模型导入测试
- ✓ 存储服务导入测试
- ✓ 服务层导入测试
- ✓ 路由导入测试
- ✓ 中间件导入测试
- ✓ 数据库连接测试
- ✓ 数据表存在测试
- ✓ 慢请求保存测试
- ✓ 慢查询保存测试
- ✓ 前端慢资源保存测试
- ✓ 统计查询测试
- ✓ 热点分析测试

## 关键特性

1. **非侵入式设计**
   - 不影响现有业务代码
   - 存储失败不阻塞主流程

2. **异步存储**
   - 使用线程池处理后台写入
   - 低延迟，高性能

3. **完整的数据模型**
   - 3个数据表，覆盖所有监控场景
   - 合理的索引设计，支持高效查询

4. **丰富的查询接口**
   - 统计信息查询
   - 列表查询（支持分页）
   - 热点分析（按路径/SQL哈希分组）

5. **前端集成**
   - 自动监控XHR/Fetch请求
   - 慢资源自动上报
   - 历史统计数据展示

## 配置说明

在 `configs/settings.yaml` 中配置：

```yaml
performance_monitor:
  enabled: true          # 启用API性能监控
  slow_threshold_ms: 500 # 慢请求阈值
  
db_profiler:
  enabled: true          # 启用数据库分析器
  slow_threshold_ms: 100 # 慢查询阈值
```

## 文件清单

### 新建文件
1. `src/gs2026/dashboard2/sql/create_slow_log_tables.sql` - 数据库表创建SQL
2. `src/gs2026/dashboard2/models/slow_log.py` - 数据模型
3. `src/gs2026/dashboard2/services/slow_log_storage.py` - 存储服务
4. `src/gs2026/dashboard2/services/slow_log_service.py` - 服务层
5. `src/gs2026/dashboard2/routes/performance.py` - 性能监控路由

### 修改文件
1. `src/gs2026/dashboard2/middleware/performance_monitor.py` - 集成慢请求存储
2. `src/gs2026/dashboard2/middleware/db_profiler.py` - 集成慢查询存储
3. `src/gs2026/dashboard/services/data_service.py` - 修复DBProfiler禁用问题
4. `src/gs2026/dashboard2/app.py` - 注册性能监控蓝图
5. `src/gs2026/dashboard2/static/js/performance.js` - 添加上报逻辑
6. `src/gs2026/dashboard2/templates/performance.html` - 增加历史统计展示
7. `src/gs2026/dashboard2/static/css/performance.css` - 添加样式

## 后续建议

1. **数据清理**: 建议定期清理过期数据（如保留30天）
2. **性能优化**: 如果数据量大，可以考虑按日期分区
3. **告警功能**: 可以基于慢日志数据添加告警机制
4. **可视化**: 可以添加趋势图展示慢请求变化
