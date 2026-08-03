# 股债交集回溯系统 - 过渡期方案 v2（精简版）

## 核心原则

1. **双轨并行**：新旧系统同时可用，用户自主选择
2. **无缝切换**：配置化切换，无需重启服务
3. **快速验证**：核心功能验证通过即可切换
4. **最短工期**：总工期压缩至 **5天**

---

## 过渡期架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         配置层                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  USE_BACKEND_FILTER = true/false  (环境变量/配置文件)    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│      旧系统（前端过滤）      │    │      新系统（后端过滤）      │
│  ┌─────────────────────┐   │    │  ┌─────────────────────┐   │
│  │ 前端JS过滤逻辑      │   │    │  │ 后端UnifiedPipeline │   │
│  │ (monitor.html)      │   │    │  │ (common/pipeline/)  │   │
│  └─────────────────────┘   │    │  └─────────────────────┘   │
│                              │    │                              │
│  优点：                       │    │  优点：                       │
│  - 无需网络请求               │    │  - 逻辑统一维护               │
│  - 响应速度快                 │    │  - 回溯系统可复用             │
│  - 已验证稳定                 │    │  - 易于扩展                   │
└─────────────────────────────┘    └─────────────────────────────┘
```

---

## 三阶段过渡期（总工期5天）

### 阶段1：开发期（3天）

**目标**：完成后端UnifiedPipeline开发，新旧系统并存

#### Day 1：基础框架
- [ ] 创建 `src/gs2026/common/pipeline/` 目录结构
- [ ] 实现 `FilterConfig` 配置类
- [ ] 实现 `Filter` 基类
- [ ] 实现 `Pipeline` 执行引擎

#### Day 2：过滤器实现
- [ ] 实现所有谓词型过滤器（IndustryFilter, BondExistsFilter, GreenListFilter）
- [ ] 实现所有排名型过滤器（TopNSectorsFilter, TopNWindowFilter, TopNCountFilter, TopNAmountFilter）
- [ ] 单元测试：每个过滤器独立测试

#### Day 3：API与集成
- [ ] 实现 `/api/filter/stock` API
- [ ] 实现 `/api/filter/bond` API
- [ ] 实现配置切换机制（USE_BACKEND_FILTER）
- [ ] 前端添加切换开关（默认关闭）
- [ ] 内部测试：前后端结果对比

**验收标准**：
- 所有过滤器单元测试通过
- API响应时间 < 300ms
- 前后端结果一致性 > 99%

**产出物**：
- `common/pipeline/` 完整代码
- `routes/filter_api.py` API实现
- `monitor.html` 切换开关

---

### 阶段2：验证期（1天）

**目标**：生产环境并行验证，确保一致性

#### 验证内容

| 验证项 | 方法 | 通过标准 |
|--------|------|----------|
| 功能一致性 | 对比模式：同时调用前后端，对比结果 | 差异率 = 0% |
| 性能对比 | 监控API响应时间 vs 前端执行时间 | API < 前端 + 100ms |
| 稳定性 | 24小时持续运行 | 错误率 < 0.1% |
| 用户体验 | 开关切换测试 | 无感知切换 |

#### 对比模式实现

```javascript
// monitor.html 添加对比模式（仅验证期启用）
const COMPARE_MODE = true;  // 验证期开启，生产期关闭

async function runPipeline(pipeline, data) {
    if (COMPARE_MODE) {
        // 同时调用新旧系统
        const frontendResult = originalRunPipeline(pipeline, data);
        const backendResult = await callBackendFilter(pipeline, data);
        
        // 对比并记录差异
        const diff = compareResults(frontendResult, backendResult);
        if (diff.length > 0) {
            logDifference(pipeline, data, diff);
        }
        
        // 返回旧系统结果（保证用户体验）
        return frontendResult;
    }
    
    // 生产模式：根据配置选择
    if (USE_BACKEND_FILTER) {
        return await callBackendFilter(pipeline, data);
    } else {
        return originalRunPipeline(pipeline, data);
    }
}
```

#### 差异处理流程

```
发现差异
    ↓
记录差异（时间、配置、输入、输出）
    ↓
分析根因（数据问题/逻辑问题/边界问题）
    ↓
修复后端代码
    ↓
重新验证
    ↓
差异率 = 0% → 通过
```

**验收标准**：
- 前后端结果完全一致
- 无阻塞性差异
- 性能达标

**产出物**：
- 验证报告
- 差异修复记录

---

### 阶段3：切换期（1天）

**目标**：切换至新系统，保留回滚能力

#### 切换步骤

**Step 1：配置切换（5分钟）**
```bash
# 修改配置文件
echo "USE_BACKEND_FILTER=true" > /etc/gs2026/config.env

# 或热更新（不重启）
curl -X POST http://localhost:5000/api/admin/config \
  -H "Content-Type: application/json" \
  -d '{"USE_BACKEND_FILTER": true}'
```

**Step 2：监控验证（30分钟）**
- 监控错误率
- 监控响应时间
- 监控用户反馈

**Step 3：确认切换成功**
- 错误率 < 0.1%
- 响应时间 < 500ms
- 无用户投诉

**切换回滚（如需要）**：
```bash
# 5分钟内回滚
echo "USE_BACKEND_FILTER=false" > /etc/gs2026/config.env
systemctl restart gs2026

# 或热回滚
curl -X POST http://localhost:5000/api/admin/config \
  -d '{"USE_BACKEND_FILTER": false}'
```

**验收标准**：
- 新系统成为默认
- 回滚机制验证通过
- 监控指标正常

---

## 切换方式详解

### 方式1：配置文件切换（推荐）

**配置文件**：`/etc/gs2026/config.env`

```bash
# 使用前端过滤（旧系统）
USE_BACKEND_FILTER=false

# 使用后端过滤（新系统）
USE_BACKEND_FILTER=true
```

**切换命令**：
```bash
# 切换到新系统
sed -i 's/USE_BACKEND_FILTER=false/USE_BACKEND_FILTER=true/' /etc/gs2026/config.env
systemctl restart gs2026

# 切换到旧系统
sed -i 's/USE_BACKEND_FILTER=true/USE_BACKEND_FILTER=false/' /etc/gs2026/config.env
systemctl restart gs2026
```

### 方式2：热更新切换（无需重启）

**API接口**：`POST /api/admin/config`

```bash
# 切换到新系统
curl -X POST http://localhost:5000/api/admin/config \
  -H "Content-Type: application/json" \
  -d '{"USE_BACKEND_FILTER": true}'

# 切换到旧系统
curl -X POST http://localhost:5000/api/admin/config \
  -d '{"USE_BACKEND_FILTER": false}'
```

**适用场景**：
- 紧急回滚（无需重启服务）
- A/B测试
- 灰度发布

### 方式3：前端开关切换（用户级）

**前端开关**（验证期可用）：
```html
<div class="filter-mode-toggle">
    <label>
        <input type="checkbox" id="useBackendFilter" 
               onchange="toggleFilterMode(this.checked)">
        使用后端过滤（实验性）
    </label>
</div>
```

**适用场景**：
- 验证期用户试用
- 特定用户测试
- 问题排查

---

## 后续清理方式

### 清理时机

**条件**：新系统稳定运行 **7天** 无问题

**指标**：
- 错误率 < 0.1%
- 无用户投诉
- 性能稳定

### 清理内容

| 清理项 | 操作 | 风险 |
|--------|------|------|
| 前端JS过滤逻辑 | 删除 `runPipeline` 旧实现 | 低（已验证新系统） |
| 对比模式代码 | 删除 `COMPARE_MODE` 相关代码 | 低 |
| 前端切换开关 | 删除用户级开关 | 低 |
| 旧过滤器配置 | 删除 `STOCK_PIPELINE` 旧定义 | 中（需确认无引用） |

### 清理步骤

**Step 1：代码审查（30分钟）**
```bash
# 查找旧代码引用
grep -r "originalRunPipeline" src/
grep -r "COMPARE_MODE" src/
grep -r "useBackendFilter" src/
```

**Step 2：删除旧代码（1小时）**
- 删除 `monitor.html` 中的旧 `runPipeline` 实现
- 删除对比模式代码
- 删除用户级开关
- 保留配置切换机制（管理员用）

**Step 3：验证（30分钟）**
- 功能测试
- 性能测试
- 确认无回归

**Step 4：提交（10分钟）**
```bash
git add -A
git commit -m "refactor: 移除前端过滤逻辑，统一使用后端Pipeline

- 删除旧runPipeline实现
- 删除对比模式代码
- 删除用户级开关
- 保留管理员配置切换

BREAKING CHANGE: 前端不再执行过滤，全部调用后端API"
```

### 清理后架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         配置层                                   │
│  USE_BACKEND_FILTER = true  (固定为true，保留配置项用于紧急回滚)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      新系统（后端过滤）                          │
│  ┌─────────────────────┐                                       │
│  │ UnifiedPipeline     │                                       │
│  │ (common/pipeline/)  │                                       │
│  └─────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 工期明细（5天）

| 阶段 | 天数 | 任务 | 产出 |
|------|------|------|------|
| 阶段1 | Day 1 | 基础框架 | FilterConfig, Filter基类, Pipeline引擎 |
| 阶段1 | Day 2 | 过滤器实现 | 所有谓词型+排名型过滤器 |
| 阶段1 | Day 3 | API与集成 | filter_api.py, 切换开关, 单元测试 |
| 阶段2 | Day 4 | 验证期 | 对比模式, 差异修复, 验证报告 |
| 阶段3 | Day 5 | 切换期 | 配置切换, 监控验证, 回滚测试 |
| **总计** | **5天** | | |

---

## 风险控制

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 后端性能不达标 | 中 | 高 | 阶段1性能测试，>500ms则优化，无法优化则延长验证期 |
| 结果不一致 | 中 | 高 | 阶段2对比模式，发现即修复，差异率>1%则延长验证期 |
| 切换后问题 | 低 | 高 | 热回滚机制，5分钟内恢复 |
| 清理后回归 | 低 | 中 | 清理前完整测试，保留回滚commit |

---

## 验收标准

### 阶段1验收
- [ ] 所有过滤器单元测试通过
- [ ] API响应时间 < 300ms
- [ ] 代码审查通过

### 阶段2验收
- [ ] 前后端结果差异率 = 0%
- [ ] 24小时稳定性测试通过
- [ ] 验证报告审批通过

### 阶段3验收
- [ ] 新系统成为默认
- [ ] 回滚机制验证通过
- [ ] 监控指标正常

---

## 文档完善计划

审核通过后，将以下内容完善到主设计文档：

1. **第16章：过渡期方案**
   - 三阶段过渡期
   - 切换方式详解
   - 后续清理方式

2. **第17章：实施计划（v3.0）**
   - 5天工期明细
   - 日任务分解

3. **附录更新**
   - 切换命令速查
   - 回滚命令速查
   - 清理检查清单

---

**文档状态**: 待审核  
**编制时间**: 2026-08-03 22:25  
**版本**: v2.0
