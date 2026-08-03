# 切换期监控指南

## 监控指标

### 关键指标

| 指标 | 告警阈值 | 严重阈值 | 处理措施 |
|------|----------|----------|----------|
| 错误率 | > 0.1% | > 1% | 热回滚 |
| 响应时间 | > 200ms | > 500ms | 热回滚 |
| 成功率 | < 99% | < 95% | 热回滚 |

### 监控命令

```bash
# 查看错误日志
tail -f /var/log/gs2026/error.log | grep -i "filter\|pipeline"

# 查看响应时间
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:5000/api/filter/stock
```

## 热回滚

### 自动回滚

连续5分钟错误率>1%自动切换回前端过滤。

### 手动回滚

```bash
# 方法1: Python脚本
python switch_to_backend.py off

# 方法2: curl命令
curl -X POST http://localhost:5000/api/filter/config \
  -d '{"USE_BACKEND_FILTER": false}'

# 方法3: 配置文件
echo "USE_BACKEND_FILTER=false" > /etc/gs2026/config.env
systemctl restart gs2026
```

## 验证清单

- [ ] 错误率 < 0.1%
- [ ] 响应时间 < 200ms
- [ ] 功能正常
- [ ] 回滚机制有效

## 联系方式

如有问题，立即回滚并联系开发团队。
