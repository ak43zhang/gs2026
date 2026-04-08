"""
Report Center Routes - File system based report management
"""
from flask import Blueprint, jsonify, request, send_file, render_template
from pathlib import Path
import logging
import hashlib

from ..services.report_service import ReportService
from ..services.document_reader import DocumentReaderFactory, PDFReaderService
from ..services.tts_service import TTSService

logger = logging.getLogger(__name__)

# Create blueprint
report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# Initialize services
report_service = ReportService()
doc_reader_factory = DocumentReaderFactory()
pdf_reader = PDFReaderService()  # 向后兼容
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
        
        # 根据文件类型设置mimetype
        file_ext = file_path.suffix.lower()
        mimetype_map = {
            '.pdf': 'application/pdf',
            '.epub': 'application/epub+zip',
        }
        mimetype = mimetype_map.get(file_ext, 'application/octet-stream')
        
        return send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading report: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@report_bp.route('/<report_type>/<filename>/preview', methods=['GET'])
def preview_epub(report_type, filename):
    """Preview EPUB content as HTML with image support"""
    try:
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        # 检查文件类型
        if file_path.suffix.lower() != '.epub':
            return jsonify({
                "success": False,
                "error": "Only EPUB files support preview"
            }), 400
        
        # 获取章节参数
        chapter = request.args.get('chapter', '1')
        try:
            chapter_num = int(chapter)
        except ValueError:
            chapter_num = 1
        
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
            import base64
        except ImportError:
            return jsonify({
                "success": False,
                "error": "ebooklib or beautifulsoup4 not available"
            }), 500
        
        book = epub.read_epub(str(file_path))
        
        # 收集所有文档章节和图片
        chapters = []
        images = {}  # 存储图片数据 {filename: base64_data}
        
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                chapters.append(item)
            elif item.get_type() == ebooklib.ITEM_IMAGE:
                # 提取图片并转为base64
                try:
                    image_name = item.get_name()
                    image_content = item.get_content()
                    # 检测图片类型
                    content_type = 'image/jpeg'
                    if image_name.lower().endswith('.png'):
                        content_type = 'image/png'
                    elif image_name.lower().endswith('.gif'):
                        content_type = 'image/gif'
                    elif image_name.lower().endswith('.svg'):
                        content_type = 'image/svg+xml'
                    
                    base64_data = base64.b64encode(image_content).decode('utf-8')
                    images[image_name] = f'data:{content_type};base64,{base64_data}'
                except Exception as e:
                    logger.warning(f"Failed to process image {item.get_name()}: {e}")
        
        if not chapters:
            return jsonify({
                "success": False,
                "error": "No chapters found in EPUB"
            }), 500
        
        # 获取指定章节
        if chapter_num < 1 or chapter_num > len(chapters):
            chapter_num = 1
        
        current_chapter = chapters[chapter_num - 1]
        soup = BeautifulSoup(current_chapter.get_content(), 'html.parser')
        
        # 提取标题
        title = ""
        title_tag = soup.find(['h1', 'h2', 'title'])
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # 处理图片：将src替换为base64数据
        for img in soup.find_all('img'):
            src = img.get('src', '')
            # 处理相对路径
            for img_name, img_data in images.items():
                if src in img_name or img_name.endswith(src):
                    img['src'] = img_data
                    break
        
        # 清理不必要的标签和属性，保留基本结构
        for tag in soup.find_all(['script', 'style']):
            tag.decompose()
        
        # 获取处理后的HTML内容
        body_content = soup.find('body')
        if body_content:
            content_html = str(body_content.decode_contents())
        else:
            content_html = str(soup)
        
        # 渲染预览模板
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title or 'EPUB Preview'}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
                    line-height: 1.8;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 40px 20px;
                    background: #fafafa;
                    color: #333;
                }}
                .chapter-nav {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 15px 20px;
                    background: #fff;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .chapter-nav a {{
                    color: #1890ff;
                    text-decoration: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    transition: background 0.2s;
                }}
                .chapter-nav a:hover {{
                    background: #e6f7ff;
                }}
                .chapter-nav a.disabled {{
                    color: #999;
                    pointer-events: none;
                }}
                .chapter-info {{
                    font-size: 14px;
                    color: #666;
                }}
                .content {{
                    background: #fff;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    word-wrap: break-word;
                }}
                .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {{
                    color: #1a1a1a;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                }}
                .content h1 {{ font-size: 1.8em; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }}
                .content h2 {{ font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
                .content h3 {{ font-size: 1.3em; }}
                .content p {{
                    margin: 1em 0;
                    text-align: justify;
                }}
                .content img {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 20px auto;
                    border-radius: 4px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .content figure {{
                    margin: 20px 0;
                    text-align: center;
                }}
                .content figcaption {{
                    font-size: 0.9em;
                    color: #666;
                    margin-top: 8px;
                }}
                .content table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                .content th, .content td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                .content th {{
                    background: #f5f5f5;
                    font-weight: 600;
                }}
                .content blockquote {{
                    border-left: 4px solid #1890ff;
                    margin: 20px 0;
                    padding: 10px 20px;
                    background: #f6ffed;
                    color: #666;
                }}
                .content ul, .content ol {{
                    margin: 1em 0;
                    padding-left: 2em;
                }}
                .content li {{
                    margin: 0.5em 0;
                }}
                .file-info {{
                    text-align: center;
                    padding: 20px;
                    color: #999;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="chapter-nav">
                <a href="/api/reports/{report_type}/{filename}/preview?chapter={chapter_num - 1}" 
                   class="{'disabled' if chapter_num <= 1 else ''}">← 上一章</a>
                <span class="chapter-info">第 {chapter_num} / {len(chapters)} 章</span>
                <a href="/api/reports/{report_type}/{filename}/preview?chapter={chapter_num + 1}" 
                   class="{'disabled' if chapter_num >= len(chapters) else ''}">下一章 →</a>
            </div>
            <div class="content">
                {content_html}
            </div>
            <div class="file-info">
                {filename} | EPUB电子书预览 | 共 {len(images)} 张图片
            </div>
        </body>
        </html>
        """
        
        from flask import Response
        return Response(html_content, mimetype='text/html')
        
    except Exception as e:
        logger.error(f"Error previewing EPUB: {e}")
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
    """Get report text content for reading with segmentation strategy
    
    支持PDF、EPUB等多种文档格式
    """
    try:
        file_path = report_service.get_report_file_path(report_type, filename)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        # Get segmentation strategy from query param
        strategy = request.args.get('strategy', 'smart')
        valid_strategies = ['original', 'line', 'smart', 'strict_line']
        if strategy not in valid_strategies:
            strategy = 'smart'
        
        # 使用文档阅读器工厂获取合适的阅读器
        reader = doc_reader_factory.get_reader(file_path)
        
        if not reader:
            # 尝试使用PDF阅读器（向后兼容）
            if file_path.suffix.lower() == '.pdf':
                segments = pdf_reader.extract_text(file_path, strategy)
            else:
                return jsonify({
                    "success": False,
                    "error": f"Unsupported file format: {file_path.suffix}"
                }), 400
        else:
            # 使用对应的阅读器提取文本
            segments = reader.extract_text(file_path, strategy)
        
        if not segments:
            return jsonify({
                "success": False,
                "error": "Failed to extract text from document"
            }), 500
        
        return jsonify({
            "success": True,
            "data": {
                "report_type": report_type,
                "filename": filename,
                "strategy": strategy,
                "total_segments": len(segments),
                "segments": segments
            }
        })
    except Exception as e:
        logger.error(f"Error getting report content: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": f"{str(e)}\n{traceback.format_exc()}"
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
        strategy = data.get('strategy', 'smart')  # 获取策略参数
        pregenerate = data.get('pregenerate', True)  # 默认预生成音频
        
        # Validate strategy
        valid_strategies = ['original', 'line', 'smart', 'strict_line']
        if strategy not in valid_strategies:
            strategy = 'smart'
        
        # Get segments with specified strategy (must match frontend)
        logger.info(f"Extracting text from {file_path} with strategy={strategy}")
        try:
            segments = pdf_reader.extract_text(file_path, strategy)
            logger.info(f"Extracted {len(segments)} segments")
        except Exception as extract_error:
            logger.error(f"Failed to extract text: {extract_error}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({
                "success": False,
                "error": f"Failed to extract text: {str(extract_error)}"
            }), 500
        
        if not segments:
            logger.error(f"No segments extracted from {file_path}")
            return jsonify({
                "success": False,
                "error": "No text content available"
            }), 500
        
        logger.info(f"Preparing TTS for {len(segments)} segments, pregenerate={pregenerate}")
        
        # Generate TTS for each segment using PDF-independent caching
        # 使用PDF独立缓存，确保每个PDF的音频是独立的
        results = tts_service.generate_for_pdf(file_path, segments, voice, speed, pregenerate=pregenerate)
        
        # Build index-based mapping for frontend
        index_map = {}
        ready_count = 0
        for i, segment in enumerate(segments):
            seg_key = str(i)
            if seg_key in results:
                index_map[seg_key] = results[seg_key]
                if results[seg_key].get('ready'):
                    ready_count += 1
        
        logger.info(f"TTS prepare complete: {ready_count}/{len(segments)} segments ready")
        
        return jsonify({
            "success": True,
            "data": {
                "total_segments": len(results),
                "ready_segments": ready_count,
                "segments": results,
                "index_map": index_map  # Frontend can use this for reliable matching
            }
        })
    except Exception as e:
        logger.error(f"Error preparing TTS: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": f"{str(e)}\n{traceback.format_exc()}"
        }), 500


@report_bp.route('/tts/audio', methods=['GET'])
def get_tts_audio():
    """Get TTS audio file (generate if not exists)
    
    支持两种模式：
    1. 传统模式：?text=<hash>&voice=<voice> - 基于文本哈希查找
    2. PDF独立模式：?pdf=<pdf_hash>&seg=<segment_index>&voice=<voice> - 基于PDF和分段索引查找
    """
    try:
        # 检查是否是PDF独立模式
        pdf_hash = request.args.get('pdf', '')
        segment_index = request.args.get('seg', '')
        voice = request.args.get('voice', 'xiaoxiao')
        speed = float(request.args.get('speed', '1.0'))
        
        # PDF独立模式
        if pdf_hash and segment_index:
            segment_index = int(segment_index)
            audio_path = tts_service.get_pdf_audio_file(pdf_hash, segment_index, voice)
            
            if audio_path and audio_path.exists():
                return send_file(
                    audio_path,
                    mimetype='audio/mpeg',
                    as_attachment=False
                )
            else:
                return jsonify({
                    "success": False,
                    "error": "Audio not found for this PDF segment",
                    "retry": True
                }), 202
        
        # 传统模式（向后兼容）
        text_hash = request.args.get('text', '')
        
        if not text_hash:
            return jsonify({
                "success": False,
                "error": "Text hash or PDF info is required"
            }), 400
        
        # Try to get existing audio
        audio_path = tts_service.get_audio_file(text_hash, voice)
        
        # If not found, try to generate on-the-fly
        if not audio_path or not audio_path.exists():
            logger.info(f"Audio not found for hash {text_hash}, attempting to generate")
            
            # Find the original text
            text = tts_service.get_text_by_hash(text_hash)
            
            if text:
                # Generate audio
                info = tts_service.generate(text, voice, speed)
                if info:
                    audio_path = Path(info.get("audio_path", ""))
                    logger.info(f"Generated audio on-the-fly for: {text[:30]}...")
                else:
                    return jsonify({
                        "success": False,
                        "error": "Failed to generate audio"
                    }), 500
            else:
                # Text not found, cannot generate
                return jsonify({
                    "success": False,
                    "error": "Audio not ready and text not found",
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
