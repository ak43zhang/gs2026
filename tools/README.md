# GS2026 工具集

项目诊断和维护工具集合

## 工具清单

### 数据库诊断
| 工具 | 功能 | 示例 |
|------|------|------|
| `db_inspector.py` | 检查表结构、索引、数据量 | `python tools/db_inspector.py --table monitor_gp_sssj_20260421` |
| `table_validator.py` | 验证表数据完整性 | `python tools/table_validator.py --check-bond` |

### Redis管理
| 工具 | 功能 | 示例 |
|------|------|------|
| `redis_checker.py` | 检查Redis键、内存 | `python tools/redis_checker.py --pattern "domain:*" --stats` |

### API测试
| 工具 | 功能 | 示例 |
|------|------|------|
| `api_tester.py` | 测试API接口 | `python tools/api_tester.py --test-stock-picker` |

### 缓存管理
| 工具 | 功能 | 示例 |
|------|------|------|
| `cache_manager.py` | 管理内存/宽表缓存 | `python tools/cache_manager.py --warm-up` |

### 环境检查
| 工具 | 功能 | 示例 |
|------|------|------|
| `env_checker.py` | 检查运行环境 | `python tools/env_checker.py` |

## 快速开始

```bash
# 检查环境
python tools/env_checker.py

# 预热缓存
python tools/cache_manager.py --warm-up

# 验证数据
python tools/table_validator.py --check-bond

# 测试API
python tools/api_tester.py --test-all
```

## 详细文档

见 `docs/06-工具使用/` 目录
