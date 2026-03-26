#!/usr/bin/env python3
"""
测试涨停炸板数据启动
"""
import sys
from pathlib import Path

# 添加项目根目录到路径 - 修正路径
project_root = Path(r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, str(project_root))

print(f"Project root: {project_root}")
print(f"Python path: {sys.path[:2]}")

# 测试导入
try:
    from gs2026.dashboard.services.process_manager import ProcessManager
    print("[OK] ProcessManager imported successfully")
    
    pm = ProcessManager()
    print(f"[OK] ProcessManager initialized")
    print(f"   - monitor_dir: {pm.monitor_dir}")
    print(f"   - project_root: {pm.project_root}")
    
    # 测试脚本路径
    script_name = 'zt_collection.py'
    script_path = project_root / "src" / "gs2026" / "collection" / "base" / script_name
    print(f"\nScript path check:")
    print(f"   - Path: {script_path}")
    print(f"   - Exists: {script_path.exists()}")
    
    # 测试启动
    print(f"\nTesting start_collection_service...")
    result = pm.start_collection_service(
        service_id='zt_zb',
        script_name='zt_collection.py',
        function_name='collect_zt_zb_collection',
        params={'start_date': '2026-03-26', 'end_date': '2026-03-26'}
    )
    print(f"Result: {result}")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
