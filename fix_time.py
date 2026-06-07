"""修复时间字段"""
fp = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\services\smart_report_service.py'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换时间字段切片
content = content.replace("d.get('event_time','')[:16]", "self._fmt_time(d.get('event_time'))")
content = content.replace("n.get('publish_time','')[:16]", "self._fmt_time(n.get('publish_time'))")
content = content.replace("z.get('trade_date','')", "self._fmt_time(z.get('trade_date'), 10)")
content = content.replace("str(z.get('zt_time',''))[:8]", "self._fmt_time(z.get('zt_time'), 8)")
content = content.replace("n.get('notice_date','')", "self._fmt_time(n.get('notice_date'), 10)")

with open(fp, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done - replacements applied')
