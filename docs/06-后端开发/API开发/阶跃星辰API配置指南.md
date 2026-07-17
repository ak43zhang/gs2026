# 阶跃星辰 API 配置指南

> 文档位置：`docs/06-AI分析/阶跃星辰API配置指南.md`  
> 适用版本：GS2026 v1.0+  
> 最后更新：2026-05-12

---

## 一、获取阶跃星辰 API Key

### 1.1 注册阶跃星辰账号

1. 访问阶跃星辰开放平台：[https://platform.stepfun.com](https://platform.stepfun.com)
2. 点击右上角「注册」按钮
3. 使用手机号或邮箱完成注册
4. 完成实名认证（企业用户需提交企业资质）

### 1.2 创建 API Key

1. 登录后进入「控制台」→「API Keys」页面
2. 点击「创建 API Key」按钮
3. 填写 Key 名称（如：GS2026-Production）
4. 选择权限范围（建议：全部模型权限）
5. 复制生成的 API Key（格式：`sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）

**⚠️ 重要提示**：
- API Key 只会显示一次，请立即保存到安全位置
- 不要将 API Key 提交到 Git 仓库
- 建议创建多个 Key 用于轮询（提高并发能力）

### 1.3 查看模型与价格

在控制台「模型广场」页面可查看：
- `step-1-8k`：快速分析，8K上下文
- `step-1-32k`：标准分析，32K上下文（推荐）
- `step-1-128k`：深度分析，128K上下文

---

## 二、配置方式

### 方式一：settings.yaml 配置（推荐）

编辑项目根目录的 `settings.yaml` 文件：

```yaml
common:
  # 阶跃星辰 API 配置
  step_api_keys:
    - "sk-your-first-api-key-here"
    - "sk-your-second-api-key-here"  # 可选：多Key轮询
    - "sk-your-third-api-key-here"   # 可选：多Key轮询
  
  step_base_url: "https://api.stepfun.com/v1"
```

**多Key轮询优势**：
- 避免单Key触发速率限制
- 提高并发处理能力
- 某个Key失效时自动切换

### 方式二：环境变量配置

在系统环境变量或 `.env` 文件中设置：

```bash
# Windows PowerShell
$env:STEP_API_KEY="sk-your-api-key-here"

# Windows CMD
set STEP_API_KEY=sk-your-api-key-here

# Linux/Mac
export STEP_API_KEY="sk-your-api-key-here"
```

**注意**：环境变量方式仅支持单Key，如需多Key请使用方式一。

### 方式三：配置文件 + 环境变量混合

优先使用环境变量，未设置时回退到配置文件：

```yaml
common:
  step_api_keys:
    - "${STEP_API_KEY}"  # 从环境变量读取
```

---

## 三、验证配置

### 3.1 快速测试

```python
from gs2026.analysis.worker.message.stepfun import StepfunClient

client = StepfunClient()
result = client.analyze(
    prompt="请返回一个JSON：{'status': 'ok'}",
    force_json=True
)
print(result)
# 预期输出：{"status": "ok"}
```

### 3.2 事件驱动分析测试

```python
from gs2026.analysis.worker.message.stepfun import analysis_event_driven

# 测试单日分析
analysis_event_driven(['2026-05-12'])
```

---

## 四、故障排查

### 4.1 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `STEP_API_KEYS 未配置` | 配置文件缺失或环境变量未设置 | 检查 settings.yaml 或环境变量 |
| `401 Unauthorized` | API Key 无效或过期 | 在控制台重新生成 Key |
| `429 Too Many Requests` | 触发速率限制 | 增加多Key轮询或降低并发 |
| `Connection timeout` | 网络问题 | 检查网络连接，或增加 timeout 参数 |

### 4.2 查看日志

日志位置：`logs/stepfun_client.log`

```bash
# 实时查看
 tail -f logs/stepfun_client.log

# 搜索错误
 grep "ERROR" logs/stepfun_client.log
```

### 4.3 调试模式

在代码中启用详细日志：

```python
import logging
logging.getLogger("stepfun_client").setLevel(logging.DEBUG)
```

---

## 五、最佳实践

### 5.1 生产环境建议

1. **多Key配置**：至少配置 3 个 API Key
2. **监控用量**：定期查看控制台「用量统计」
3. **设置告警**：监控 API 错误率，超过阈值时告警
4. **备份配置**：将 settings.yaml 纳入版本控制（脱敏后）

### 5.2 成本控制

| 模型 | 适用场景 | 成本 |
|------|---------|------|
| `step-1-8k` | 快速测试、简单分析 | 低 |
| `step-1-32k` | 标准事件驱动分析（推荐） | 中 |
| `step-1-128k` | 复杂深度分析 | 高 |

### 5.3 与 DeepSeek 对比

| 维度 | DeepSeek | 阶跃星辰 |
|------|----------|---------|
| 稳定性 | 低（易封号） | 高（API服务） |
| 延迟 | 30-120s | 5-30s |
| 并发 | 单账号串行 | 多Key并行 |
| 成本 | 免费但不稳定 | 按token计费 |
| 配置复杂度 | 高（需账号池） | 低（仅需API Key） |

---

## 六、相关文档

- [阶跃星辰开放平台](https://platform.stepfun.com)
- [API 文档](https://platform.stepfun.com/docs)
- [价格说明](https://platform.stepfun.com/pricing)
- 项目内：`docs/06-AI分析/事件驱动分析-阶跃版本设计.md`

---

## 七、更新记录

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-05-12 | v1.0 | 初始版本，阶跃星辰 API 配置指南 |

---

**技术支持**：如有问题请联系阶跃星辰客服或项目维护者。
