-- 新闻分析性能优化 - 数据库索引添加脚本
-- 执行时间: 2026-04-15
-- 目标表: analysis_news_detail_2026

-- ============================================
-- 1. 基础索引
-- ============================================

-- 1.1 时间范围查询索引（最重要）
-- 用于优化 WHERE publish_time BETWEEN 'xxx' AND 'yyy'
ALTER TABLE analysis_news_detail_2026 ADD INDEX idx_publish_time (publish_time);

-- 1.2 消息类型索引
-- 用于优化 WHERE news_type = '利好'
ALTER TABLE analysis_news_detail_2026 ADD INDEX idx_news_type (news_type);

-- 1.3 消息大小索引
-- 用于优化 WHERE news_size = '重大'
ALTER TABLE analysis_news_detail_2026 ADD INDEX idx_news_size (news_size);

-- ============================================
-- 2. 复合索引（组合查询优化）
-- ============================================

-- 2.1 时间+类型+大小复合索引（最常用）
-- 用于优化时间范围+类型+大小的组合筛选
ALTER TABLE analysis_news_detail_2026 ADD INDEX idx_time_type_size (publish_time, news_type, news_size);

-- 2.2 时间+评分复合索引（排序优化）
-- 用于优化按评分排序的查询
ALTER TABLE analysis_news_detail_2026 ADD INDEX idx_time_score (publish_time, composite_score);

-- ============================================
-- 3. 全文搜索索引
-- ============================================

-- 3.1 标题+内容全文索引
-- 用于优化 MATCH(title, content) AGAINST 搜索
-- 注意: 全文索引只支持 MyISAM 或 InnoDB 5.6+
ALTER TABLE analysis_news_detail_2026 ADD FULLTEXT INDEX ft_title_content (title, content);

-- ============================================
-- 4. 验证索引
-- ============================================

-- 查看表的所有索引
SHOW INDEX FROM analysis_news_detail_2026;

-- 查看索引使用情况（执行查询后）
-- EXPLAIN SELECT * FROM analysis_news_detail_2026 WHERE publish_time BETWEEN '2026-04-14 15:00:00' AND '2026-04-15 09:00:00';
