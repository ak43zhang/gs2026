"""
Markdown 导出器
"""
from pathlib import Path
from typing import Dict, Any

from .base import ReportExporter, ExporterFactory


@ExporterFactory.register
class MarkdownExporter(ReportExporter):
    """Markdown 导出器"""
    
    format = 'md'
    
    def export(self, data: Dict[str, Any], output_path: Path) -> Path:
        """导出 Markdown"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建 Markdown 内容
        lines = []
        
        # 标题
        title = data.get('title', '报告')
        lines.append(f'# {title}')
        lines.append('')
        
        # 日期
        report_date = data.get('date', '')
        lines.append(f'**日期**: {report_date}')
        lines.append('')
        lines.append('---')
        lines.append('')
        
        # 内容
        content = data.get('content', [])
        for item in content:
            item_type = item.get('type', 'text')
            
            if item_type == 'heading':
                lines.append(f'## {item.get("text", "")}')
                lines.append('')
            
            elif item_type == 'text':
                lines.append(item.get('text', ''))
                lines.append('')
            
            elif item_type == 'table':
                table_data = item.get('data', [])
                if table_data:
                    # 表头
                    header = table_data[0]
                    lines.append('| ' + ' | '.join(str(cell) for cell in header) + ' |')
                    lines.append('| ' + ' | '.join(['---'] * len(header)) + ' |')
                    
                    # 数据行
                    for row in table_data[1:]:
                        lines.append('| ' + ' | '.join(str(cell) for cell in row) + ' |')
                    
                    lines.append('')
            
            elif item_type == 'page_break':
                lines.append('<div style="page-break-after: always;"></div>')
                lines.append('')
        
        # 写入文件
        output_path.write_text('\n'.join(lines), encoding='utf-8')
        
        return output_path
    
    def extract_text(self, file_path: Path) -> str:
        """提取纯文本"""
        content = file_path.read_text(encoding='utf-8')
        # 简单移除 Markdown 标记
        import re
        text = re.sub(r'#+ ', '', content)  # 标题
        text = re.sub(r'\*\*', '', text)     # 粗体
        text = re.sub(r'\*', '', text)       # 斜体
        text = re.sub(r'\|', ' ', text)      # 表格
        text = re.sub(r'---+', '', text)     # 分隔线
        return text
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """获取文件信息"""
        info = super().get_file_info(file_path)
        # 估算行数
        content = file_path.read_text(encoding='utf-8')
        info['page_count'] = len(content.split('\n')) // 40  # 假设每页40行
        return info
