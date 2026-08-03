# 前后端过滤对比验证方案

## 一、验证目标

确保后端 UnifiedPipeline 与前端过滤逻辑执行效果 **100% 一致**

## 二、验证方法

### 2.1 对比测试框架

```
┌─────────────────────────────────────────────────────────────────┐
│                      对比测试框架                                │
├─────────────────────────────────────────────────────────────────┤
│  输入: 同一组原始数据 + 同一套过滤配置                            │
│                          │                                      │
│          ┌───────────────┴───────────────┐                      │
│          ▼                               ▼                      │
│  ┌───────────────┐               ┌───────────────┐              │
│  │  前端过滤      │               │  后端过滤      │              │
│  │  (JavaScript) │               │  (Python)     │              │
│  │               │               │               │              │
│  │ runPipeline() │               │ Pipeline.     │              │
│  │               │               │ execute()     │              │
│  └───────┬───────┘               └───────┬───────┘              │
│          │                               │                      │
│          ▼                               ▼                      │
│  ┌───────────────┐               ┌───────────────┐              │
│  │  前端结果      │               │  后端结果      │              │
│  │  Result_A     │               │  Result_B     │              │
│  └───────────────┘               └───────────────┘              │
│          │                               │                      │
│          └───────────────┬───────────────┘                      │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │     对比引擎           │                          │
│              │  compare(Result_A,    │                          │
│              │         Result_B)     │                          │
│              └───────────┬───────────┘                          │
│                          │                                      │
│              ┌───────────┴───────────┐                          │
│              ▼                       ▼                          │
│        ✅ 一致                      ❌ 差异                      │
│        (通过)                      (记录并修复)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 测试数据生成

#### 2.2.1 股票测试数据

```python
# 模拟股票数据（与前端数据结构一致）
stock_test_data = [
    {
        'code': '000001',
        'name': '平安银行',
        'change_pct': 2.5,
        'price': 12.5,
        'count': 15,
        'window_count': 3,
        'industry': '银行',
        'main_net_amount': 1250.5,
        'bond_code': '113001',
        'bond_name': '平安转债',
        'consecutive_attacks': 2,
        'main_net_count': 5,
        'max_cumulative_main_net': 2000.0
    },
    {
        'code': '000002',
        'name': '万科A',
        'change_pct': -1.2,
        'price': 18.3,
        'count': 8,
        'window_count': 0,  # 边界：0值
        'industry': '房地产',
        'main_net_amount': -500.0,
        'bond_code': '113002',
        'bond_name': '万科转债',
        'consecutive_attacks': 0,
        'main_net_count': 2,
        'max_cumulative_main_net': 800.0
    },
    # ... 更多测试数据（100条）
]
```

#### 2.2.2 债券测试数据

```python
# 模拟债券数据
bond_test_data = [
    {
        'code': '113001',
        'name': '平安转债',
        'change_pct': 1.8,
        'price': 125.8,
        'count': 12,
        'window_count': 2,
        'amount': 5000.0,
        'industry': '银行',
        'main_net_amount': 890.3,
        'min1_change_pct': 0.5,
        'min1_amount': 200.0,
        'is_green': False
    },
    {
        'code': '113002',
        'name': '万科转债',
        'change_pct': -0.5,
        'price': 108.2,
        'count': 5,
        'window_count': 0,
        'amount': 2000.0,  # 边界：小金额
        'industry': '房地产',
        'main_net_amount': -200.0,
        'min1_change_pct': -0.2,
        'min1_amount': 50.0,
        'is_green': True  # 绿名单
    },
    # ... 更多测试数据（100条）
]
```

#### 2.2.3 边界测试数据

```python
# 边界条件测试数据
boundary_test_cases = [
    # 1. 空数据
    {'name': '空数据', 'data': []},
    
    # 2. 单条数据
    {'name': '单条数据', 'data': [stock_test_data[0]]},
    
    # 3. 全零值
    {'name': '全零window_count', 'data': [{'window_count': 0, 'count': 0, ...}]},
    
    # 4. 负值
    {'name': '负涨跌幅', 'data': [{'change_pct': -5.0, ...}]},
    
    # 5. 缺失字段
    {'name': '缺失bond_code', 'data': [{'code': '000003', 'bond_code': None, ...}]},
    
    # 6. 大数据量
    {'name': '1000条数据', 'data': generate_large_dataset(1000)},
    
    # 7. 同一行业
    {'name': '全银行', 'data': [{'industry': '银行', ...} for _ in range(50)]},
]
```

### 2.3 过滤配置组合

```python
# 测试所有过滤配置组合
test_configs = [
    # 1. 基础配置
    {'name': '无过滤', 'stock': {}, 'bond': {}},
    
    # 2. 单过滤器
    {'name': '股票仅前10区间次数', 'stock': {'topn_window': 10}, 'bond': {}},
    {'name': '债券仅前20金额', 'stock': {}, 'bond': {'topn_amount': 20}},
    {'name': '股票仅银行行业', 'stock': {'industry': '银行'}, 'bond': {}},
    {'name': '债券排除绿名单', 'stock': {}, 'bond': {'green_list': True}},
    
    # 3. 多过滤器组合
    {
        'name': '股票：前5行业+前10区间次数',
        'stock': {'topn_sectors': 5, 'topn_window': 10},
        'bond': {}
    },
    {
        'name': '债券：前5行业+前20金额+排除绿名单',
        'stock': {},
        'bond': {'topn_sectors': 5, 'topn_amount': 20, 'green_list': True}
    },
    
    # 4. 复杂组合
    {
        'name': '股票全过滤+债券全过滤',
        'stock': {
            'industry': '电子',
            'topn_sectors': 5,
            'topn_sectors_pct': 0,
            'topn_window': 10,
            'topn_count': 20,
            'bond_filter': True
        },
        'bond': {
            'industry': '电子',
            'topn_sectors': 5,
            'topn_sectors_pct': 0,
            'topn_amount': 20,
            'topn_window': 10,
            'topn_count': 20,
            'green_list': True
        }
    },
    
    # 5. 边界值
    {'name': '前N=0（全部）', 'stock': {'topn_window': 0}, 'bond': {}},
    {'name': '前N=1（最小）', 'stock': {'topn_count': 1}, 'bond': {}},
    {'name': '前N=100（超过数据量）', 'stock': {'topn_count': 100}, 'bond': {}},
]
```

## 三、对比验证流程

### 3.1 自动化测试脚本

```python
# test_pipeline_comparison.py
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By

class PipelineComparator:
    """前后端过滤对比验证器"""
    
    def __init__(self, backend_url='http://localhost:5000'):
        self.backend_url = backend_url
        self.driver = webdriver.Chrome()
        self.differences = []
    
    def get_frontend_result(self, data, config):
        """通过Selenium获取前端过滤结果"""
        # 1. 打开页面
        self.driver.get('http://localhost:5000/monitor')
        
        # 2. 注入测试数据
        self.driver.execute_script(f"""
            window._rankRawData['stock-ranking'] = {json.dumps(data['stocks'])};
            window._rankRawData['bond-ranking'] = {json.dumps(data['bonds'])};
        """)
        
        # 3. 设置过滤配置
        for key, value in config.get('stock', {}).items():
            el = self.driver.find_element(By.ID, f'stock-{key}')
            el.value = str(value)
            el.dispatch_event('change')
        
        # 4. 执行过滤
        self.driver.execute_script("rerenderStockRanking(); rerenderBondRanking();")
        
        # 5. 获取结果
        result = self.driver.execute_script("""
            return {
                'stocks': window._filteredStockData || [],
                'bonds': window._filteredBondData || []
            };
        """)
        
        return result
    
    def get_backend_result(self, data, config):
        """调用后端API获取过滤结果"""
        response = requests.post(
            f'{self.backend_url}/api/filter/compare',
            json={
                'stocks': data['stocks'],
                'bonds': data['bonds'],
                'config': config
            }
        )
        return response.json()['data']
    
    def compare_results(self, frontend_result, backend_result):
        """对比前后端结果"""
        differences = []
        
        # 对比股票结果
        frontend_codes = set(s['code'] for s in frontend_result['stocks'])
        backend_codes = set(s['code'] for s in backend_result['stocks'])
        
        if frontend_codes != backend_codes:
            differences.append({
                'type': 'stock_codes_mismatch',
                'frontend': list(frontend_codes),
                'backend': list(backend_codes),
                'only_in_frontend': list(frontend_codes - backend_codes),
                'only_in_backend': list(backend_codes - frontend_codes)
            })
        
        # 对比债券结果
        frontend_bond_codes = set(b['code'] for b in frontend_result['bonds'])
        backend_bond_codes = set(b['code'] for b in backend_result['bonds'])
        
        if frontend_bond_codes != backend_bond_codes:
            differences.append({
                'type': 'bond_codes_mismatch',
                'frontend': list(frontend_bond_codes),
                'backend': list(backend_bond_codes),
                'only_in_frontend': list(frontend_bond_codes - backend_bond_codes),
                'only_in_backend': list(backend_bond_codes - frontend_bond_codes)
            })
        
        # 对比字段值
        for stock in frontend_result['stocks']:
            backend_stock = next(
                (s for s in backend_result['stocks'] if s['code'] == stock['code']), 
                None
            )
            if backend_stock:
                for field in ['change_pct', 'count', 'window_count', 'main_net_amount']:
                    if abs(stock.get(field, 0) - backend_stock.get(field, 0)) > 0.01:
                        differences.append({
                            'type': 'field_value_mismatch',
                            'code': stock['code'],
                            'field': field,
                            'frontend': stock.get(field),
                            'backend': backend_stock.get(field)
                        })
        
        return differences
    
    def run_test(self, test_data, test_config):
        """执行单次对比测试"""
        print(f"\n测试: {test_config['name']}")
        
        # 获取前后端结果
        frontend_result = self.get_frontend_result(test_data, test_config)
        backend_result = self.get_backend_result(test_data, test_config)
        
        # 对比
        differences = self.compare_results(frontend_result, backend_result)
        
        if differences:
            print(f"  ❌ 发现 {len(differences)} 处差异")
            self.differences.append({
                'config': test_config['name'],
                'differences': differences
            })
            return False
        else:
            print(f"  ✅ 一致")
            return True
    
    def run_all_tests(self):
        """执行所有测试"""
        passed = 0
        failed = 0
        
        for test_data in all_test_datasets:
            for test_config in test_configs:
                if self.run_test(test_data, test_config):
                    passed += 1
                else:
                    failed += 1
        
        # 生成报告
        self.generate_report(passed, failed)
        
        return failed == 0
    
    def generate_report(self, passed, failed):
        """生成对比测试报告"""
        report = {
            'summary': {
                'total': passed + failed,
                'passed': passed,
                'failed': failed,
                'pass_rate': f"{passed/(passed+failed)*100:.2f}%"
            },
            'differences': self.differences,
            'timestamp': datetime.now().isoformat()
        }
        
        with open('pipeline_comparison_report.json', 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*50}")
        print(f"测试完成: 总计 {passed+failed}, 通过 {passed}, 失败 {failed}")
        print(f"通过率: {passed/(passed+failed)*100:.2f}%")
        print(f"报告已保存: pipeline_comparison_report.json")

# 运行测试
if __name__ == '__main__':
    comparator = PipelineComparator()
    success = comparator.run_all_tests()
    exit(0 if success else 1)
```

### 3.2 后端对比API

```python
# routes/filter_api.py

@api.route('/api/filter/compare', methods=['POST'])
def filter_compare():
    """
    对比测试专用API
    接收前端原始数据，返回过滤结果
    """
    data = request.json
    stocks = data.get('stocks', [])
    bonds = data.get('bonds', [])
    config = FilterConfig.from_dict(data.get('config', {}))
    
    pipeline = UnifiedPipeline(config)
    
    # 股票过滤
    filtered_stocks = pipeline.filter_stocks(stocks)
    
    # 债券过滤
    filtered_bonds = pipeline.filter_bonds(bonds)
    
    return jsonify({
        'success': True,
        'data': {
            'stocks': filtered_stocks,
            'bonds': filtered_bonds,
            'stock_count': len(filtered_stocks),
            'bond_count': len(filtered_bonds)
        }
    })
```

## 四、验证检查清单

### 4.1 功能一致性检查

| 检查项 | 检查方法 | 通过标准 |
|--------|----------|----------|
| 谓词型过滤器 | 单过滤器测试 | 结果code集合一致 |
| 排名型过滤器 | 单过滤器测试 | 结果code集合一致 |
| 多过滤器组合 | 组合测试 | 结果code集合一致 |
| 两阶段执行 | 谓词+排名组合 | 执行顺序正确 |
| 排名型取交集 | 多ranking测试 | 交集逻辑正确 |
| 排除<=0 | ranking字段=0测试 | 正确排除 |
| 降序排序 | 结果顺序检查 | 降序正确 |
| 前N截取 | N=5,10,20测试 | 截取数量正确 |

### 4.2 边界条件检查

| 检查项 | 测试数据 | 通过标准 |
|--------|----------|----------|
| 空数据 | [] | 返回空数组 |
| 单条数据 | [item] | 正确处理 |
| 全零值 | window_count=0 | 排除<=0 |
| 负值 | change_pct=-5 | 正确处理 |
| 缺失字段 | bond_code=None | 正确处理 |
| 大数据量 | 1000条 | 性能<500ms |
| 前N>数据量 | N=100, 数据20条 | 返回全部 |

### 4.3 性能对比

| 指标 | 前端 | 后端 | 差异 |
|------|------|------|------|
| 100条数据 | ~10ms | <300ms | 后端可接受 |
| 500条数据 | ~30ms | <500ms | 后端可接受 |
| 1000条数据 | ~50ms | <1000ms | 需优化 |

## 五、差异处理流程

```
发现差异
    ↓
记录差异详情（配置、输入数据、前后端输出）
    ↓
分析根因
    ├── 数据问题 → 修复测试数据
    ├── 逻辑问题 → 修复后端代码
    └── 边界问题 → 补充边界处理
    ↓
修复并重新测试
    ↓
验证通过
```

## 六、产出物

| 产出物 | 说明 |
|--------|------|
| `test_pipeline_comparison.py` | 自动化对比测试脚本 |
| `test_data/` | 测试数据集（JSON） |
| `pipeline_comparison_report.json` | 对比测试报告 |
| `fix_log.md` | 差异修复记录 |

## 七、验收标准

- [ ] 所有功能测试用例通过（差异率=0%）
- [ ] 所有边界测试用例通过
- [ ] 性能指标达标（<500ms）
- [ ] 对比测试报告审批通过

---

**文档状态**: 待审核  
**编制时间**: 2026-08-03 22:40
