# API测试工具使用说明

## api_tester.py

测试各模块API接口

### 使用示例

```bash
# 测试单个端点
python tools/api_tester.py --endpoint /api/stock-picker/search --params "q=电力&limit=10"

# POST请求
python tools/api_tester.py --endpoint /api/stock-picker/query --method POST --data '{"tags":["industry:881145"]}'

# 测试智能选股
python tools/api_tester.py --test-stock-picker

# 测试数据监控
python tools/api_tester.py --test-monitor

# 测试所有API
python tools/api_tester.py --test-all
```

### 测试覆盖

- 智能选股: 搜索、查询
- 数据监控: 时间戳、排行榜

### 输出说明

- 状态码
- 响应码/消息
- 数据条数
- 样本数据
