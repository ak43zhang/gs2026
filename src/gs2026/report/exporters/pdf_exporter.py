"""
PDF 导出器
使用 reportlab
"""
from pathlib import Path
from typing import Dict, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from .base import ReportExporter, ExporterFactory


# 注册中文字体
try:
    pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttc'))
    pdfmetrics.registerFont(TTFont('SimHei', 'simhei.ttf'))
except:
    # 如果系统没有这些字体，使用默认字体
    pass


@ExporterFactory.register
class PDFExporter(ReportExporter):
    """PDF 导出器"""
    
    format = 'pdf'
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        # 添加中文样式
        self.styles.add(ParagraphStyle(
            name='ChineseTitle',
            fontName='SimHei',
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=30
        ))
        self.styles.add(ParagraphStyle(
            name='ChineseHeading',
            fontName='SimHei',
            fontSize=14,
            alignment=TA_LEFT,
            spaceAfter=12,
            spaceBefore=12
        ))
        self.styles.add(ParagraphStyle(
            name='ChineseBody',
            fontName='SimSun',
            fontSize=10,
            alignment=TA_LEFT,
            spaceAfter=6
        ))
    
    def export(self, data: Dict[str, Any], output_path: Path) -> Path:
        """导出 PDF"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建 PDF 文档
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # 构建内容
        story = []
        
        # 标题
        title = data.get('title', '报告')
        story.append(Paragraph(title, self.styles['ChineseTitle']))
        story.append(Spacer(1, 0.5*cm))
        
        # 日期
        report_date = data.get('date', '')
        story.append(Paragraph(f'日期: {report_date}', self.styles['ChineseBody']))
        story.append(Spacer(1, 1*cm))
        
        # 内容
        content = data.get('content', [])
        for item in content:
            item_type = item.get('type', 'text')
            
            if item_type == 'heading':
                story.append(Paragraph(item.get('text', ''), self.styles['ChineseHeading']))
            
            elif item_type == 'text':
                story.append(Paragraph(item.get('text', ''), self.styles['ChineseBody']))
            
            elif item_type == 'table':
                table_data = item.get('data', [])
                if table_data:
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'SimHei'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 0.5*cm))
            
            elif item_type == 'page_break':
                story.append(PageBreak())
        
        # 生成 PDF
        doc.build(story)
        
        return output_path
    
    def extract_text(self, file_path: Path) -> str:
        """从 PDF 提取文本"""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(file_path))
            text = []
            for page in reader.pages:
                text.append(page.extract_text())
            return '\n'.join(text)
        except Exception as e:
            print(f'提取 PDF 文本失败: {e}')
            return ''
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """获取文件信息"""
        info = super().get_file_info(file_path)
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(file_path))
            info['page_count'] = len(reader.pages)
        except:
            pass
        return info
