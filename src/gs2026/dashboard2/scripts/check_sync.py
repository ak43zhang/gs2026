"""Simple sync check - v3"""
import re
import sys
from pathlib import Path

FRONTEND = Path(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html')
BACKEND = Path(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\backtest_worker.py')

def main():
    f_content = FRONTEND.read_text(encoding='utf-8')
    b_content = BACKEND.read_text(encoding='utf-8')
    
    # Extract frontend IDs from BP_CONDITIONS array
    f_match = re.search(r'var BP_CONDITIONS = \[([\s\S]+?)\];\s*\n\s*var _bpParams', f_content)
    if f_match:
        f_ids = set(re.findall(r"id:'([^']+)'", f_match.group(1)))
    else:
        f_ids = set()
    
    # Extract backend IDs - look for all 'id': 'xxx' in the file within condition functions
    # Find the three function blocks
    b_ids = set()
    for func_name in ['_get_market_conditions', '_get_stock_conditions', '_get_link_conditions']:
        # Find function start
        start = b_content.find(f'def {func_name}')
        if start == -1:
            continue
        # Find next def or end of class
        end = b_content.find('\n    def ', start + 1)
        if end == -1:
            end = len(b_content)
        block = b_content[start:end]
        ids = re.findall(r"'id':\s*'([^']+)'", block)
        b_ids.update(ids)
    
    print("=" * 50)
    print("BP_CONDITIONS Sync Check")
    print("=" * 50)
    print(f"Frontend: {len(f_ids)} conditions")
    print(f"Backend:  {len(b_ids)} conditions")
    print()
    
    only_f = f_ids - b_ids
    only_b = b_ids - f_ids
    common = f_ids & b_ids
    
    if only_f:
        print(f"[!] Only in frontend ({len(only_f)}):")
        for cid in sorted(only_f):
            print(f"    - {cid}")
        print()
    
    if only_b:
        print(f"[!] Only in backend ({len(only_b)}):")
        for cid in sorted(only_b):
            print(f"    - {cid}")
        print()
    
    print(f"[OK] Common: {len(common)} conditions")
    for cid in sorted(common):
        print(f"    + {cid}")
    
    print()
    print("=" * 50)
    if not only_f and not only_b:
        print("[PASS] All conditions synced!")
        return 0
    else:
        print(f"[FAIL] {len(only_f) + len(only_b)} mismatch(es)")
        return 1

if __name__ == '__main__':
    sys.exit(main())
