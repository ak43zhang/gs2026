"""修复剩余8个文件的 create_engine"""
import os, re, sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src\gs2026\tools")
from batch_fix_engine import modify_file

files = [
    r"F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\combine_collection.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\combine_ztb_area.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\collection\base\baostock_collection.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\collection\base\baostock_collection_v2.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\collection\base\base_collection.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\collection\base\bk_gn_collection.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\tools\migrate_analysis_news.py",
    r"F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\trading_day_util.py",
]

for f in files:
    name = os.path.basename(f)
    print(f"\n[{name}]")
    try:
        result = modify_file(f)
        if result:
            print(f"  ✓ 修改成功")
        else:
            print(f"  - 跳过")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
