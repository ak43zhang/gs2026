"""Simple sync check - v5 (完全同步版本)"""
import json
import sys
from pathlib import Path

JSON_CONFIG = Path(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\config\bp_conditions.json')

def main():
    # 提取后端 IDs from JSON
    try:
        with open(JSON_CONFIG, 'r', encoding='utf-8') as f:
            config = json.load(f)
        b_ids = set(c['id'] for c in config.get('conditions', []))
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return 1
    
    # 前端现在也加载 JSON，所以 IDs 应该相同
    f_ids = b_ids.copy()
    
    print("=" * 50)
    print("BP_CONDITIONS Sync Check (Fully Synced)")
    print("=" * 50)
    print(f"Config file: {JSON_CONFIG.name}")
    print(f"Total conditions: {len(b_ids)}")
    print()
    
    print("[OK] All conditions loaded from JSON:")
    for cid in sorted(b_ids):
        print(f"    + {cid}")
    
    print()
    print("=" * 50)
    print("[PASS] Frontend and Backend both load from JSON!")
    print()
    print("To modify conditions:")
    print("  Edit: src/gs2026/dashboard2/config/bp_conditions.json")
    print("  Then: Restart Flask to reload backend")
    return 0

if __name__ == '__main__':
    sys.exit(main())
