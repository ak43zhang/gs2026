"""创建分析中心相关数据表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.utils import mysql_util, log_util

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 领域分析表
CREATE_DOMAIN_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_domain_detail_2026 (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  content_hash VARCHAR(64) NOT NULL COMMENT '领域id：关键事件+时间的MD5',
  main_area VARCHAR(64) NOT NULL COMMENT '主领域（科技/消费/医疗等）',
  child_area VARCHAR(64) NOT NULL COMMENT '子领域（AI/新能源等）',
  event_time DATETIME NOT NULL COMMENT '事件发生时间',
  event_source VARCHAR(100) DEFAULT '' COMMENT '事件来源（新华社/财联社等）',
  key_event VARCHAR(500) DEFAULT '' COMMENT '关键事件标题',
  brief_desc TEXT COMMENT '简要描述',
  importance_score TINYINT NOT NULL DEFAULT 0 COMMENT '重要程度评分（0-15）',
  business_impact_score SMALLINT NOT NULL DEFAULT 0 COMMENT '业务影响维度评分（-60至60）',
  composite_score SMALLINT NOT NULL DEFAULT 0 COMMENT '综合评分（重要程度×4+业务影响）',
  news_size ENUM('重大','大','中','小') NOT NULL DEFAULT '小' COMMENT '消息大小',
  news_type ENUM('利好','利空','中性') NOT NULL DEFAULT '中性' COMMENT '利空利好',
  sectors JSON COMMENT '涉及板块（JSON数组）',
  concepts JSON COMMENT '涉及概念（JSON数组）',
  stock_codes JSON COMMENT '股票代码（JSON数组）',
  reason_analysis TEXT COMMENT '原因分析',
  deep_analysis JSON COMMENT '深度分析（多维度）',
  analysis_version VARCHAR(32) DEFAULT '' COMMENT 'AI分析语料版本',
  analysis_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'AI分析完成时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_content_hash (content_hash),
  KEY idx_event_time (event_time),
  KEY idx_main_area (main_area),
  KEY idx_child_area (child_area),
  KEY idx_composite_score (composite_score),
  KEY idx_news_type (news_type),
  KEY idx_news_size (news_size),
  KEY idx_area_time (main_area, child_area, event_time),
  KEY idx_time_type (event_time, news_type),
  KEY idx_time_score (event_time, composite_score),
  FULLTEXT KEY ft_key_event_desc (key_event, brief_desc, reason_analysis) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='领域分析明细表（事件驱动分析）';
"""

# 涨停分析表
CREATE_ZTB_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_ztb_detail_2025 (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  content_hash VARCHAR(64) NOT NULL COMMENT '股票名称+日期MD5',
  stock_name VARCHAR(64) NOT NULL COMMENT '股票简称',
  stock_code VARCHAR(20) DEFAULT '' COMMENT '股票代码',
  trade_date DATE NOT NULL COMMENT '交易日期',
  zt_time TIME DEFAULT NULL COMMENT '涨停时间',
  stock_nature TEXT COMMENT '股性分析',
  lhb_analysis TEXT COMMENT '龙虎榜分析',
  sector_msg JSON COMMENT '板块消息 [{板块, 板块刺激消息[]}]',
  concept_msg JSON COMMENT '概念消息 [{概念, 概念刺激消息[]}]',
  leading_stock_msg JSON COMMENT '龙头股消息 [{龙头股, 龙头股刺激消息[]}]',
  influence_msg JSON COMMENT '影响消息 [{影响消息, 最早出现时间}]',
  expect_msg JSON COMMENT '预期消息 [{预期消息, 最早出现时间, 延续性}]',
  deep_analysis JSON COMMENT '深度分析 [字符串数组]',
  sectors JSON COMMENT '涉及板块名称列表（提取自sector_msg）',
  concepts JSON COMMENT '涉及概念名称列表（提取自concept_msg）',
  leading_stocks JSON COMMENT '龙头股名称列表',
  has_expect TINYINT DEFAULT 0 COMMENT '是否有预期消息(0/1)',
  continuity TINYINT DEFAULT 0 COMMENT '延续性判断(0=否,1=是)',
  zt_time_range ENUM('early','mid','late') DEFAULT 'mid' COMMENT '涨停时段(early=早盘,mid=中盘,late=尾盘)',
  analysis_version VARCHAR(32) DEFAULT '' COMMENT 'AI分析版本',
  analysis_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_content_hash (content_hash),
  KEY idx_trade_date (trade_date),
  KEY idx_stock_name (stock_name),
  KEY idx_stock_code (stock_code),
  KEY idx_zt_time (zt_time),
  KEY idx_zt_time_range (zt_time_range),
  KEY idx_has_expect (has_expect),
  KEY idx_continuity (continuity),
  KEY idx_time_stock (trade_date, stock_name),
  FULLTEXT KEY ft_nature_analysis (stock_nature, lhb_analysis) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='涨停分析明细表';
"""

# 公告分析表
CREATE_NOTICE_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_notice_detail_2026 (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  content_hash VARCHAR(64) NOT NULL COMMENT '公告ID的MD5',
  notice_id VARCHAR(64) DEFAULT '' COMMENT '原始公告ID',
  stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
  stock_name VARCHAR(64) DEFAULT '' COMMENT '股票简称',
  notice_date DATE NOT NULL COMMENT '公告日期',
  notice_title VARCHAR(500) DEFAULT '' COMMENT '公告标题',
  notice_content TEXT COMMENT '公告内容',
  risk_level ENUM('高','中','低') DEFAULT '中' COMMENT '风险等级',
  notice_type ENUM('利好','利空','中性') DEFAULT '中性' COMMENT '消息类型',
  judgment_basis TEXT COMMENT '判定依据',
  key_points JSON COMMENT '关键要点 [字符串数组]',
  short_term_impact VARCHAR(500) DEFAULT '' COMMENT '短线影响',
  medium_term_impact VARCHAR(500) DEFAULT '' COMMENT '中线影响',
  risk_score TINYINT DEFAULT 50 COMMENT '风险评分(高=75,中=50,低=25)',
  type_score TINYINT DEFAULT 50 COMMENT '类型评分(利好=75,中性=50,利空=25)',
  analysis_version VARCHAR(32) DEFAULT '' COMMENT 'AI分析版本',
  analysis_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_content_hash (content_hash),
  KEY idx_notice_date (notice_date),
  KEY idx_stock_code (stock_code),
  KEY idx_stock_name (stock_name),
  KEY idx_risk_level (risk_level),
  KEY idx_notice_type (notice_type),
  KEY idx_risk_score (risk_score),
  KEY idx_time_type (notice_date, notice_type),
  FULLTEXT KEY ft_title_content (notice_title, notice_content, judgment_basis) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公告分析明细表';
"""


def create_tables():
    """创建所有分析中心表"""
    mysql_tool = mysql_util.MysqlTool()
    
    tables = [
        ('analysis_domain_detail_2026', CREATE_DOMAIN_TABLE),
        ('analysis_ztb_detail_2025', CREATE_ZTB_TABLE),
        ('analysis_notice_detail_2026', CREATE_NOTICE_TABLE),
    ]
    
    for table_name, sql in tables:
        try:
            mysql_tool.update_data(sql)
            logger.info(f"✅ 表 {table_name} 创建成功")
        except Exception as e:
            logger.error(f"❌ 表 {table_name} 创建失败: {e}")


if __name__ == '__main__':
    create_tables()
