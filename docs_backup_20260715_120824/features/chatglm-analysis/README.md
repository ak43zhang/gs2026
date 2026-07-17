# 智谱清言版事件驱动分析 - 使用说明

## 文件结构

```
gs2026/
└── analysis/
    └── worker/
        └── message/
            ├── deepseek/                    # DeepSeek版本（已有）
            │   ├── deepseek_analysis_event_driven.py
            │   └── result_processor.py
            │
            └── zhipuqingyan/                # 智谱清言版本（新增）
                ├── __init__.py
                ├── zhipuqingyan_analysis_event_driven.py
                ├── result_processor.py
                └── test_module.py
```

## 数据库表（与DeepSeek版本共用）

智谱清言版本**复用DeepSeek版本的数据库表**，无需新建表：

| 表名 | 说明 |
|------|------|
| `analysis_area2026` | 分析结果主表（JSON原始数据） |
| `analysis_domain_detail_2026` | 分析明细表（拆分后的结构化数据） |

### 表结构说明

**analysis_area2026**（与DeepSeek共用）
```sql
- id: 主键
- news_date: 分析日期
- main_area: 主领域
- child_area: 子领域
- json_data: AI分析结果JSON
- create_time: 创建时间
```

**analysis_domain_detail_2026**（与DeepSeek共用）
```sql
- id: 主键
- content_hash: 内容哈希（唯一）
- main_area: 主领域
- child_area: 子领域
- event_time: 事件时间
- event_source: 事件来源
- key_event: 关键事件
- brief_desc: 简要描述
- importance_score: 重要程度评分
- business_impact_score: 业务影响评分
- composite_score: 综合评分
- news_size: 消息大小
- news_type: 利空利好
- sectors: 涉及板块（JSON）
- concepts: 涉及概念（JSON）
- stock_codes: 股票代码（JSON）
- reason_analysis: 原因分析
- deep_analysis: 深度分析（JSON）
- analysis_version: 版本（zhipuqingyan-1.0.0）
- create_time: 创建时间
```

## 使用方法

### 1. 作为模块导入

```python
from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven

# 分析指定日期列表
analysis_event_driven(['2026-05-20', '2026-05-21'])
```

### 2. 命令行运行

```bash
cd F:\pyworkspace2026\gs2026\src

# 使用默认日期列表
python -m gs2026.analysis.worker.message.zhipuqingyan.zhipuqingyan_analysis_event_driven

# 使用自定义日期列表
python -m gs2026.analysis.worker.message.zhipuqingyan.zhipuqingyan_analysis_event_driven --params '{"date_list": ["2026-05-20", "2026-05-21"]}'
```

### 3. 作为守护进程运行

```python
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven

# 启动守护进程
date_list = ['2026-05-20', '2026-05-21']
run_daemon_task(target=analysis_event_driven, args=(date_list,))
```

## 核心流程

```
1. 查询待分析记录 (news_area 表)
2. 获取板块/概念字典
3. 构造多维度评分 Prompt（与DeepSeek相同）
4. 启动 Firefox 浏览器
5. 访问 https://chatglm.cn/main/alltoolsdetail
6. 关闭产品推广弹窗
7. 点击"思考"按钮启用深度思考
8. 点击"联网"按钮启用联网搜索
9. 发送 Prompt 并等待回复
10. 解析 JSON 结果
11. 存储到 analysis_area2026 表
12. 拆分入库到 analysis_domain_detail_2026 表
```

## 与 DeepSeek 版本对比

| 特性 | DeepSeek | 智谱清言 |
|------|----------|---------|
| 数据库表 | `analysis_area2026` | **共用相同表** |
| 明细表 | `analysis_domain_detail_2026` | **共用相同表** |
| 版本标识 | `1.0.0` | `zhipuqingyan-1.0.0` |
| 登录 | 需要 | **无需** |
| 弹窗处理 | 无 | **需要** |
| 深度思考 | DeepThink 按钮 | "思考" 按钮 |
| 联网搜索 | Search 按钮 | "联网" 按钮 |
| Prompt | 多维度评分 | **完全复用** |
| 结果解析 | 领域分析 | **完全复用** |
| Redis Key | `domain:xxx` | **相同格式** |

## 数据区分方式

通过 `analysis_version` 字段区分数据来源：

```sql
-- 查询DeepSeek分析结果
SELECT * FROM analysis_domain_detail_2026 
WHERE analysis_version LIKE '1.0.0' OR analysis_version LIKE 'deepseek%';

-- 查询智谱清言分析结果
SELECT * FROM analysis_domain_detail_2026 
WHERE analysis_version LIKE 'zhipuqingyan%';

-- 查询所有分析结果
SELECT * FROM analysis_domain_detail_2026;
```

## 测试

运行测试脚本：

```bash
cd F:\pyworkspace2026\gs2026\src
python gs2026\analysis\worker\message\zhipuqingyan\test_module.py
```

## 注意事项

1. **无需建表**：直接使用DeepSeek版本的表
2. **无需登录**：智谱清言可以直接使用
3. **弹窗处理**：会自动关闭产品推广弹窗
4. **功能启用**：会自动点击"思考"和"联网"按钮
5. **重试机制**：失败会自动重试30次
6. **分布式锁**：使用Redis防止并发重复处理
7. **数据共存**：与DeepSeek数据存储在同一表中，通过version字段区分

## Cookies 持久化

### 自动保存和复用
系统会自动保存和复用 cookies，避免重复验证：

```
cookies/
└── chatglm_cookies.json    # 自动保存的 cookies
```

### 方式1: 使用 Microsoft Edge（推荐）

**步骤1: 获取 Cookies**
```bash
cd F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan

# 运行 Edge 获取工具
python get_cookies_from_edge.py
```

流程：
1. Edge 自动打开智谱清言
2. **手动完成验证**（Access Verification）
3. 返回命令行，按 Enter 保存
4. Cookies 保存到 `cookies/chatglm_cookies.json`

**步骤2: 验证 Cookies**
```bash
python verify_cookies.py
```

**步骤3: 配置使用 Edge**
在 `openclaw.json` 中添加：
```json
{
  "common": {
    "browser_type": "edge",
    "edge_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  }
}
```

**步骤4: 运行程序**
```python
from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven
analysis_event_driven(['2026-05-20'])
```

### 方式2: 使用 Firefox
```bash
# 获取 cookies
python get_cookies_manual.py

# 配置使用 Firefox（默认）
# browser_type 默认为 firefox，无需修改配置
```

### 方式3: 直接编辑 Cookies 文件
```bash
# 创建示例文件
python cookies_helper.py sample

# 编辑文件
notepad cookies\chatglm_cookies.json
```

### 查看当前 Cookies
```bash
python cookies_helper.py show
```

### 手动清除 Cookies
```bash
# 删除 cookies 文件
del cookies\chatglm_cookies.json
```

### 注意事项
- Cookies 有效期通常为几天到几周
- Edge 获取的 cookies 与 Firefox 格式相同，可以通用
- 建议定期备份 cookies 文件

## 故障排查

### 问题1：浏览器启动失败
- 检查 Firefox 路径配置 `common.browser_path`
- 确保 Firefox 已安装

### 问题2：Access Verification 验证页面
- 系统会自动检测并尝试刷新
- 首次运行可能需要人工完成验证
- 验证完成后 cookies 会自动保存
- 后续运行将自动复用 cookies

### 问题3：页面元素找不到
- 智谱清言页面结构可能变化
- 检查 `ChatGLMBrowser` 类中的选择器

### 问题4：JSON解析失败
- 检查智谱清言返回格式
- 查看日志中的原始返回内容

### 问题5：数据未写入
- 检查表名是否正确（`analysis_area2026`, `analysis_domain_detail_2026`）
- 检查数据库连接配置

## 联系

如有问题，请查看日志或联系开发团队。
