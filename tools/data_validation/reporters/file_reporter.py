"""文件报告生成器"""
import json
import os
from typing import List
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ValidationReport, FixReport


class FileReporter:
    """文件报告生成器"""
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate(self, reports: List[ValidationReport]):
        """生成文件报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # JSON报告
        json_file = os.path.join(self.output_dir, f"validation_report_{timestamp}.json")
        self._generate_json(reports, json_file)
        
        # Markdown报告
        md_file = os.path.join(self.output_dir, f"validation_report_{timestamp}.md")
        self._generate_markdown(reports, md_file)
        
        print(f"\n报告已保存:")
        print(f"  - {json_file}")
        print(f"  - {md_file}")
        
        return json_file, md_file
    
    def _generate_json(self, reports: List[ValidationReport], filepath: str):
        """生成JSON报告"""
        data = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_records": sum(r.total_records for r in reports),
                "total_invalid": sum(r.invalid_count for r in reports),
            },
            "reports": []
        }
        
        for report in reports:
            data["reports"].append({
                "validator_type": report.validator_type,
                "start_date": report.start_date,
                "end_date": report.end_date,
                "total_records": report.total_records,
                "invalid_count": report.invalid_count,
                "invalid_rate": report.invalid_rate,
                "duration_seconds": report.duration_seconds,
                "invalid_records": [
                    {
                        "content_hash": r.content_hash,
                        "table_name": r.table_name,
                        "source_table": r.source_table,
                        "errors": r.errors,
                        "raw_data": r.raw_data
                    }
                    for r in report.invalid_records
                ]
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _generate_markdown(self, reports: List[ValidationReport], filepath: str):
        """生成Markdown报告"""
        lines = [
            "# 数据质量验证报告",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 汇总",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总记录数 | {sum(r.total_records for r in reports)} |",
            f"| 异常记录数 | {sum(r.invalid_count for r in reports)} |",
            f"| 异常率 | {sum(r.invalid_count for r in reports) / max(sum(r.total_records for r in reports), 1) * 100:.2f}% |",
            "",
        ]
        
        for report in reports:
            lines.extend([
                f"## {report.validator_type}",
                "",
                f"- 日期范围: {report.start_date} ~ {report.end_date}",
                f"- 总记录数: {report.total_records}",
                f"- 异常记录数: {report.invalid_count}",
                f"- 异常率: {report.invalid_rate:.2f}%",
                f"- 耗时: {report.duration_seconds:.2f}秒",
                "",
            ])
            
            if report.invalid_records:
                lines.extend([
                    "### 异常详情",
                    "",
                    "| 序号 | content_hash | 错误描述 |",
                    "|------|--------------|----------|",
                ])
                
                for i, record in enumerate(report.invalid_records[:50], 1):
                    errors = "; ".join(record.errors)
                    if len(errors) > 100:
                        errors = errors[:100] + "..."
                    lines.append(f"| {i} | `{record.content_hash[:16]}...` | {errors} |")
                
                if len(report.invalid_records) > 50:
                    lines.append(f"| ... | ... | 还有 {len(report.invalid_records) - 50} 条记录 |")
                
                lines.append("")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
