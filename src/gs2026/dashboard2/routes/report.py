"""
报表中心路由
"""
from flask import Blueprint, jsonify, request, send_file
import sys
from pathlib import Path
from datetime import date, datetime
import uuid

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..models.database import get_session
from ..models.report_model import ReportType, Report, ReportTask
from ..services.tts_service import SyncTTSService
from gs2026.report import ReportGeneratorFactory

report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# 输出目录
OUTPUT_ROOT = Path(project_root) / 'output'
TTS_CACHE_DIR = OUTPUT_ROOT / 'tts_cache'

# TTS 服务
tts_service = SyncTTSService(TTS_CACHE_DIR)


@report_bp.route('/types', methods=['GET'])
def get_report_types():
    """获取报告类型列表"""
    try:
        session = get_session('gs_platform')
        types = session.query(ReportType).filter_by(report_type_is_active=True).order_by(
            ReportType.report_type_sort_order
        ).all()
        
        # 获取每种类型的报告数量
        result = []
        for t in types:
            count = session.query(Report).filter_by(report_type=t.report_type_code).count()
            data = t.to_dict()
            data['report_count'] = count
            result.append(data)
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """获取报告列表"""
    try:
        session = get_session('gs_platform')
        
        # 获取参数
        report_type = request.args.get('type')
        report_format = request.args.get('format')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 20))
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        keyword = request.args.get('keyword')
        
        # 构建查询
        query = session.query(Report)
        
        if report_type:
            query = query.filter_by(report_type=report_type)
        if report_format:
            query = query.filter_by(report_file_format=report_format)
        if start_date:
            query = query.filter(Report.report_date >= start_date)
        if end_date:
            query = query.filter(Report.report_date <= end_date)
        if keyword:
            query = query.filter(Report.report_name.like(f'%{keyword}%'))
        
        # 按时间倒序
        query = query.order_by(Report.report_date.desc(), Report.report_created_at.desc())
        
        # 分页
        total = query.count()
        reports = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return jsonify({
            'success': True,
            'data': {
                'report_total': total,
                'report_page': page,
                'report_page_size': page_size,
                'report_list': [r.to_dict() for r in reports]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<int:report_id>', methods=['GET'])
def get_report(report_id):
    """获取报告详情"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report:
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        data = report.to_dict(include_content=True)
        data['report_view_url'] = f'/api/reports/file/{report_id}/view'
        if report.report_tts_audio_path:
            data['report_tts_audio_url'] = f'/api/reports/{report_id}/tts/audio'
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/file/<int:report_id>/view', methods=['GET'])
def view_report_file(report_id):
    """查看报告文件"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report:
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        file_path = OUTPUT_ROOT / report.report_file_path
        
        if not file_path.exists():
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        # 根据格式返回不同内容
        fmt = report.report_file_format.lower()
        
        if fmt == 'pdf':
            return send_file(file_path, mimetype='application/pdf')
        elif fmt == 'epub':
            return send_file(file_path, mimetype='application/epub+zip')
        elif fmt == 'txt':
            return send_file(file_path, mimetype='text/plain')
        elif fmt in ['md', 'markdown']:
            content = file_path.read_text(encoding='utf-8')
            return jsonify({'success': True, 'content': content, 'format': 'markdown'})
        elif fmt == 'html':
            content = file_path.read_text(encoding='utf-8')
            return jsonify({'success': True, 'content': content, 'format': 'html'})
        elif fmt == 'docx':
            # TODO: 转换为 HTML
            return send_file(file_path, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif fmt == 'xlsx':
            # TODO: 转换为 JSON
            return send_file(file_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            return send_file(file_path)
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<int:report_id>/tts/generate', methods=['POST'])
def generate_tts(report_id):
    """生成语音播报"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report:
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        # 检查是否有文本内容
        if not report.report_content_text:
            return jsonify({'success': False, 'error': '报告没有文本内容'}), 400
        
        # 获取参数
        data = request.get_json() or {}
        voice = data.get('voice', 'xiaoxiao')
        speed = data.get('speed', 1.0)
        
        # 更新状态为 running
        report.report_tts_status = 'running'
        session.commit()
        
        try:
            # 生成语音
            result = tts_service.generate_for_report(report, TTS_CACHE_DIR)
            
            # 更新报告记录
            report.report_tts_status = 'completed'
            report.report_tts_duration = result['duration']
            report.report_tts_audio_path = result['audio_path'].replace(str(OUTPUT_ROOT), '').lstrip('/\\')
            session.commit()
            
            return jsonify({
                'success': True,
                'data': {
                    'report_tts_status': 'completed',
                    'report_tts_duration': result['duration'],
                    'report_tts_audio_url': f'/api/reports/{report_id}/tts/audio'
                }
            })
            
        except Exception as e:
            report.report_tts_status = 'failed'
            session.commit()
            raise e
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<int:report_id>/tts/status', methods=['GET'])
def get_tts_status(report_id):
    """获取语音生成状态"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report:
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        result = {
            'report_tts_status': report.report_tts_status,
            'report_tts_duration': report.report_tts_duration
        }
        
        if report.report_tts_audio_path:
            result['report_tts_audio_url'] = f'/api/reports/{report_id}/tts/audio'
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<int:report_id>/tts/audio', methods=['GET'])
def get_tts_audio(report_id):
    """获取语音文件"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report or not report.report_tts_audio_path:
            return jsonify({'success': False, 'error': '语音文件不存在'}), 404
        
        audio_path = OUTPUT_ROOT / report.report_tts_audio_path
        
        if not audio_path.exists():
            return jsonify({'success': False, 'error': '语音文件不存在'}), 404
        
        return send_file(audio_path, mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """生成报告"""
    try:
        data = request.get_json() or {}
        report_type = data.get('report_type') or data.get('type')
        report_date = data.get('report_date') or data.get('date')
        report_format = data.get('report_format') or data.get('format')
        params = data.get('report_params') or data.get('params', {})
        
        if not report_type or not report_date:
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        session = get_session('gs_platform')
        
        # 检查类型是否存在（通过 code 查询）
        type_obj = session.query(ReportType).filter_by(report_type_code=report_type).first()
        if not type_obj:
            return jsonify({'success': False, 'error': '报告类型不存在'}), 400
        
        # 生成任务ID
        task_id = f"{report_type}_{report_date.replace('-', '')}_{uuid.uuid4().hex[:6]}"
        
        # 创建任务记录
        task = ReportTask(
            report_task_id=task_id,
            report_type=report_type,
            report_date=report_date,
            report_format=report_format or type_obj.report_type_default_format,
            report_task_status='pending',
            report_task_params=params
        )
        session.add(task)
        session.commit()
        
        # 启动生成任务（同步执行，后续可改为异步）
        try:
            task.report_task_status = 'running'
            task.report_task_started_at = datetime.now()
            session.commit()
            
            # 获取生成器
            generator = ReportGeneratorFactory.get_generator(report_type)
            
            # 生成报告
            result = generator.generate(
                report_date=datetime.strptime(report_date, '%Y-%m-%d').date(),
                output_format=report_format or type_obj.report_type_default_format,
                params=params
            )
            
            # 创建报告记录
            report = Report(
                report_type=report_type,
                report_name=generator.get_report_name(datetime.strptime(report_date, '%Y-%m-%d').date()),
                report_date=report_date,
                report_file_path=result['file_path'],
                report_file_format=report_format or type_obj.report_type_default_format,
                report_file_size=result['file_size'],
                report_page_count=result['page_count'],
                report_content_text=result['content_text'],
                report_params=params,
                report_status='completed'
            )
            session.add(report)
            session.commit()
            
            # 更新任务状态
            task.report_task_status = 'completed'
            task.report_task_result_id = report.report_id
            task.report_task_completed_at = datetime.now()
            task.report_task_progress = 100
            session.commit()
            
            return jsonify({
                'success': True,
                'data': {
                    'report_task_id': task_id,
                    'report_task_status': 'completed',
                    'report_id': report.report_id
                }
            })
            
        except Exception as e:
            task.report_task_status = 'failed'
            task.report_task_error = str(e)
            task.report_task_completed_at = datetime.now()
            session.commit()
            raise e
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/tasks/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    """获取任务状态"""
    try:
        session = get_session('gs_platform')
        task = session.query(ReportTask).get(task_id)
        
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        
        return jsonify({'success': True, 'data': task.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    """删除报告"""
    try:
        session = get_session('gs_platform')
        report = session.query(Report).get(report_id)
        
        if not report:
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        # 删除文件
        file_path = OUTPUT_ROOT / report.report_file_path
        if file_path.exists():
            file_path.unlink()
        
        # 删除语音文件
        if report.report_tts_audio_path:
            audio_path = OUTPUT_ROOT / report.report_tts_audio_path
            if audio_path.exists():
                audio_path.unlink()
        
        # 删除数据库记录
        session.delete(report)
        session.commit()
        
        return jsonify({'success': True, 'message': '报告已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
