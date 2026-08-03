"""
前后端过滤结果对比脚本

使用方法：
1. 前端过滤后执行：copy(_filteredStockData) 保存为 frontend_stock.json
2. 调用后端API获取结果保存为 backend_stock.json
3. 运行：python compare_results.py frontend_stock.json backend_stock.json
"""
import json
import sys
from typing import List, Dict, Any, Set


def load_json(filepath: str) -> List[Dict[str, Any]]:
    """加载JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 加载文件失败: {filepath}, 错误: {e}")
        return []


def extract_codes(data: List[Dict[str, Any]]) -> Set[str]:
    """提取code集合"""
    return {str(item.get('code', '')) for item in data if item.get('code')}


def compare_field_values(frontend: List[Dict], backend: List[Dict], 
                         field: str, tolerance: float = 0.01) -> List[Dict]:
    """
    对比字段值
    
    Args:
        frontend: 前端结果
        backend: 后端结果
        field: 字段名
        tolerance: 浮点数容差
    
    Returns:
        差异列表
    """
    differences = []
    
    # 构建后端数据映射
    backend_map = {item['code']: item for item in backend if item.get('code')}
    
    for item in frontend:
        code = item.get('code')
        if not code or code not in backend_map:
            continue
        
        frontend_val = item.get(field)
        backend_val = backend_map[code].get(field)
        
        # 处理None
        if frontend_val is None and backend_val is None:
            continue
        if frontend_val is None or backend_val is None:
            differences.append({
                'code': code,
                'field': field,
                'frontend': frontend_val,
                'backend': backend_val,
                'diff': 'None mismatch'
            })
            continue
        
        # 数值对比
        try:
            f_val = float(frontend_val)
            b_val = float(backend_val)
            if abs(f_val - b_val) > tolerance:
                differences.append({
                    'code': code,
                    'field': field,
                    'frontend': f_val,
                    'backend': b_val,
                    'diff': abs(f_val - b_val)
                })
        except (ValueError, TypeError):
            # 字符串对比
            if str(frontend_val) != str(backend_val):
                differences.append({
                    'code': code,
                    'field': field,
                    'frontend': frontend_val,
                    'backend': backend_val,
                    'diff': 'String mismatch'
                })
    
    return differences


def compare_results(frontend_file: str, backend_file: str, 
                   detailed: bool = False) -> bool:
    """
    对比前后端结果
    
    Args:
        frontend_file: 前端结果文件
        backend_file: 后端结果文件
        detailed: 是否详细对比字段值
    
    Returns:
        True=一致, False=不一致
    """
    print(f"\n{'='*60}")
    print(f"对比: {frontend_file} vs {backend_file}")
    print(f"{'='*60}")
    
    # 加载数据
    frontend = load_json(frontend_file)
    backend = load_json(backend_file)
    
    if not frontend or not backend:
        print("❌ 数据加载失败")
        return False
    
    # 提取code集合
    frontend_codes = extract_codes(frontend)
    backend_codes = extract_codes(backend)
    
    print(f"\n数据量:")
    print(f"  前端: {len(frontend)} 条")
    print(f"  后端: {len(backend)} 条")
    print(f"  前端唯一code: {len(frontend_codes)}")
    print(f"  后端唯一code: {len(backend_codes)}")
    
    # 对比code集合
    if frontend_codes == backend_codes:
        print(f"\n✅ Code集合一致 ({len(frontend_codes)} 条)")
        
        # 详细字段对比
        if detailed:
            print(f"\n详细字段对比:")
            fields = ['change_pct', 'count', 'window_count', 'main_net_amount']
            all_match = True
            
            for field in fields:
                diffs = compare_field_values(frontend, backend, field)
                if diffs:
                    print(f"  ❌ {field}: {len(diffs)} 处差异")
                    for d in diffs[:3]:  # 只显示前3个
                        print(f"     {d['code']}: 前端={d['frontend']}, 后端={d['backend']}")
                    all_match = False
                else:
                    print(f"  ✅ {field}: 一致")
            
            return all_match
        
        return True
    else:
        print(f"\n❌ Code集合不一致")
        
        only_frontend = frontend_codes - backend_codes
        only_backend = backend_codes - frontend_codes
        
        if only_frontend:
            print(f"\n  仅前端有 ({len(only_frontend)} 条):")
            for code in list(only_frontend)[:5]:
                print(f"    - {code}")
            if len(only_frontend) > 5:
                print(f"    ... 还有 {len(only_frontend) - 5} 条")
        
        if only_backend:
            print(f"\n  仅后端有 ({len(only_backend)} 条):")
            for code in list(only_backend)[:5]:
                print(f"    - {code}")
            if len(only_backend) > 5:
                print(f"    ... 还有 {len(only_backend) - 5} 条")
        
        return False


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python compare_results.py <frontend.json> <backend.json> [--detailed]")
        print("示例: python compare_results.py frontend_stock.json backend_stock.json --detailed")
        sys.exit(1)
    
    frontend_file = sys.argv[1]
    backend_file = sys.argv[2]
    detailed = '--detailed' in sys.argv
    
    result = compare_results(frontend_file, backend_file, detailed)
    
    print(f"\n{'='*60}")
    if result:
        print("✅ 对比通过")
    else:
        print("❌ 对比失败")
    print(f"{'='*60}\n")
    
    sys.exit(0 if result else 1)


if __name__ == '__main__':
    main()
