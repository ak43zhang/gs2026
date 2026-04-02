"""
Report Center Routes - File system based report management
"""
from flask import Blueprint, jsonify, request, send_file, render_template
from pathlib import Path
import logging

from ..services.report_service import ReportService

logger = logging.getLogger(__name__)

# Create blueprint
report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# Initialize service
report_service = ReportService()


@report_bp.route('/types', methods=['GET'])
def get_report_types():
    """Get all report types (subdirectories)"""
    try:
        types = report_service.get_report_types()
        return jsonify({
            "success": True,
            "data": types
        })
    except Exception as e:
        logger.error(f"Error getting report types: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/list', methods=['GET'])
def get_reports():
    """Get reports by type"""
    try:
        report_type = request.args.get('type', '')
        
        if not report_type:
            return jsonify({
                "success": False,
                "error": "Report type is required"
            }), 400
        
        reports = report_service.get_reports_by_type(report_type)
        return jsonify({
            "success": True,
            "data": {
                "type": report_type,
                "reports": reports,
                "total": len(reports)
            }
        })
    except Exception as e:
        logger.error(f"Error getting reports: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/search', methods=['GET'])
def search_reports():
    """Search reports by keyword"""
    try:
        keyword = request.args.get('keyword', '')
        
        if not keyword:
            return jsonify({
                "success": False,
                "error": "Keyword is required"
            }), 400
        
        results = report_service.search_reports(keyword)
        return jsonify({
            "success": True,
            "data": {
                "keyword": keyword,
                "reports": results,
                "total": len(results)
            }
        })
    except Exception as e:
        logger.error(f"Error searching reports: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/file', methods=['GET'])
def get_report_file():
    """Get report file for preview/download"""
    try:
        report_type = request.args.get('type', '')
        filename = request.args.get('filename', '')
        
        if not report_type or not filename:
            return jsonify({
                "success": False,
                "error": "Type and filename are required"
            }), 400
        
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error getting report file: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/download', methods=['GET'])
def download_report():
    """Download report file"""
    try:
        report_type = request.args.get('type', '')
        filename = request.args.get('filename', '')
        
        if not report_type or not filename:
            return jsonify({
                "success": False,
                "error": "Type and filename are required"
            }), 400
        
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading report: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# HTML Page Route
@report_bp.route('/page', methods=['GET'])
def report_page():
    """Render report center page"""
    return render_template('reports.html')
