"""
报表中心路由 - 支持本地文件系统扫描
"""
from flask import Blueprint, jsonify, request, send_file, current_app
from pathlib import Path
from datetime import datetime
import re

report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# 报告根目录
REPORT_ROOT = Path('G:/report')

# 报告类型配置（从目录结构自动发现）
def get_report_types():
    """获取报告类型（从目录结构）"""
    types = []
    if not REPORT_ROOT.exists():
        return types
    
    # 遍历根目录下的子目录
    for idx, dir_path in enumerate(sorted(REPORT_ROOT.iterdir()), 1):
        if dir_path.is_dir():
            type_code = dir_path.name
            # 获取该类型下的文件数量
            file_count = len(list(dir_path.glob('*.pdf')))
            
            types.append({
                'report_type_code': type_code,
                'report_type_name': type_code,  # 使用目录名作为显示名
                'report_type_icon': '📄',
                'report_type_description': f'{type_code} 报告',
                'report_type_output_dir': str(dir_path),
                'report_type_default_format': 'pdf',
                'report_type_supported_formats': ['pdf'],
                'report_type_is_active': True,
                'report_type_sort_order': idx,
                'file_count': file_count
            })
    
    return types


@report_bp.route('/types', methods=['GET'])
def get_types():
    """获取报告类型列表"""
    try:
        types = get_report_types()
        return jsonify({
            'success': True,
            'data': types
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """获取报告列表（从文件系统）"""
    try:
        report_type = request.args.get('type')
        keyword = request.args.get('keyword', '')
        
        reports = []
        
        if report_type:
            # 扫描指定类型的目录
            type_dir = REPORT_ROOT / report_type
            if type_dir.exists():
                for file_path in sorted(type_dir.glob('*.pdf'), reverse=True):
                    # 提取日期（从文件名）
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{8})', file_path.name)
                    report_date = date_match.group(1) if date_match else ''
                    
                    # 格式化日期
                    if report_date and len(report_date) == 8:
                        report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"
                    
                    # 检查是否匹配关键词
                    if keyword and keyword.lower() not in file_path.name.lower():
                        continue
                    
                    stat = file_path.stat()
                    reports.append({
                        'report_id': str(file_path),  # 使用完整路径作为ID
                        'report_type': report_type,
                        'report_name': file_path.stem,
                        'report_date': report_date,
                        'report_file_path': str(file_path),
                        'report_file_format': 'pdf',
                        'report_file_size': stat.st_size,
                        'report_page_count': 0,  # 暂不计算页数
                        'report_tts_status': 'none',
                        'report_created_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
        else:
            # 扫描所有类型
            for type_dir in REPORT_ROOT.iterdir():
                if type_dir.is_dir():
                    for file_path in sorted(type_dir.glob('*.pdf'), reverse=True):
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{8})', file_path.name)
                        report_date = date_match.group(1) if date_match else ''
                        
                        if keyword and keyword.lower() not in file_path.name.lower():
                            continue
                        
                        stat = file_path.stat()
                        reports.append({
                            'report_id': str(file_path),
                            'report_type': type_dir.name,
                            'report_name': file_path.stem,
                            'report_date': report_date,
                            'report_file_path': str(file_path),
                            'report_file_format': 'pdf',
                            'report_file_size': stat.st_size,
                            'report_page_count': 0,
                            'report_tts_status': 'none',
                            'report_created_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
        
        # 分页
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 20))
        total = len(reports)
        start = (page - 1) * page_size
        end = start + page_size
        
        return jsonify({
            'success': True,
            'data': {
                'report_list': reports[start:end],
                'report_total': total,
                'report_page': page
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/<path:report_path>', methods=['GET'])
def get_report(report_path):
    """获取报告详情"""
    try:
        file_path = Path(report_path)
        if not file_path.exists():
            return jsonify({'success': False, 'error': '报告不存在'}), 404
        
        stat = file_path.stat()
        
        return jsonify({
            'success': True,
            'data': {
                'report_id': str(file_path),
                'report_type': file_path.parent.name,
                'report_name': file_path.stem,
                'report_date': '',
                'report_file_path': str(file_path),
                'report_file_format': 'pdf',
                'report_file_size': stat.st_size,
                'report_page_count': 0,
                'report_view_url': f'/api/reports/file/{file_path.name}/view?path={file_path.parent}',
                'report_download_url': f'/api/reports/file/{file_path.name}/download?path={file_path.parent}'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/file/<filename>/view', methods=['GET'])
def view_file(filename):
    """查看/预览报告文件"""
    try:
        file_dir = request.args.get('path', '')
        if file_dir:
            file_path = Path(file_dir) / filename
        else:
            # 尝试在所有类型目录中查找
            file_path = None
            for type_dir in REPORT_ROOT.iterdir():
                if type_dir.is_dir():
                    candidate = type_dir / filename
                    if candidate.exists():
                        file_path = candidate
                        break
        
        if not file_path or not file_path.exists():
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=False
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/file/<filename>/download', methods=['GET'])
def download_file(filename):
    """下载报告文件"""
    try:
        file_dir = request.args.get('path', '')
        if file_dir:
            file_path = Path(file_dir) / filename
        else:
            file_path = None
            for type_dir in REPORT_ROOT.iterdir():
                if type_dir.is_dir():
                    candidate = type_dir / filename
                    if candidate.exists():
                        file_path = candidate
                        break
        
        if not file_path or not file_path.exists():
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/scan', methods=['POST'])
def scan_reports():
    """重新扫描报告目录"""
    try:
        types = get_report_types()
        total_files = sum(t['file_count'] for t in types)
        
        return jsonify({
            'success': True,
            'data': {
                'types_found': len(types),
                'total_files': total_files,
                'types': types
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
