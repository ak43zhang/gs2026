# 今天添加索引的影响评估报告

> 评估时间: 2026-03-31 14:13  
> 当前状态: 交易中（14:13）

---

## 一、当前表状态

根据之前的数据分析：

| 表名 | 数据量 | 状态 |
|------|--------|------|
| monitor_gp_sssj_20260331 | ~2400万条 | 无索引 |
| monitor_zq_sssj_20260331 | ~数百万条 | 无索引 |
| monitor_hy_sssj_20260331 | ~数十万条 | 无索引 |
| monitor_gp_top30_20260331 | ~数万条 | 无索引 |
| monitor_zq_top30_20260331 | ~数万条 | 无索引 |
| monitor_hy_top30_20260331 | ~数万条 | 无索引 |
| monitor_gp_apqd_20260331 | ~4800条 | 无索引 |

---

## 二、索引添加影响分析

### 2.1 对INSERT的影响

**结论: 低影响**

```
MySQL 5.6+ 支持 Online DDL
- 添加索引不会阻塞 INSERT 操作
- 但会增加 INSERT 的耗时（需要维护索引）
- 预计 INSERT 性能下降: 10-20%
```

**实际影响**:
- 当前每3秒插入一批数据
- 索引维护会增加少量CPU和IO开销
- 对于2400万条数据的大表，影响可接受

### 2.2 对SELECT的影响

**结论: 立即受益**

```
添加索引后:
- 按股票代码查询: 27秒 → 50-100ms (提升270-540倍)
- 按时间查询: 全表扫描 → 索引扫描
- 查询性能立即提升
```

### 2.3 索引添加时间估算

| 表名 | 数据量 | 预估时间 |
|------|--------|----------|
| monitor_gp_sssj_20260331 | 2400万 | 30-60秒 |
| monitor_zq_sssj_20260331 | 数百万 | 10-20秒 |
| monitor_hy_sssj_20260331 | 数十万 | 3-5秒 |
| *_top30_* | 数万 | 1-3秒 |
| monitor_gp_apqd_20260331 | 4800 | <1秒 |

**总计**: 约 60-90秒

### 2.4 风险评估

| 风险项 | 等级 | 说明 |
|--------|------|------|
| 阻塞INSERT | 低 | MySQL 5.6+ Online DDL 支持 |
| CPU升高 | 中 | 索引构建期间CPU使用率上升 |
| IO升高 | 中 | 大量磁盘读写操作 |
| 锁等待 | 低 | Online DDL 减少锁竞争 |
| 查询失败 | 极低 | 索引添加不影响现有查询 |

---

## 三、方案对比

### 方案A: 立即添加索引（推荐）

**优点**:
- 立即解决慢查询问题（27秒 → 100ms）
- 当前14:13不是交易高峰
- MySQL 5.6+ Online DDL 保证不阻塞写入

**缺点**:
- 索引构建期间CPU/IO升高
- INSERT性能短暂下降10-20%

**建议**: ✓ 推荐

---

### 方案B: 收盘后添加（15:00后）

**优点**:
- 无交易压力，更安全
- 系统资源充足

**缺点**:
- 慢查询问题持续45分钟
- 用户体验受影响

**建议**: 备选方案

---

### 方案C: 分阶段添加

**步骤**:
1. 先添加小表（top30, apqd）- 约10秒
2. 等待1分钟观察
3. 再添加中等表（hy_sssj, zq_sssj）- 约30秒
4. 等待1分钟观察
5. 最后添加大表（gp_sssj）- 约60秒

**优点**:
- 降低单次操作风险
- 可以观察每阶段影响

**缺点**:
- 操作复杂，耗时更长
- 大表问题仍未立即解决

**建议**: 如果担心风险，可选此方案

---

## 四、最终建议

### 推荐方案: 方案A（立即添加）

**理由**:
1. **MySQL 5.6+ Online DDL** 保证不阻塞INSERT
2. **当前非交易高峰**，系统压力较小
3. **立即解决** 27秒慢查询问题
4. **风险可控**，索引构建时间仅60-90秒

**实施步骤**:
```bash
# 1. 先添加小表（约10秒）
ALTER TABLE monitor_gp_top30_20260331 ADD INDEX idx_time (time);
ALTER TABLE monitor_zq_top30_20260331 ADD INDEX idx_time (time);
...

# 2. 再添加中等表（约30秒）
ALTER TABLE monitor_hy_sssj_20260331 ADD INDEX idx_code_time (industry_code, time);
ALTER TABLE monitor_zq_sssj_20260331 ADD INDEX idx_code_time (bond_code, time);

# 3. 最后添加大表（约60秒）
ALTER TABLE monitor_gp_sssj_20260331 ADD INDEX idx_code_time (stock_code, time);
ALTER TABLE monitor_gp_sssj_20260331 ADD INDEX idx_time (time);
```

**监控指标**:
- CPU使用率
- 磁盘IO
- INSERT响应时间
- 查询响应时间

---

## 五、回滚方案

如果添加索引后出现问题，可以立即删除索引：

```sql
-- 删除索引
ALTER TABLE monitor_gp_sssj_20260331 DROP INDEX idx_code_time;
ALTER TABLE monitor_gp_sssj_20260331 DROP INDEX idx_time;
```

删除索引是快速操作（<1秒），不会影响数据。

---

**结论**: 建议立即实施方案A，风险可控，收益明显。
