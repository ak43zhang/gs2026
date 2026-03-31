"""
Dashboard2 调度中心 API 路由
提供任务管理、执行记录、调度链等接口
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json

from gs2026.dashboard2.services.scheduler_service import scheduler_service
from gs2026.utils import log_util

logger = log_util.setup_logger(__name__)

scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/api/scheduler')


# ========== 任务管理 API ==========

@scheduler_bp.route('/jobs', methods=['GET'])
def list_jobs():
    """获取调度任务列表"""
    try:
        filters = {}
        job_type = request.args.get('job_type')
        status = request.args.get('status')

        if job_type:
            filters['job_type'] = job_type
        if status:
            filters['status'] = status

        jobs = scheduler_service.get_jobs(filters if filters else None)

        # 解析JSON字段并格式化时间
        for job in jobs:
            for field in ['job_config', 'trigger_config', 'next_job_ids']:
                if job.get(field) and isinstance(job[field], str):
                    try:
                        job[field] = json.loads(job[field])
                    except:
                        pass
            # 格式化时间字段
            for time_field in ['last_run_time', 'created_at', 'updated_at']:
                if job.get(time_field):
                    job[time_field] = _format_datetime(job[time_field])

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'jobs': jobs,
                'total': len(jobs)
            }
        })
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs', methods=['POST'])
def create_job():
    """创建调度任务"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['job_id', 'job_name', 'job_type', 'job_config', 'trigger_type', 'trigger_config']
        for field in required_fields:
            if field not in data:
                return jsonify({'code': 400, 'message': f'Missing required field: {field}'}), 400
        
        # 设置默认值
        if 'status' not in data:
            data['status'] = 'enabled'
        if 'created_by' not in data:
            data['created_by'] = 'system'
        
        job_id = scheduler_service.add_job(data)
        
        return jsonify({
            'code': 200,
            'message': 'Job created successfully',
            'data': {'job_id': job_id}
        })
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """获取任务详情"""
    try:
        job = scheduler_service.get_job(job_id)
        
        if not job:
            return jsonify({'code': 404, 'message': 'Job not found'}), 404
        
        # 解析JSON字段
        for field in ['job_config', 'trigger_config', 'next_job_ids']:
            if job.get(field) and isinstance(job[field], str):
                try:
                    job[field] = json.loads(job[field])
                except:
                    pass
        
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': job
        })
    except Exception as e:
        logger.error(f"Failed to get job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs/<job_id>', methods=['PUT'])
def update_job(job_id):
    """更新调度任务"""
    try:
        data = request.get_json()
        
        # 不允许修改job_id
        if 'job_id' in data:
            del data['job_id']
        
        scheduler_service.update_job(job_id, data)
        
        return jsonify({
            'code': 200,
            'message': 'Job updated successfully',
            'data': {'job_id': job_id}
        })
    except Exception as e:
        logger.error(f"Failed to update job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """删除调度任务"""
    try:
        scheduler_service.remove_job(job_id)
        
        return jsonify({
            'code': 200,
            'message': 'Job deleted successfully',
            'data': {'job_id': job_id}
        })
    except Exception as e:
        logger.error(f"Failed to delete job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs/<job_id>/toggle', methods=['POST'])
def toggle_job(job_id):
    """启用/禁用任务"""
    try:
        data = request.get_json() or {}
        enabled = data.get('enabled', True)
        
        scheduler_service.toggle_job(job_id, enabled)
        
        return jsonify({
            'code': 200,
            'message': f"Job {'enabled' if enabled else 'disabled'} successfully",
            'data': {'job_id': job_id, 'enabled': enabled}
        })
    except Exception as e:
        logger.error(f"Failed to toggle job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/jobs/<job_id>/run', methods=['POST'])
def run_job_now(job_id):
    """立即执行任务"""
    try:
        result = scheduler_service.run_job_now(job_id)
        
        return jsonify({
            'code': 200,
            'message': 'Job triggered successfully',
            'data': {'job_id': job_id, 'result': result}
        })
    except Exception as e:
        logger.error(f"Failed to run job: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


# ========== 执行记录 API ==========

def _format_datetime(dt):
    """将datetime格式化为带时区的ISO格式（北京时间）"""
    if dt is None:
        return None
    if isinstance(dt, str):
        # 如果已经是字符串，检查是否包含时区信息
        if '+08:00' in dt or 'Z' in dt:
            return dt
        # 如果是GMT格式（如 "Tue, 31 Mar 2026 22:46:09 GMT"），转换为ISO格式
        if 'GMT' in dt:
            try:
                from datetime import datetime
                # 解析GMT格式
                dt_obj = datetime.strptime(dt, '%a, %d %b %Y %H:%M:%S GMT')
                return dt_obj.strftime('%Y-%m-%dT%H:%M:%S+08:00')
            except:
                pass
        return dt
    # 假设dt是北京时间，添加+08:00时区标记
    return dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')


@scheduler_bp.route('/executions', methods=['GET'])
def list_executions():
    """获取执行记录列表"""
    try:
        job_id = request.args.get('job_id')
        limit = int(request.args.get('limit', 50))

        executions = scheduler_service.get_executions(job_id, limit)

        # 解析JSON字段并格式化时间
        for execution in executions:
            for field in ['next_executions']:
                if execution.get(field) and isinstance(execution[field], str):
                    try:
                        execution[field] = json.loads(execution[field])
                    except:
                        pass
            # 格式化时间字段
            for time_field in ['start_time', 'end_time', 'created_at', 'updated_at']:
                if execution.get(time_field):
                    execution[time_field] = _format_datetime(execution[time_field])

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'executions': executions,
                'total': len(executions)
            }
        })
    except Exception as e:
        logger.error(f"Failed to list executions: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/executions/<execution_id>', methods=['GET'])
def get_execution_detail(execution_id):
    """获取执行详情"""
    try:
        execution = scheduler_service.get_execution(execution_id)

        if not execution:
            return jsonify({'code': 404, 'message': 'Execution not found'}), 404

        # 解析JSON字段
        for field in ['next_executions']:
            if execution.get(field) and isinstance(execution[field], str):
                try:
                    execution[field] = json.loads(execution[field])
                except:
                    pass

        # 格式化时间字段
        for time_field in ['start_time', 'end_time', 'created_at', 'updated_at']:
            if execution.get(time_field):
                execution[time_field] = _format_datetime(execution[time_field])

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': execution
        })
    except Exception as e:
        logger.error(f"Failed to get execution: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/executions/running', methods=['GET'])
def get_running_executions():
    """获取正在执行的作业"""
    try:
        executions = scheduler_service.get_running_executions()

        # 格式化时间字段
        for execution in executions:
            for time_field in ['start_time', 'end_time', 'created_at', 'updated_at']:
                if execution.get(time_field):
                    execution[time_field] = _format_datetime(execution[time_field])

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'executions': executions,
                'total': len(executions)
            }
        })
    except Exception as e:
        logger.error(f"Failed to get running executions: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


# ========== 调度链 API ==========

@scheduler_bp.route('/chains', methods=['GET'])
def list_chains():
    """获取调度链列表"""
    try:
        # 获取chain类型的任务
        chains = scheduler_service.get_jobs({'job_type': 'chain'})
        
        # 解析JSON字段
        for chain in chains:
            for field in ['job_config', 'trigger_config', 'next_job_ids']:
                if chain.get(field) and isinstance(chain[field], str):
                    try:
                        chain[field] = json.loads(chain[field])
                    except:
                        pass
        
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'chains': chains,
                'total': len(chains)
            }
        })
    except Exception as e:
        logger.error(f"Failed to list chains: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/chains', methods=['POST'])
def create_chain():
    """创建调度链"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['job_id', 'job_name', 'job_config']
        for field in required_fields:
            if field not in data:
                return jsonify({'code': 400, 'message': f'Missing required field: {field}'}), 400
        
        # 强制设置为chain类型
        data['job_type'] = 'chain'
        
        # 设置默认触发器（如果没有）
        if 'trigger_type' not in data:
            data['trigger_type'] = 'cron'
        if 'trigger_config' not in data:
            data['trigger_config'] = {'hour': 9, 'minute': 30}
        
        job_id = scheduler_service.add_job(data)
        
        return jsonify({
            'code': 200,
            'message': 'Chain created successfully',
            'data': {'job_id': job_id}
        })
    except Exception as e:
        logger.error(f"Failed to create chain: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/chains/<chain_id>/run', methods=['POST'])
def run_chain(chain_id):
    """执行调度链"""
    try:
        result = scheduler_service.run_job_now(chain_id)
        
        return jsonify({
            'code': 200,
            'message': 'Chain triggered successfully',
            'data': {'chain_id': chain_id, 'result': result}
        })
    except Exception as e:
        logger.error(f"Failed to run chain: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


# ========== 调度器管理 API ==========

@scheduler_bp.route('/status', methods=['GET'])
def get_scheduler_status():
    """获取调度器状态"""
    try:
        status = scheduler_service.get_scheduler_status()
        
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': status
        })
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/start', methods=['POST'])
def start_scheduler():
    """启动调度器"""
    try:
        scheduler_service.start()
        
        return jsonify({
            'code': 200,
            'message': 'Scheduler started successfully',
            'data': scheduler_service.get_scheduler_status()
        })
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@scheduler_bp.route('/stop', methods=['POST'])
def stop_scheduler():
    """停止调度器"""
    try:
        scheduler_service.shutdown()
        
        return jsonify({
            'code': 200,
            'message': 'Scheduler stopped successfully',
            'data': scheduler_service.get_scheduler_status()
        })
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


# ========== 页面路由 ==========

@scheduler_bp.route('/page', methods=['GET'])
def scheduler_page():
    """调度中心页面"""
    from flask import render_template
    return render_template('scheduler.html')
