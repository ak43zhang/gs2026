"""
涨停报告生成器
"""
from datetime import date
from pathlib import Path
from typing import Dict, Any, List
import sys

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..base import ReportGenerator
from ..exporters import ExporterFactory


class ZTReportGenerator(ReportGenerator):
    """涨停报告生成器"""
    
    report_type = 'zt_report'
    report_name = '涨停报告'
    
    def generate(self, report_date: date, output_format: str = 'pdf', 
                 params: Dict = None) -> Dict[str, Any]:
        """
        生成涨停报告
        
        Args:
            report_date: 报告日期
            output_format: 输出格式
            params: 额外参数
        
        Returns:
            dict: 生成结果
        """
        params = params or {}
        
        # 获取数据
        data = self._fetch_data(report_date, params)
        
        # 构建报告数据
        report_data = {
            'id': f'zt_{report_date.strftime("%Y%m%d")}',
            'title': f'涨停报告_{report_date.strftime("%Y%m%d")}',
            'date': report_date.strftime('%Y-%m-%d'),
            'type': self.report_type,
            'content': self._build_content(data)
        }
        
        # 获取导出器
        exporter = ExporterFactory.get_exporter(output_format)
        
        # 构建输出路径
        output_dir = Path(project_root) / 'output' / 'zt_report' / report_date.strftime('%Y/%m')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f'涨停报告_{report_date.strftime("%Y%m%d")}.{output_format}'
        output_path = output_dir / filename
        
        # 导出文件
        exporter.export(report_data, output_path)
        
        # 获取文件信息
        file_info = exporter.get_file_info(output_path)
        
        # 提取文本（用于语音播报）
        content_text = exporter.extract_text(output_path)
        
        return {
            'file_path': str(output_path.relative_to(Path(project_root) / 'output')),
            'file_size': file_info['file_size'],
            'page_count': file_info['page_count'],
            'content_text': content_text,
            'data': report_data
        }
    
    def _fetch_data(self, report_date: date, params: Dict) -> Dict[str, Any]:
        """获取涨停数据"""
        # TODO: 从数据库获取真实数据
        # 这里使用模拟数据
        
        # 模拟涨停股票数据
        zt_stocks = [
            {'code': '000001', 'name': '平安银行', 'price': 12.50, 'change': 10.00, 'reason': '金融板块走强'},
            {'code': '000002', 'name': '万科A', 'price': 18.30, 'change': 10.02, 'reason': '房地产政策利好'},
            {'code': '600519', 'name': '贵州茅台', 'price': 1680.00, 'change': 10.00, 'reason': '白酒消费复苏'},
            {'code': '000858', 'name': '五粮液', 'price': 158.50, 'change': 10.01, 'reason': '白酒消费复苏'},
            {'code': '002594', 'name': '比亚迪', 'price': 268.50, 'change': 10.00, 'reason': '新能源汽车销量增长'},
        ]
        
        # 按行业统计
        industry_stats = {
            '金融': 2,
            '房地产': 1,
            '白酒': 2,
            '新能源汽车': 1
        }
        
        return {
            'date': report_date.strftime('%Y-%m-%d'),
            'total_zt': len(zt_stocks),
            'zt_stocks': zt_stocks,
            'industry_stats': industry_stats
        }
    
    def _build_content(self, data: Dict) -> List[Dict]:
        """构建报告内容"""
        content = []
        
        # 概览
        content.append({
            'type': 'heading',
            'text': '一、涨停概览'
        })
        content.append({
            'type': 'text',
            'text': f'今日（{data["date"]}）共有 {data["total_zt"]} 只股票涨停。'
        })
        
        # 行业分布
        content.append({
            'type': 'heading',
            'text': '二、行业分布'
        })
        
        industry_data = [['行业', '涨停数量']]
        for industry, count in data['industry_stats'].items():
            industry_data.append([industry, str(count)])
        
        content.append({
            'type': 'table',
            'data': industry_data
        })
        
        content.append({
            'type': 'text',
            'text': '从行业分布来看，金融和白酒板块表现较为活跃。'
        })
        
        # 涨停明细
        content.append({
            'type': 'heading',
            'text': '三、涨停明细'
        })
        
        stocks_data = [['股票代码', '股票名称', '涨停价', '涨幅', '涨停原因']]
        for stock in data['zt_stocks']:
            stocks_data.append([
                stock['code'],
                stock['name'],
                f"{stock['price']:.2f}",
                f"{stock['change']:.2f}%",
                stock['reason']
            ])
        
        content.append({
            'type': 'table',
            'data': stocks_data
        })
        
        # 分析总结
        content.append({
            'type': 'heading',
            'text': '四、分析总结'
        })
        content.append({
            'type': 'text',
            'text': '今日市场整体表现活跃，涨停股票主要集中在金融、白酒和新能源汽车板块。建议关注政策利好驱动的房地产板块以及消费复苏相关的白酒板块。'
        })
        
        return content
    
    def get_report_name(self, report_date: date) -> str:
        """获取报告名称"""
        return f'涨停报告_{report_date.strftime("%Y%m%d")}'
