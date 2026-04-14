"""
EPUB 导出器
使用 ebooklib
"""
from pathlib import Path
from typing import Dict, Any
from ebooklib import epub

from .base import ReportExporter, ExporterFactory


@ExporterFactory.register
class EPUBExporter(ReportExporter):
    """EPUB 导出器"""
    
    format = 'epub'
    
    def export(self, data: Dict[str, Any], output_path: Path) -> Path:
        """导出 EPUB"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建 EPUB 书籍
        book = epub.EpubBook()
        
        # 设置元数据
        book.set_identifier(f"report_{data.get('id', 'unknown')}")
        book.set_title(data.get('title', '报告'))
        book.set_language('zh-CN')
        
        # 添加作者
        book.add_author('GS2026')
        
        # 构建内容 HTML
        content_html = self._build_html_content(data)
        
        # 创建章节
        chapter = epub.EpubHtml(title='正文', file_name='content.xhtml')
        chapter.content = content_html
        book.add_item(chapter)
        
        # 添加 CSS 样式
        style = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=self._get_css()
        )
        book.add_item(style)
        
        # 添加导航
        book.toc = (epub.Link('content.xhtml', '正文', 'content'),)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 定义 spine
        book.spine = ['nav', chapter]
        
        # 写入文件
        epub.write_epub(str(output_path), book)
        
        return output_path
    
    def _build_html_content(self, data: Dict[str, Any]) -> str:
        """构建 HTML 内容"""
        html_parts = [
            '<html xmlns="http://www.w3.org/1999/xhtml">',
            '<head>',
            '<meta charset="utf-8"/>',
            '<link rel="stylesheet" type="text/css" href="style.css"/>',
            '</head>',
            '<body>',
            f'<h1>{data.get("title", "报告")}</h1>',
            f'<p class="date">日期: {data.get("date", "")}</p>',
            '<hr/>'
        ]
        
        # 内容
        content = data.get('content', [])
        for item in content:
            item_type = item.get('type', 'text')
            
            if item_type == 'heading':
                html_parts.append(f'<h2>{item.get("text", "")}</h2>')
            
            elif item_type == 'text':
                html_parts.append(f'<p>{item.get("text", "")}</p>')
            
            elif item_type == 'table':
                table_data = item.get('data', [])
                if table_data:
                    html_parts.append('<table>')
                    for i, row in enumerate(table_data):
                        html_parts.append('<tr>')
                        tag = 'th' if i == 0 else 'td'
                        for cell in row:
                            html_parts.append(f'<{tag}>{cell}</{tag}>')
                        html_parts.append('</tr>')
                    html_parts.append('</table>')
            
            elif item_type == 'page_break':
                html_parts.append('<div class="page-break"></div>')
        
        html_parts.extend(['</body>', '</html>'])
        
        return '\n'.join(html_parts)
    
    def _get_css(self) -> str:
        """获取 CSS 样式"""
        return '''
        body {
            font-family: "SimSun", serif;
            line-height: 1.6;
            padding: 20px;
        }
        h1 {
            font-family: "SimHei", sans-serif;
            text-align: center;
            font-size: 24px;
            margin-bottom: 10px;
        }
        h2 {
            font-family: "SimHei", sans-serif;
            font-size: 18px;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        .date {
            text-align: center;
            color: #666;
            margin-bottom: 20px;
        }
        p {
            text-indent: 2em;
            margin-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        .page-break {
            page-break-after: always;
        }
        '''
    
    def extract_text(self, file_path: Path) -> str:
        """从 EPUB 提取文本"""
        try:
            from bs4 import BeautifulSoup
            from ebooklib import ITEM_DOCUMENT
            book = epub.read_epub(str(file_path))
            texts = []
            
            for item in book.get_items():
                if item.get_type() == ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    texts.append(soup.get_text())
            
            return '\n'.join(texts)
        except Exception as e:
            print(f'提取 EPUB 文本失败: {e}')
            return ''
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """获取文件信息"""
        info = super().get_file_info(file_path)
        # EPUB 页数难以准确统计，返回章节数
        try:
            from ebooklib import ITEM_DOCUMENT
            book = epub.read_epub(str(file_path))
            info['page_count'] = len(list(book.get_items_of_type(ITEM_DOCUMENT)))
        except:
            pass
        return info
