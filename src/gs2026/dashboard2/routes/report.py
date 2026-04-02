"""
Report Center Routes - File system based report management
"""
from flask import Blueprint, jsonify, request, send_file, render_template
from pathlib import Path
import logging
import hashlib

from ..services.report_service import ReportService
from ..services.pdf_reader import PDFReaderService
from ..services.tts_service import TTSService

logger = logging.getLogger(__name__)

# Create blueprint
report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# Initialize services
report_service = ReportService()
pdf_reader = PDFReaderService()
tts_service = TTSService()


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


# ========== Reading & TTS APIs ==========

@report_bp.route('/<report_type>/<filename>/content', methods=['GET'])
def get_report_content(report_type, filename):
    """Get report text content for reading"""
    try:
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        # Extract text from PDF
        segments = pdf_reader.extract_and_cache(file_path)
        
        if not segments:
            return jsonify({
                "success": False,
                "error": "Failed to extract text from PDF"
            }), 500
        
        return jsonify({
            "success": True,
            "data": {
                "report_type": report_type,
                "filename": filename,
                "total_segments": len(segments),
                "segments": segments
            }
        })
    except Exception as e:
        logger.error(f"Error getting report content: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/<report_type>/<filename>/tts/prepare', methods=['POST'])
def prepare_tts(report_type, filename):
    """Prepare TTS audio for all segments"""
    try:
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        # Get request params
        data = request.get_json() or {}
        voice = data.get('voice', 'xiaoxiao')
        speed = data.get('speed', 1.0)
        
        # Get segments
        segments = pdf_reader.extract_and_cache(file_path)
        
        if not segments:
            return jsonify({
                "success": False,
                "error": "No text content available"
            }), 500
        
        # Generate TTS for each segment
        results = tts_service.generate_for_segments(segments, voice, speed)
        
        return jsonify({
            "success": True,
            "data": {
                "total_segments": len(results),
                "segments": results
            }
        })
    except Exception as e:
        logger.error(f"Error preparing TTS: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/tts/audio', methods=['GET'])
def get_tts_audio():
    """Get TTS audio file (generate if not exists)"""
    try:
        text_hash = request.args.get('text', '')
        voice = request.args.get('voice', 'xiaoxiao')
        speed = request.args.get('speed', '1.0')
        
        if not text_hash:
            return jsonify({
                "success": False,
                "error": "Text hash is required"
            }), 400
        
        # Try to get existing audio
        audio_path = tts_service.get_audio_file(text_hash, voice)
        
        # If not found, we need to find the text and generate
        if not audio_path or not audio_path.exists():
            # Return 202 Accepted to indicate generation in progress
            # Client should retry
            return jsonify({
                "success": False,
                "error": "Audio not ready",
                "retry": True
            }), 202
        
        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=False
        )
    except Exception as e:
        logger.error(f"Error getting TTS audio: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/tts/generate', methods=['POST'])
def generate_tts():
    """Generate TTS audio on demand"""
    try:
        data = request.get_json() or {}
        text = data.get('text', '')
        voice = data.get('voice', 'xiaoxiao')
        speed = data.get('speed', 1.0)
        
        if not text:
            return jsonify({
                "success": False,
                "error": "Text is required"
            }), 400
        
        # Generate audio
        info = tts_service.ensure_audio(text, voice, speed)
        
        if not info:
            return jsonify({
                "success": False,
                "error": "Failed to generate audio"
            }), 500
        
        return jsonify({
            "success": True,
            "data": {
                "audio_url": f"/api/reports/tts/audio?text={hashlib.md5(text.encode()).hexdigest()}&voice={voice}",
                "duration": info.get("duration", 0)
            }
        })
    except Exception as e:
        logger.error(f"Error generating TTS: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
