# 采集任务执行记录系统设计方案

> 版本: v1.0  
> 创建时间: 2026-03-30  
> 用途: 采集任务执行留痕与问题排查

---

## 1. 设计目标

### 1.1 核心需求
- **执行留痕**: 所有采集任务执行后有一条完整记录
- **问题排查**: 可追溯执行流程，定位失败原因
- **性能分析**: 统计执行时长、数据库查询次数、API调用次数

### 1.2 关键字段
| 字段类别 | 说明 |
|---------|------|
| 任务标识 | process_id, service_id, module, task_name |
| 执行参数 | JSON格式存储 |
| 时间记录 | 开始时间、结束时间、执行时长 |
| 执行结果 | 状态、消息、错误类型、错误堆栈 |
| 流程回溯 | 执行步骤详细记录 |
| 性能指标 | 查询次数、API调用、处理行数 |

---

## 2. 数据库设计

### 2.1 主表: task_execution_log

```sql
CREATE TABLE task_execution_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    process_id VARCHAR(64) NOT NULL COMMENT '进程ID',
    service_id VARCHAR(64) NOT NULL COMMENT '服务ID',
    module VARCHAR(32) NOT NULL COMMENT '模块名(base/news/risk/monitor)',
    task_name VARCHAR(64) NOT NULL COMMENT '任务名称',
    
    -- 执行参数
    params JSON COMMENT '执行参数',
    
    -- 时间记录
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME DEFAULT NULL COMMENT '结束时间',
    duration_seconds INT DEFAULT 0 COMMENT '执行时长(秒)',
    
    -- 执行状态
    status ENUM('running', 'success', 'failed', 'stopped', 'timeout') 
        NOT NULL DEFAULT 'running',
    
    -- 执行结果
    result_message TEXT COMMENT '结果消息',
    error_type VARCHAR(64) COMMENT '错误类型',
    error_stack TEXT COMMENT '错误堆栈',
    records_count INT DEFAULT 0 COMMENT '处理记录数',
    
    -- 执行流程回溯（关键！）
    execution_trace JSON COMMENT '执行步骤记录',
    
    -- 性能指标
    db_query_count INT DEFAULT 0 COMMENT '数据库查询次数',
    api_call_count INT DEFAULT 0 COMMENT 'API调用次数',
    total_rows_processed INT DEFAULT 0 COMMENT '总行数',
    
    -- 进程信息
    pid INT COMMENT '进程PID',
    wrapper_path VARCHAR(512) COMMENT '包装脚本路径',
    python_version VARCHAR(32) COMMENT 'Python版本',
    
    -- 主机信息
    hostname VARCHAR(64) COMMENT '主机名',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_process_id (process_id),
    INDEX idx_service_id (service_id),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time),
    INDEX idx_error_type (error_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采集任务执行记录';
```

### 2.2 步骤详情表: task_execution_step

```sql
CREATE TABLE task_execution_step (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    execution_id BIGINT NOT NULL COMMENT '关联的执行记录ID',
    step_order INT NOT NULL COMMENT '步骤序号',
    step_name VARCHAR(128) NOT NULL COMMENT '步骤名称',
    step_type VARCHAR(32) COMMENT '步骤类型(query/api/process/file)',
    
    -- 时间
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    duration_ms INT COMMENT '耗时(毫秒)',
    
    -- 状态
    status ENUM('running', 'success', 'failed', 'skipped') DEFAULT 'running',
    
    -- 详情
    input_params JSON COMMENT '输入参数',
    output_result JSON COMMENT '输出结果',
    error_message TEXT COMMENT '错误信息',
    rows_affected INT DEFAULT 0 COMMENT '影响行数',
    
    -- 关联信息
    sql_query TEXT COMMENT 'SQL查询语句',
    api_endpoint VARCHAR(512) COMMENT 'API端点',
    file_path VARCHAR(512) COMMENT '文件路径',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_execution_id (execution_id),
    INDEX idx_step_order (execution_id, step_order),
    FOREIGN KEY (execution_id) REFERENCES task_execution_log(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行步骤详情';
```

---

## 3. Python 代码设计

### 3.1 数据模型

```python
# gs2026/models/task_execution.py

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, Dict, Any, List
import json


@dataclass
class TaskExecutionLog:
    """采集任务执行记录"""
    id: Optional[int] = None
    process_id: str = ""
    service_id: str = ""
    module: str = ""  # base/news/risk/monitor
    task_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: int = 0
    status: str = "running"  # running/success/failed/stopped/timeout
    result_message: str = ""
    error_type: Optional[str] = None
    error_stack: Optional[str] = None
    records_count: int = 0
    execution_trace: List[Dict] = field(default_factory=list)
    db_query_count: int = 0
    api_call_count: int = 0
    total_rows_processed: int = 0
    pid: Optional[int] = None
    wrapper_path: str = ""
    python_version: str = ""
    hostname: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # JSON字段序列化
        for field_name in ['params', 'execution_trace']:
            if data.get(field_name) and isinstance(data[field_name], (dict, list)):
                data[field_name] = json.dumps(data[field_name], ensure_ascii=False)
        return data
    
    @classmethod
    def from_db_row(cls, row: Dict) -> 'TaskExecutionLog':
        """从数据库行创建对象"""
        data = dict(row)
        # JSON字段反序列化
        for field_name in ['params', 'execution_trace']:
            if data.get(field_name) and isinstance(data[field_name], str):
                data[field_name] = json.loads(data[field_name])
        return cls(**data)


@dataclass
class TaskExecutionStep:
    """执行步骤详情"""
    id: Optional[int] = None
    execution_id: int = 0
    step_order: int = 0
    step_name: str = ""
    step_type: str = ""  # query/api/process/file
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: str = "running"
    input_params: Dict[str, Any] = field(default_factory=dict)
    output_result: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    rows_affected: int = 0
    sql_query: Optional[str] = None
    api_endpoint: Optional[str] = None
    file_path: Optional[str] = None
```

### 3.2 执行记录管理器

```python
# gs2026/utils/task_execution_logger.py

import json
import traceback
import socket
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from gs2026.models.task_execution import TaskExecutionLog, TaskExecutionStep
from gs2026.utils import mysql_util, log_util

logger = log_util.get_logger(__name__)


class ExecutionTrace:
    """执行流程追踪器"""
    
    def __init__(self, execution_id: int):
        self.execution_id = execution_id
        self.steps: List[Dict] = []
        self.current_step = 0
        self.mysql_tool = mysql_util.MysqlTool()
    
    def add_step(self, name: str, step_type: str = "process", 
                 input_params: Dict = None) -> int:
        """添加执行步骤"""
        self.current_step += 1
        step = {
            'step': self.current_step,
            'name': name,
            'type': step_type,
            'start_time': datetime.now().isoformat(),
            'status': 'running',
            'input': input_params or {}
        }
        self.steps.append(step)
        
        # 写入数据库
        try:
            sql = """
                INSERT INTO task_execution_step 
                (execution_id, step_order, step_name, step_type, start_time, status, input_params)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            self.mysql_tool.execute(sql, (
                self.execution_id,
                self.current_step,
                name,
                step_type,
                datetime.now(),
                'running',
                json.dumps(input_params or {}, ensure_ascii=False)
            ))
        except Exception as e:
            logger.error(f"[ExecutionTrace] Failed to add step: {e}")
        
        return self.current_step
    
    def end_step(self, step_order: int, status: str = 'success',
                 output: Dict = None, error: str = None,
                 rows_affected: int = 0):
        """结束执行步骤"""
        # 更新内存中的步骤
        for step in self.steps:
            if step['step'] == step_order:
                step['end_time'] = datetime.now().isoformat()
                step['status'] = status
                step['output'] = output or {}
                step['error'] = error
                break
        
        # 更新数据库
        try:
            start_time = datetime.fromisoformat(step['start_time'])
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            sql = """
                UPDATE task_execution_step 
                SET end_time = %s, status = %s, duration_ms = %s,
                    output_result = %s, error_message = %s, rows_affected = %s
                WHERE execution_id = %s AND step_order = %s
            """
            self.mysql_tool.execute(sql, (
                datetime.now(),
                status,
                duration_ms,
                json.dumps(output or {}, ensure_ascii=False),
                error,
                rows_affected,
                self.execution_id,
                step_order
            ))
        except Exception as e:
            logger.error(f"[ExecutionTrace] Failed to end step: {e}")
    
    @contextmanager
    def step_context(self, name: str, step_type: str = "process",
                     input_params: Dict = None):
        """步骤上下文管理器（自动记录开始和结束）"""
        step_order = self.add_step(name, step_type, input_params)
        try:
            yield step_order
            self.end_step(step_order, 'success')
        except Exception as e:
            self.end_step(step_order, 'failed', error=str(e))
            raise


class TaskExecutionLogger:
    """任务执行记录管理器（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.mysql_tool = mysql_util.MysqlTool()
        self._hostname = socket.gethostname()
        self._python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self._initialized = True
    
    def start_execution(self, **kwargs) -> tuple:
        """
        记录任务开始执行
        
        Returns:
            (execution_id, trace) - 执行记录ID和流程追踪器
        """
        try:
            log_entry = TaskExecutionLog(
                process_id=kwargs.get('process_id'),
                service_id=kwargs.get('service_id'),
                module=kwargs.get('module'),
                task_name=kwargs.get('task_name'),
                params=kwargs.get('params', {}),
                start_time=datetime.now(),
                status="running",
                pid=kwargs.get('pid'),
                wrapper_path=kwargs.get('wrapper_path'),
                python_version=self._python_version,
                hostname=self._hostname
            )
            
            sql = """
                INSERT INTO task_execution_log 
                (process_id, service_id, module, task_name, params, start_time, 
                 status, pid, wrapper_path, python_version, hostname, execution_trace)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.mysql_tool.execute(sql, (
                log_entry.process_id,
                log_entry.service_id,
                log_entry.module,
                log_entry.task_name,
                json.dumps(log_entry.params, ensure_ascii=False),
                log_entry.start_time,
                log_entry.status,
                log_entry.pid,
                log_entry.wrapper_path,
                log_entry.python_version,
                log_entry.hostname,
                '[]'
            ))
            
            result = self.mysql_tool.query("SELECT LAST_INSERT_ID() as id")
            execution_id = result[0]['id'] if result else None
            
            # 创建流程追踪器
            trace = ExecutionTrace(execution_id) if execution_id else None
            
            logger.info(f"[TaskExecution] Started: {log_entry.process_id}, ID: {execution_id}")
            return execution_id, trace
            
        except Exception as e:
            logger.error(f"[TaskExecution] Failed to start log: {e}")
            return None, None
    
    def end_execution(self, execution_id: int, trace: ExecutionTrace = None,
                     status: str = 'success', result_message: str = "",
                     error_type: str = None, error_stack: str = None,
                     records_count: int = 0, **metrics):
        """记录任务执行结束"""
        try:
            # 计算执行时长
            start_result = self.mysql_tool.query(
                "SELECT start_time FROM task_execution_log WHERE id = %s",
                (execution_id,)
            )
            duration = 0
            if start_result:
                start_time = start_result[0]['start_time']
                duration = int((datetime.now() - start_time).total_seconds())
            
            # 更新执行记录
            execution_trace = json.dumps(trace.steps if trace else [], ensure_ascii=False)
            
            sql = """
                UPDATE task_execution_log 
                SET end_time = %s, status = %s, duration_seconds = %s,
                    result_message = %s, error_type = %s, error_stack = %s,
                    records_count = %s, execution_trace = %s,
                    db_query_count = %s, api_call_count = %s, total_rows_processed = %s
                WHERE id = %s
            """
            
            self.mysql_tool.execute(sql, (
                datetime.now(),
                status,
                duration,
                result_message,
                error_type,
                error_stack,
                records_count,
                execution_trace,
                metrics.get('db_query_count', 0),
                metrics.get('api_call_count', 0),
                metrics.get('total_rows_processed', 0),
                execution_id
            ))
            
            logger.info(f"[TaskExecution] Ended: ID={execution_id}, status={status}, duration={duration}s")
            
        except Exception as e:
            logger.error(f"[TaskExecution] Failed to end log: {e}")
    
    def update_by_process_id(self, process_id: str, status: str,
                            result_message: str = ""):
        """通过process_id更新执行记录（用于停止任务时）"""
        try:
            sql = """
                UPDATE task_execution_log 
                SET end_time = %s, status = %s, result_message = %s
                WHERE process_id = %s AND status = 'running'
            """
            self.mysql_tool.execute(sql, (
                datetime.now(), status, result_message, process_id
            ))
        except Exception as e:
            logger.error(f"[TaskExecution] Failed to update log: {e}")
    
    def get_execution_detail(self, execution_id: int) -> Optional[Dict]:
        """获取执行详情（包含步骤回溯）"""
        try:
            # 获取主记录
            sql = "SELECT * FROM task_execution_log WHERE id = %s"
            result = self.mysql_tool.query(sql, (execution_id,))
            if not result:
                return None
            
            execution = dict(result[0])
            for field in ['execution_trace', 'params']:
                if execution.get(field) and isinstance(execution[field], str):
                    execution[field] = json.loads(execution[field])
            
            # 获取步骤详情
            sql = """
                SELECT * FROM task_execution_step 
                WHERE execution_id = %s 
                ORDER BY step_order
            """
            steps = self.mysql_tool.query(sql, (execution_id,))
            execution['steps_detail'] = []
            for step in steps or []:
                step_dict = dict(step)
                for field in ['input_params', 'output_result']:
                    if step_dict.get(field) and isinstance(step_dict[field], str):
                        step_dict[field] = json.loads(step_dict[field])
                execution['steps_detail'].append(step_dict)
            
            return execution
            
        except Exception as e:
            logger.error(f"[TaskExecution] Failed to get detail: {e}")
            return None


# 全局实例
task_execution_logger = TaskExecutionLogger()
```

---

## 4. 集成方案

### 4.1 包装脚本模板修改

```python
# process_manager.py 中的 _generate_collection_wrapper 方法

def _generate_collection_wrapper(self, service_id: str, script_name: str, 
                                 function_name: str, params: Dict,
                                 module: str = "base") -> str:
    """生成采集包装脚本（带执行记录）"""
    
    # ... 路径处理逻辑 ...
    
    params_str = json.dumps(params, ensure_ascii=False)
    
    lines = [
        '#!/usr/bin/env python3',
        'import sys',
        'import os',
        'import json',
        'import traceback',
        'from pathlib import Path',
        'from datetime import datetime',
        '',
        'PROJECT_ROOT = Path(__file__).parent.parent',
        'sys.path.insert(0, str(PROJECT_ROOT))',
        '',
        '# 导入执行记录器',
        'from gs2026.utils.task_execution_logger import task_execution_logger',
        '',
        f'SERVICE_ID = "{service_id}"',
        f'FUNCTION_NAME = "{function_name}"',
        f'MODULE = "{module}"',
        f'PARAMS = {params_str}',
        f'PROCESS_ID = "{service_id}_" + datetime.now().strftime("%Y%m%d_%H%M%S")',
        '',
        '# 记录执行开始',
        'execution_id, trace = task_execution_logger.start_execution(',
        '    process_id=PROCESS_ID,',
        '    service_id=SERVICE_ID,',
        '    module=MODULE,',
        '    task_name=FUNCTION_NAME,',
        '    params=PARAMS,',
        '    pid=os.getpid(),',
        '    wrapper_path=str(Path(__file__))',
        ')',
        '',
        'records_count = 0',
        'error_msg = ""',
        'error_type = None',
        '',
        'try:',
        f'    from {script_path} import {function_name}',
        '    ',
        '    # 如果函数支持trace参数，传递trace',
        f'    import inspect',
        f'    sig = inspect.signature({function_name})',
        f'    if "execution_id" in sig.parameters:',
        f'        result = {function_name}(execution_id=execution_id, **PARAMS)',
        f'    else:',
        f'        result = {function_name}(**PARAMS)',
        '    ',
        '    # 尝试获取处理记录数',
        '    if isinstance(result, dict):',
        '        records_count = result.get("records_count", 0)',
        '    elif isinstance(result, int):',
        '        records_count = result',
        '    ',
        '    # 记录成功',
        '    if execution_id:',
        '        task_execution_logger.end_execution(',
        '            execution_id=execution_id,',
        '            trace=trace,',
        '            status="success",',
        '            result_message="执行成功",',
        '            records_count=records_count',
        '        )',
        '',
        'except Exception as e:',
        '    error_type = type(e).__name__',
        '    error_msg = str(e)',
        '    traceback_str = traceback.format_exc()',
        '    ',
        '    # 记录失败',
        '    if execution_id:',
        '        task_execution_logger.end_execution(',
        '            execution_id=execution_id,',
        '            trace=trace,',
        '            status="failed",',
        '            result_message=error_msg,',
        '            error_type=error_type,',
        '            error_stack=traceback_str,',
        '            records_count=records_count',
        '        )',
        '    raise',
    ]
    
    return '\n'.join(lines)
```

### 4.2 采集函数改造示例

```python
# notice_risk_history.py 改造示例

def notice_and_risk_collect(start_date: str, end_date: str, 
                           execution_id: int = None) -> Dict:
    """
    先执行公告采集，再执行公告风险采集
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        execution_id: 执行记录ID（用于流程追踪）
    
    Returns:
        {"records_count": int, "steps": [...]}
    """
    from gs2026.utils.task_execution_logger import ExecutionTrace
    
    trace = ExecutionTrace(execution_id) if execution_id else None
    result = {"records_count": 0, "steps": []}
    
    # 步骤1：公告采集
    if trace:
        with trace.step_context("公告数据采集", "process", 
                               {"start_date": start_date, "end_date": end_date}):
            records = notice_collect(start_date, end_date, trace)
            result["records_count"] += records
    else:
        records = notice_collect(start_date, end_date)
        result["records_count"] += records
    
    # 步骤2：风险分析
    if trace:
        with trace.step_context("公告风险分析", "process",
                               {"start_date": start_date, "end_date": end_date}):
            risk_records = notice_risk_collect(start_date, end_date, trace)
            result["records_count"] += risk_records
    else:
        risk_records = notice_risk_collect(start_date, end_date)
        result["records_count"] += risk_records
    
    return result


def notice_collect(start_date: str, end_date: str,
                   trace: ExecutionTrace = None) -> int:
    """公告采集（支持步骤追踪）"""
    total_records = 0
    
    # 获取交易日列表
    if trace:
        with trace.step_context("获取交易日列表", "query",
                               {"start": start_date, "end": end_date}):
            day_sql = f"""select trade_date from data_jyrl 
                         where trade_date between '{start_date}' and '{end_date}' 
                         order by trade_date desc"""
            day_df = pd.read_sql(day_sql, con=con)
    else:
        day_sql = f"""select trade_date from data_jyrl 
                     where trade_date between '{start_date}' and '{end_date}' 
                     order by trade_date desc"""
        day_df = pd.read_sql(day_sql, con=con)
    
    date_list = day_df.values.tolist()
    
    # 逐日采集
    for date1 in date_list:
        set_date = date1[0]
        now_str = set_date.replace("-", "")
        year = set_date[:4]
        save_table_name = f'jhsaggg{year}'
        
        if trace:
            with trace.step_context(f"采集 {set_date} 公告", "api",
                                   {"date": set_date, "table": save_table_name}):
                df = hsjaggg(now_str)
                rows = len(df)
                save2mysql(df, save_table_name, '内容hash', '')
                total_records += rows
        else:
            df = hsjaggg(now_str)
            save2mysql(df, save_table_name, '内容hash', '')
            total_records += len(df)
    
    return total_records
```

---

## 5. API 接口设计

### 5.1 查询执行记录

```python
# collection.py

@collection_bp.route('/executions', methods=['GET'])
def get_executions():
    """获取任务执行记录列表"""
    module = request.args.get('module')
    status = request.args.get('status')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    
    from gs2026.utils.task_execution_logger import task_execution_logger
    
    # 构建查询
    conditions = []
    params = []
    if module:
        conditions.append("module = %s")
        params.append(module)
    if status:
        conditions.append("status = %s")
        params.append(status)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    sql = f"""
        SELECT * FROM task_execution_log 
        {where_clause}
        ORDER BY start_time DESC 
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    result = mysql_tool.query(sql, tuple(params))
    logs = [TaskExecutionLog.from_db_row(row).to_dict() for row in result] if result else []
    
    return jsonify({
        'success': True,
        'data': logs,
        'total': len(logs)
    })


@collection_bp.route('/execution/<int:execution_id>', methods=['GET'])
def get_execution_detail(execution_id: int):
    """获取执行详情（用于问题排查）"""
    from gs2026.utils.task_execution_logger import task_execution_logger
    
    detail = task_execution_logger.get_execution_detail(execution_id)
    if not detail:
        return jsonify({'success': False, 'message': '执行记录不存在'})
    
    # 格式化时间轴
    timeline = []
    for step in detail.get('steps_detail', []):
        timeline.append({
            'time': step['start_time'].strftime('%H:%M:%S.%f')[:-3] if step['start_time'] else '-',
            'step': step['step_order'],
            'name': step['step_name'],
            'type': step['step_type'],
            'duration': f"{step['duration_ms']}ms" if step['duration_ms'] else '-',
            'status': step['status'],
            'rows': step['rows_affected'],
            'error': step['error_message'][:200] if step['error_message'] else None
        })
    
    return jsonify({
        'success': True,
        'data': {
            'execution_id': detail['id'],
            'process_id': detail['process_id'],
            'service_id': detail['service_id'],
            'module': detail['module'],
            'task_name': detail['task_name'],
            'status': detail['status'],
            'params': detail['params'],
            'start_time': detail['start_time'],
            'end_time': detail['end_time'],
            'duration': detail['duration_seconds'],
            'error_type': detail['error_type'],
            'error_stack': detail['error_stack'],
            'timeline': timeline,
            'metrics': {
                'db_queries': detail['db_query_count'],
                'api_calls': detail['api_call_count'],
                'total_rows': detail['total_rows_processed']
            }
        }
    })
```

---

## 6. 问题排查示例

### 场景：公告风险采集失败

**步骤1：查看执行列表**
```
GET /api/collection/executions?module=risk&status=failed
```

**步骤2：获取失败详情**
```
GET /api/collection/execution/12345
```

**响应示例：**
```json
{
  "success": true,
  "data": {
    "execution_id": 12345,
    "service_id": "notice_risk",
    "status": "failed",
    "params": {"start_date": "2026-03-19", "end_date": "2026-04-04"},
    "duration": 127,
    "error_type": "ConnectionTimeout",
    "timeline": [
      {"time": "02:15:32.123", "step": 1, "name": "获取交易日列表", "type": "query", "duration": "15ms", "status": "success"},
      {"time": "02:15:32.456", "step": 2, "name": "采集 2026-03-30 公告", "type": "api", "duration": "5234ms", "status": "success", "rows": 150},
      {"time": "02:15:37.890", "step": 3, "name": "采集 2026-03-29 公告", "type": "api", "duration": "120ms", "status": "failed", "error": "Connection timeout"}
    ],
    "metrics": {
      "db_queries": 3,
      "api_calls": 2,
      "total_rows": 150
    }
  }
}
```

**结论**：第3步 API 调用超时，需要检查网络或 API 服务状态。

---

## 7. 实施计划

### 阶段一：基础框架（1天）
- [ ] 创建数据库表
- [ ] 创建数据模型
- [ ] 创建 TaskExecutionLogger

### 阶段二：集成改造（2天）
- [ ] 修改 process_manager.py 包装脚本
- [ ] 修改所有采集函数支持 trace 参数
- [ ] 添加 API 接口

### 阶段三：前端展示（1天）
- [ ] 创建执行记录列表页面
- [ ] 创建执行详情/时间轴页面

### 阶段四：优化完善（1天）
- [ ] 性能测试
- [ ] 错误处理完善

---

## 8. 文件清单

| 文件 | 说明 |
|------|------|
| `gs2026/models/task_execution.py` | 数据模型 |
| `gs2026/utils/task_execution_logger.py` | 执行记录管理器 |
| `gs2026/dashboard/services/process_manager.py` | 包装脚本生成（修改） |
| `gs2026/dashboard2/routes/collection.py` | API接口（修改） |
| `gs2026/collection/risk/notice_risk_history.py` | 采集函数示例（修改） |

---

**文档保存完毕，待后续实施。**
