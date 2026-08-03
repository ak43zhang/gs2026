"""
债券绿名单系统（可扩展多模式）

纯 MySQL 查询 + pandas 逻辑计算，生成 green_bond_list 表。
新增模式：在 strategies/ 下新建策略文件 + @register + 在 strategies/__init__.py 导入。

入口：
  python -m gs2026.tools.green_bond.runner --mode full
  python -m gs2026.tools.green_bond.verify   # 一致性验收
"""
