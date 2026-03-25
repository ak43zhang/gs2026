"""
测试新的包装脚本生成
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

from gs2026.dashboard.services.process_manager import ProcessManager

pm = ProcessManager()

# 生成财联社包装脚本
config = {
    'file': 'deepseek_analysis_news_cls.py',
    'name': '财联社新闻分析',
    'params': [
        {'name': 'polling_time', 'type': 'number', 'label': '轮询间隔(秒)', 'default': 10},
        {'name': 'year', 'type': 'text', 'label': '年份', 'default': '2026'}
    ]
}
params = {'polling_time': 5, 'year': '2026'}

wrapper = pm._generate_analysis_wrapper('news_cls', config, params)
print("生成的包装脚本:")
print("=" * 60)
print(wrapper)
print("=" * 60)

# 保存并运行测试
temp_path = pm.project_root / "temp" / "test_news_cls_wrapper_v2.py"
temp_path.write_text(wrapper, encoding='utf-8')
print(f"\n已保存到: {temp_path}")
print("\n手动运行测试:")
print(f"  python {temp_path}")
