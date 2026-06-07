"""测试智能报告生成"""
from gs2026.dashboard2.services.smart_report_service import SmartReportService

service = SmartReportService()
result = service.generate_report('2026-06-05')

print(f"success: {result['success']}")
print(f"path: {result['path']}")
print(f"stats: {result['stats']}")
print(f"headlines: {result['headline_count']}")
