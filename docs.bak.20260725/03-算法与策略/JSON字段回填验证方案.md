# JSON字段回填验证方案

## 验证策略（不影响生产数据）

### 方案1：单日小范围测试（推荐）

```bash
# 1. 选择最近的一天进行测试
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_shape

# 2. 使用 --skip-existing 模式（只读取，不写入）
# 修改代码临时测试：
# 在 _process_bond_worker 中注释掉 UPDATE 部分，只打印 SQL
```

### 方案2：备份后测试

```sql
-- 1. 备份原表
CREATE TABLE monitor_zq_sssj_20260723_backup AS SELECT * FROM monitor_zq_sssj_20260723;

-- 2. 测试回填
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_shape

-- 3. 验证数据
SELECT 
    bond_code, 
    time,
    ext_indicators->>'$.mkt_shape' as shape,
    ext_indicators->>'$.mkt_shape_detail' as detail
FROM monitor_zq_sssj_20260723 
WHERE ext_indicators->>'$.mkt_shape' IS NOT NULL
LIMIT 10;

-- 4. 如有问题，恢复备份
-- DROP TABLE monitor_zq_sssj_20260723;
-- RENAME TABLE monitor_zq_sssj_20260723_backup TO monitor_zq_sssj_20260723;
```

### 方案3：只读验证模式（最安全）

修改 `backfill_json_fields.py` 添加 `--dry-run` 模式：

```python
# 在 main() 中添加参数
parser.add_argument('--dry-run', action='store_true', help='只读模式，不实际更新')

# 在 _process_bond_worker 中
if dry_run:
    print(f"[DRY-RUN] 将更新 {len(updates)} 条记录")
    for upd in updates:
        print(f"  {upd['time']}: {upd['field_values']}")
    return {'success': True, 'updates': len(updates)}
```

## 验证检查清单

### 测试前
- [ ] 确认备份策略（方案1/2/3选择）
- [ ] 选择测试日期（建议最近1天）
- [ ] 确认字段注册表加载正确

### 测试中
- [ ] 观察日志输出，确认计算正确
- [ ] 检查是否有报错
- [ ] 验证计算结果合理性

### 测试后
- [ ] 查询数据库验证字段已更新
- [ ] 对比实时计算和回填结果是否一致
- [ ] 确认其他字段未被影响

## 快速验证命令

```bash
# 1. 检查注册表加载
python -c "
import sys
sys.path.insert(0, 'src/gs2026/monitor')
from monitor_bond import get_json_field_registry
r = get_json_field_registry()
print('注册表字段:', list(r.keys()))
"

# 2. 单日测试（建议先修改代码添加 --dry-run）
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_shape

# 3. 验证结果
mysql -e "
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN ext_indicators->>'$.mkt_shape' IS NOT NULL THEN 1 END) as has_shape
FROM monitor_zq_sssj_20260723;
"

# 4. 查看具体值
mysql -e "
SELECT 
    bond_code,
    time,
    ext_indicators->>'$.mkt_shape' as shape,
    ext_indicators->>'$.mkt_shape_detail' as detail
FROM monitor_zq_sssj_20260723 
WHERE ext_indicators->>'$.mkt_shape' IS NOT NULL
LIMIT 5;
"
```

## 建议

**推荐方案**：先使用 **单日测试** + **备份**，确认无误后再批量回填。

如需添加 `--dry-run` 模式，我可以立即修改代码。
