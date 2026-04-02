# 调度中心任务类型完整设计方案

> 版本: v1.0  
> 日期: 2026-04-01  
> 状态: 待确认

---

## 一、任务类型总览

| 类型 | 标识 | 执行方式 | 适用场景 |
|-----|------|---------|---------|
| **函数调用** | `function` | 直接调用Python函数 | 轻量级任务（缓存更新、数据清理） |
| **脚本执行** | `script` | 启动独立Python进程 | 耗时任务（数据采集、分析） |
| **任务调度** | `scheduler` | 调用Dashboard2现有调度器 | 复用采集/分析模块 |

---

## 二、统一参数传递方案

### 2.1 参数定义规范

```python
PARAM_SCHEMA = {
    "param_name": {
        "type": "string|int|float|bool|date|select|list",
        "required": True|False,
        "default": value,
        "description": "参数说明",
        # 可选
        "options": [...],        # select类型选项
        "format": "%Y%m%d",      # date类型格式
        "min": 0, "max": 100,    # int/float范围
        "item_type": "string"    # list元素类型
    }
}
```

### 2.2 参数类型映射

| 类型 | 前端组件 | 后端接收 | 环境变量格式 |
|-----|---------|---------|-------------|
| `string` | 文本输入 | `str` | 原值 |
| `int` | 数字输入 | `int` | `str(value)` |
| `float` | 数字输入 | `float` | `str(value)` |
| `bool` | 开关 | `bool` | `"true"/"false"` |
| `date` | 日期选择器 | `str(YYYYMMDD)` | `YYYYMMDD` |
| `select` | 下拉选择 | `str` | 原值 |
| `list` | 多选/标签 | `List[str]` | 逗号分隔 |

---

## 三、三种任务类型详细设计

### 3.1 Function 类型（函数调用）

#### 配置示例

```json
{
  "job_id": "red_list_cache_daily",
  "job_name": "红名单每日缓存更新",
  "job_type": "function",
  "job_config": {
    "module": "gs2026.dashboard2.routes.red_list_cache",
    "function": "update_red_list_cache",
    "params": {
      "date_str": {
        "type": "date",
        "required": false,
        "default": null,
        "format": "%Y%m%d",
        "description": "日期YYYYMMDD，null表示今天"
      }
    }
  },
  "trigger_type": "cron",
  "trigger_config": {
    "hour": "9",
    "minute": "20",
    "day_of_week": "mon-fri"
  }
}
```

#### 执行流程

```
调度器接收参数 {date_str: "20260331"}
        ↓
动态导入模块: gs2026.dashboard2.routes.red_list_cache
        ↓
获取函数: update_red_list_cache
        ↓
参数转换: "20260331" → date_str="20260331"
        ↓
直接调用: update_red_list_cache(date_str="20260331")
        ↓
获取返回值: {'success': True, 'count': 128}
        ↓
记录执行结果
```

#### 执行器代码

```python
def _execute_function(self, config: dict, params: dict, execution_id: str) -> str:
    """执行函数调用"""
    module_path = config['module']
    function_name = config['function']
    
    # 动态导入
    module = importlib.import_module(module_path)
    func = getattr(module, function_name)
    
    # 直接调用（同步执行）
    result = func(**params)
    
    return str(result)
```

---

### 3.2 Script 类型（脚本执行）

#### 配置示例

```json
{
  "job_id": "combine_ztb_area_analysis",
  "job_name": "涨停板与区域分析",
  "job_type": "script",
  "job_config": {
    "script_path": "gs2026.analysis.worker.message.deepseek.combine_ztb_area",
    "python_exe": "python",
    "work_dir": "F:/pyworkspace2026/gs2026",
    "params": {
      "date": {
        "type": "date",
        "required": false,
        "default": null,
        "format": "%Y%m%d",
        "description": "分析日期，YYYYMMDD，null表示今天"
      }
    }
  },
  "trigger_type": "cron",
  "trigger_config": {
    "hour": "17",
    "minute": "0"
  }
}
```

#### 执行流程

```
调度器接收参数 {date: "20260331"}
        ↓
参数转换: "2026-03-31" → "20260331"
        ↓
设置环境变量: ANALYSIS_DATE=20260331
        ↓
构建命令: python -m gs2026.analysis.worker.message.deepseek.combine_ztb_area
        ↓
启动子进程: subprocess.Popen(env={**os.environ, 'ANALYSIS_DATE': '20260331'})
        ↓
脚本读取: os.environ.get('ANALYSIS_DATE') → "20260331"
        ↓
解析执行: base_date = datetime(2026, 3, 31)
        ↓
独立运行（异步）
```

#### 脚本读取代码

```python
# combine_ztb_area.py
import os
from datetime import datetime

# 从环境变量读取
date_str = os.environ.get('ANALYSIS_DATE')
if date_str:
    base_date = datetime.strptime(date_str, '%Y%m%d')
else:
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# 其他参数保持硬编码
ztb_hour, ztb_minute = 18, 0
area_hour, area_minute = 0, 0
```

#### 执行器代码

```python
def _execute_script(self, config: dict, params: dict, execution_id: str) -> str:
    """执行Python脚本（独立进程）"""
    script_path = config['script_path']
    python_exe = config.get('python_exe', 'python')
    
    # 构建命令
    cmd = [python_exe, '-m', script_path]
    
    # 设置环境变量
    env = os.environ.copy()
    for key, value in params.items():
        if value is not None:
            env[f"ANALYSIS_{key.upper()}"] = str(value)
    
    # 启动子进程
    process = subprocess.Popen(
        cmd,
        cwd=config.get('work_dir'),
        env=env,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    )
    
    return f"Process started: PID {process.pid}"
```

---

### 3.3 Scheduler 类型（任务调度）

#### 配置示例

```json
{
  "job_id": "market_monitor_auto",
  "job_name": "自动启动市场监控",
  "job_type": "scheduler",
  "job_config": {
    "target": "collection",
    "task_id": "market_monitor",
    "action": "start",
    "params": {
      "date": {
        "type": "date",
        "required": false,
        "default": null,
        "format": "%Y%m%d",
        "description": "监控日期"
      }
    }
  },
  "trigger_type": "cron",
  "trigger_config": {
    "hour": "9",
    "minute": "25"
  }
}
```

#### 执行流程

```
调度器接收参数 {date: "20260331"}
        ↓
调用 Dashboard2 ProcessManager
        ↓
process_manager.start_task(
    module='collection',
    task_id='market_monitor',
    params={'date': '20260331'}
)
        ↓
创建包装脚本（带参数）
        ↓
启动子进程执行实际任务
        ↓
返回进程PID
```

#### 执行器代码

```python
def _execute_scheduler(self, config: dict, params: dict, execution_id: str) -> str:
    """调用Dashboard2调度器"""
    from gs2026.dashboard2.services.process_manager import process_manager
    
    target = config['target']      # 'collection' 或 'analysis'
    task_id = config['task_id']    # 任务ID
    action = config['action']      # 'start' 或 'stop'
    
    if action == 'start':
        result = process_manager.start_task(
            module=target,
            task_id=task_id,
            params=params
        )
    else:
        result = process_manager.stop_task(
            module=target,
            task_id=task_id
        )
    
    return str(result)
```

---

## 四、API接口设计

### 4.1 获取任务列表

```http
GET /api/scheduler/jobs
```

**响应**

```json
{
  "code": 200,
  "data": {
    "jobs": [
      {
        "job_id": "red_list_cache_daily",
        "job_name": "红名单每日缓存更新",
        "job_type": "function",
        "status": "enabled",
        "next_run_time": "2026-04-01T09:20:00+08:00"
      }
    ]
  }
}
```

### 4.2 获取任务详情（含参数配置）

```http
GET /api/scheduler/jobs/{job_id}
```

**响应**

```json
{
  "code": 200,
  "data": {
    "job_id": "combine_ztb_area_analysis",
    "job_name": "涨停板与区域分析",
    "job_type": "script",
    "job_config": {
      "script_path": "gs2026.analysis.worker.message.deepseek.combine_ztb_area",
      "params": {
        "date": {
          "type": "date",
          "required": false,
          "default": null,
          "description": "分析日期，YYYYMMDD，null表示今天"
        }
      }
    },
    "trigger_type": "cron",
    "trigger_config": {
      "hour": "17",
      "minute": "0"
    }
  }
}
```

### 4.3 手动执行任务（带参数）

```http
POST /api/scheduler/jobs/{job_id}/execute
Content-Type: application/json

{
  "params": {
    "date": "20260331"
  }
}
```

### 4.4 响应

```json
{
  "code": 200,
  "data": {
    "execution_id": "combine_ztb_area_analysis_20260401_003000_abc123",
    "status": "running",
    "start_time": "2026-04-01T00:30:00+08:00"
  }
}
```

---

## 五、前端参数表单动态生成

```javascript
// 根据任务配置生成表单
function generateParamForm(jobConfig) {
    const params = jobConfig.params || {};
    const form = document.createElement('div');
    
    for (const [key, config] of Object.entries(params)) {
        const field = createField(key, config);
        form.appendChild(field);
    }
    
    return form;
}

function createField(name, config) {
    const wrapper = document.createElement('div');
    wrapper.className = 'param-field';
    
    // 标签
    const label = document.createElement('label');
    label.textContent = config.description || name;
    if (config.required) {
        label.innerHTML += ' <span class="required">*</span>';
    }
    wrapper.appendChild(label);
    
    // 输入组件
    let input;
    switch (config.type) {
        case 'date':
            input = document.createElement('input');
            input.type = 'date';
            input.name = name;
            if (config.default) {
                // YYYYMMDD -> YYYY-MM-DD
                input.value = `${config.default.slice(0,4)}-${config.default.slice(4,6)}-${config.default.slice(6,8)}`;
            }
            break;
            
        case 'int':
        case 'float':
            input = document.createElement('input');
            input.type = 'number';
            input.name = name;
            if (config.min !== undefined) input.min = config.min;
            if (config.max !== undefined) input.max = config.max;
            input.value = config.default;
            break;
            
        case 'bool':
            input = document.createElement('input');
            input.type = 'checkbox';
            input.name = name;
            input.checked = config.default;
            break;
            
        case 'select':
            input = document.createElement('select');
            input.name = name;
            config.options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                if (opt.value === config.default) {
                    option.selected = true;
                }
                input.appendChild(option);
            });
            break;
            
        default: // string
            input = document.createElement('input');
            input.type = 'text';
            input.name = name;
            input.value = config.default || '';
    }
    
    wrapper.appendChild(input);
    return wrapper;
}

// 收集表单参数
function collectParams(form) {
    const params = {};
    const inputs = form.querySelectorAll('input, select');
    
    inputs.forEach(input => {
        const name = input.name;
        let value;
        
        switch (input.type) {
            case 'checkbox':
                value = input.checked;
                break;
            case 'date':
                // YYYY-MM-DD -> YYYYMMDD
                value = input.value.replace(/-/g, '');
                break;
            case 'number':
                value = input.valueAsNumber;
                break;
            default:
                value = input.value;
        }
        
        if (value !== '' && value !== null) {
            params[name] = value;
        }
    });
    
    return params;
}
```

---

## 六、数据库表结构

```sql
-- 任务表
CREATE TABLE scheduler_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(100) UNIQUE NOT NULL COMMENT '任务标识',
    job_name VARCHAR(200) NOT NULL COMMENT '任务名称',
    job_type ENUM('function', 'script', 'scheduler') NOT NULL COMMENT '任务类型',
    job_config JSON NOT NULL COMMENT '任务配置（含参数定义）',
    trigger_type ENUM('cron', 'interval', 'date', 'once') NOT NULL,
    trigger_config JSON NOT NULL COMMENT '触发器配置',
    status ENUM('enabled', 'disabled', 'paused') DEFAULT 'enabled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 执行记录表
CREATE TABLE scheduler_executions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    execution_id VARCHAR(100) UNIQUE NOT NULL,
    job_id VARCHAR(100) NOT NULL,
    trigger_type ENUM('cron', 'manual', 'chain') NOT NULL,
    params JSON COMMENT '执行参数',
    status ENUM('pending', 'running', 'success', 'failed', 'timeout') DEFAULT 'pending',
    start_time TIMESTAMP NULL,
    end_time TIMESTAMP NULL,
    result_message TEXT,
    error_stack TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 七、实施计划

### 阶段1: 后端基础（2天）
1. 修改 `scheduler_jobs` 表结构
2. 实现三种任务类型的执行器
3. 添加参数验证和转换逻辑
4. 更新API接口

### 阶段2: 脚本改造（1天）
1. 修改 `combine_ztb_area.py` 支持环境变量
2. 测试脚本执行

### 阶段3: 前端开发（2天）
1. 实现参数表单动态生成
2. 集成到调度中心页面
3. 测试参数传递

### 阶段4: 集成测试（1天）
1. 三种任务类型端到端测试
2. 参数传递验证
3. 异常情况处理

---

## 八、风险评估

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 参数类型转换错误 | 高 | 严格的参数验证和单元测试 |
| 环境变量传递失败 | 中 | 添加日志记录，验证环境变量设置 |
| 前端表单生成异常 | 中 | 默认值处理，空值校验 |
| 向后兼容性 | 低 | 保留原有API，新增参数可选 |

---

**待确认事项：**
1. 三种任务类型是否满足所有场景？
2. 参数类型是否需要增加其他类型（如文件上传）？
3. 环境变量命名前缀 `ANALYSIS_` 是否合适？
4. 实施计划时间安排是否合理？
