"""DeepSeek AI 分析模块。

该包提供基于 DeepSeek 大语言模型的事件驱动分析功能，
包括全球重要事件采集、多维度评分、A股影响分析等核心能力。

主要模块:
    - deepseek_analysis_event_driven: 事件驱动分析主流程，
      负责调度 DeepSeek AI 对新闻事件进行多维度评分与分析。

依赖:
    - Playwright: 浏览器自动化，用于与 DeepSeek 网页端交互
    - Redis: 分布式锁，防止多进程重复分析同一事件
    - SQLAlchemy: 数据库连接与数据持久化
    - pandas: 数据处理与查询结果转换
"""
