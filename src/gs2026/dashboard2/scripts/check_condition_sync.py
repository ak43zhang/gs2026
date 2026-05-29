"""
校验前后端买点条件定义是否同步
用法: python check_condition_sync.py
"""
import re
import sys
from pathlib import Path

# 文件路径
FRONTEND_FILE = Path(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html')
BACKEND_FILE = Path(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\backtest_worker.py')

def parse_frontend_conditions():
    """解析前端 BP_CONDITIONS"""
    content = FRONTEND_FILE.read_text(encoding='utf-8')
    
    # 找到 BP_CONDITIONS 数组
    match = re.search(r'var BP_CONDITIONS = \[([^\]]+)', content, re.DOTALL)
    if not match:
        print("ERROR: Cannot find frontend BP_CONDITIONS")
        return []
    
    array_content = match.group(1)
    
    # 提取每个条件对象 - 匹配多行
    conditions = []
    # 匹配从 {id:... 到 }, 或 },\n 结束
    pattern = r"\{id:'([^']+)'[^}]*?type:'([^']+)'[^}]*?name:'([^']+)'[^}]*?\n\s*\}"
    for m in re.finditer(pattern, array_content, re.DOTALL):
        block = m.group(0)
        cond = {
            'id': m.group(1),
            'type': m.group(2),
            'name': m.group(3),
        }
        # 提取 mode - 可能带引号也可能不带
        mode_match = re.search(r"mode:'([^']+)'", block)
        cond['mode'] = mode_match.group(1) if mode_match else 'normal'
        # 提取 param - 可能带引号
        param_match = re.search(r"param:'([^']+)'", block)
        cond['param'] = param_match.group(1) if param_match else None
        # 提取 def - 可能是数字或字符串
        def_match = re.search(r"def:([^,}\s]+)", block)
        if def_match:
            val = def_match.group(1).strip()
            # 去掉可能的引号
            cond['default'] = val.strip("'\"")
        else:
            cond['default'] = None
        # 提取 on
        on_match = re.search(r"on:(true|false)", block)
        cond['on'] = on_match.group(1) == 'true' if on_match else True
        
        conditions.append(cond)
    
    return conditions

def parse_backend_conditions():
    """解析后端条件定义"""
    content = BACKEND_FILE.read_text(encoding='utf-8')
    
    conditions = []
    
    # 解析 _get_market_conditions
    mkt_match = re.search(r'def _get_market_conditions.*?return \[(.*?)\]', content, re.DOTALL)
    if mkt_match:
        for line in mkt_match.group(1).split('\n'):
            if "'id':" in line:
                cond = {'type': 'market'}
                id_match = re.search(r"'id':\s*'([^']+)'", line)
                name_match = re.search(r"'name':\s*'([^']+)'", line)
                mode_match = re.search(r"'mode':\s*'([^']+)'", line)
                param_match = re.search(r"'param':\s*'([^']+)'", line)
                def_match = re.search(r"'def':\s*([^,}]+)", line)
                
                if id_match:
                    cond['id'] = id_match.group(1)
                    cond['name'] = name_match.group(1) if name_match else ''
                    cond['mode'] = mode_match.group(1) if mode_match else 'normal'
                    cond['param'] = param_match.group(1) if param_match else None
                    cond['default'] = def_match.group(1).strip() if def_match else None
                    conditions.append(cond)
    
    # 解析 _get_stock_conditions
    stock_match = re.search(r'def _get_stock_conditions.*?return \[(.*?)\]', content, re.DOTALL)
    if stock_match:
        for line in stock_match.group(1).split('\n'):
            if "'id':" in line:
                cond = {'type': 'stock'}
                id_match = re.search(r"'id':\s*'([^']+)'", line)
                name_match = re.search(r"'name':\s*'([^']+)'", line)
                mode_match = re.search(r"'mode':\s*'([^']+)'", line)
                param_match = re.search(r"'param':\s*'([^']+)'", line)
                def_match = re.search(r"'def':\s*([^,}]+)", line)
                
                if id_match:
                    cond['id'] = id_match.group(1)
                    cond['name'] = name_match.group(1) if name_match else ''
                    cond['mode'] = mode_match.group(1) if mode_match else 'normal'
                    cond['param'] = param_match.group(1) if param_match else None
                    cond['default'] = def_match.group(1).strip() if def_match else None
                    conditions.append(cond)
    
    # 解析 _get_link_conditions
    link_match = re.search(r'def _get_link_conditions.*?return \[(.*?)\]', content, re.DOTALL)
    if link_match:
        for line in link_match.group(1).split('\n'):
            if "'id':" in line:
                cond = {'type': 'link'}
                id_match = re.search(r"'id':\s*'([^']+)'", line)
                name_match = re.search(r"'name':\s*'([^']+)'", line)
                mode_match = re.search(r"'mode':\s*'([^']+)'", line)
                param_match = re.search(r"'param':\s*'([^']+)'", line)
                def_match = re.search(r"'def':\s*([^,}]+)", line)
                
                if id_match:
                    cond['id'] = id_match.group(1)
                    cond['name'] = name_match.group(1) if name_match else ''
                    cond['mode'] = mode_match.group(1) if mode_match else 'normal'
                    cond['param'] = param_match.group(1) if param_match else None
                    cond['default'] = def_match.group(1).strip() if def_match else None
                    conditions.append(cond)
    
    return conditions

def compare_conditions():
    """对比前后端条件"""
    frontend = {c['id']: c for c in parse_frontend_conditions()}
    backend = {c['id']: c for c in parse_backend_conditions()}
    
    print("=" * 60)
    print("BP_CONDITIONS Sync Check Report")
    print("=" * 60)
    
    # 检查前端有后端无
    frontend_only = set(frontend.keys()) - set(backend.keys())
    if frontend_only:
        print(f"\n[!] Frontend only ({len(frontend_only)}):")
        for cid in frontend_only:
            print(f"   - {cid}: {frontend[cid]['name']}")
    
    # 检查后端有前端无
    backend_only = set(backend.keys()) - set(frontend.keys())
    if backend_only:
        print(f"\n[!] Backend only ({len(backend_only)}):")
        for cid in backend_only:
            print(f"   - {cid}: {backend[cid]['name']}")
    
    # 检查共同条件的一致性
    common = set(frontend.keys()) & set(backend.keys())
    mismatches = []
    for cid in common:
        f, b = frontend[cid], backend[cid]
        issues = []
        if f['type'] != b['type']:
            issues.append(f"type: {f['type']} vs {b['type']}")
        if f['mode'] != b['mode']:
            issues.append(f"mode: {f['mode']} vs {b['mode']}")
        if f['param'] != b['param']:
            issues.append(f"param: {f['param']} vs {b['param']}")
        if f['default'] != b['default']:
            issues.append(f"def: {f['default']} vs {b['default']}")
        if issues:
            mismatches.append((cid, f['name'], issues))
    
    if mismatches:
        print(f"\n[!] Mismatched ({len(mismatches)}):")
        for cid, name, issues in mismatches:
            print(f"   - {cid} ({name}):")
            for issue in issues:
                print(f"      * {issue}")
    
    # 总结
    total_issues = len(frontend_only) + len(backend_only) + len(mismatches)
    print(f"\n{'=' * 60}")
    if total_issues == 0:
        print("[OK] All conditions in sync")
        return 0
    else:
        print(f"[FAIL] {total_issues} issue(s) found")
        return 1

if __name__ == '__main__':
    sys.exit(compare_conditions())
