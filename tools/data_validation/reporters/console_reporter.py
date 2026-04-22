"""控制台报告生成器"""
from typing import List
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ValidationReport, FixReport


class ConsoleReporter:
    """控制台报告生成器"""
    
    def generate(self, reports: List[ValidationReport]):
        """生成控制台报告"""
        print("\n" + "=" * 80)
        print("数据质量验证报告".center(80))
        print("=" * 80)
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        total_records = 0
        total_invalid = 0
        
        for report in reports:
            self._print_single_report(report)
            total_records += report.total_records
            total_invalid += report.invalid_count
        
        # 汇总
        print("\n" + "=" * 80)
        print("汇总".center(80))
        print("=" * 80)
        print(f"总记录数: {total_records}")
        print(f"异常记录数: {total_invalid}")
        if total_records > 0:
            print(f"异常率: {total_invalid / total_records * 100:.2f}%")
        print("=" * 80)
    
    def _print_single_report(self, report: ValidationReport):
        """打印单个报告"""
        print(f"\n【{report.validator_type}】")
        print(f"  日期范围: {report.start_date} ~ {report.end_date}")
        print(f"  总记录数: {report.total_records}")
        print(f"  异常记录数: {report.invalid_count}")
        if report.total_records > 0:
            print(f"  异常率: {report.invalid_rate:.2f}%")
        print(f"  耗时: {report.duration_seconds:.2f}秒")
        
        if report.invalid_records:
            print(f"\n  异常详情 (前10条):")
            for i, record in enumerate(report.invalid_records[:10], 1):
                print(f"    {i}. {record.content_hash[:16]}...")
                for error in record.errors:
                    print(f"       - {error}")
            
            if len(report.invalid_records) > 10:
                print(f"    ... 还有 {len(report.invalid_records) - 10} 条异常记录")
    
    def generate_fix_report(self, fix_report: FixReport):
        """生成修复报告"""
        print("\n" + "=" * 80)
        print("数据清理报告".center(80))
        print("=" * 80)
        
        report = fix_report.validation_report
        print(f"\n验证类型: {report.validator_type}")
        print(f"日期范围: {report.start_date} ~ {report.end_date}")
        print(f"异常记录总数: {report.invalid_count}")
        
        print("\n清理结果:")
        print(f"  删除分析表记录: {fix_report.deleted_mysql}")
        print(f"  清理Redis缓存: {fix_report.deleted_redis}")
        print(f"  标记源表重跑: {fix_report.marked_source}")
        
        if fix_report.errors:
            print(f"\n清理失败: {len(fix_report.errors)} 条")
            for error in fix_report.errors[:5]:
                print(f"  - {error}")
        
        print("=" * 80)
