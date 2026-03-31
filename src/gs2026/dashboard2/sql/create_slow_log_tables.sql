-- 慢查询/慢请求/前端慢资源持久化存储表
-- 创建时间: 2026-03-31

-- 1. 慢请求表 (slow_requests)
CREATE TABLE IF NOT EXISTS slow_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    request_date DATE NOT NULL COMMENT '请求日期',
    request_hour TINYINT NOT NULL COMMENT '请求小时(0-23)',

    -- 请求信息
    method VARCHAR(10) NOT NULL COMMENT 'HTTP方法(GET/POST/...)',
    path VARCHAR(500) NOT NULL COMMENT '请求路径',
    endpoint VARCHAR(200) COMMENT '端点名称',

    -- 性能指标
    duration_ms INT NOT NULL COMMENT '总耗时(毫秒)',
    status_code SMALLINT COMMENT 'HTTP状态码',

    -- 数据库指标
    db_queries INT DEFAULT 0 COMMENT '数据库查询次数',
    db_time_ms INT DEFAULT 0 COMMENT '数据库耗时(毫秒)',

    -- Redis指标
    redis_queries INT DEFAULT 0 COMMENT 'Redis查询次数',
    redis_time_ms INT DEFAULT 0 COMMENT 'Redis耗时(毫秒)',

    -- 扩展信息(JSON格式，可选)
    extra_info JSON COMMENT '扩展信息',

    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_request_date (request_date),
    INDEX idx_path (path(100)),
    INDEX idx_duration (duration_ms),
    INDEX idx_composite (request_date, duration_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='慢请求记录表';

-- 2. 慢查询表 (slow_queries)
CREATE TABLE IF NOT EXISTS slow_queries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    query_date DATE NOT NULL COMMENT '查询日期',
    query_hour TINYINT NOT NULL COMMENT '查询小时(0-23)',

    -- SQL信息
    sql_statement TEXT NOT NULL COMMENT 'SQL语句(前500字符)',
    sql_hash VARCHAR(64) COMMENT 'SQL语句MD5哈希(用于归类相同SQL)',
    sql_type VARCHAR(20) COMMENT 'SQL类型(SELECT/INSERT/UPDATE/DELETE)',

    -- 性能指标
    duration_ms INT NOT NULL COMMENT '执行耗时(毫秒)',

    -- 表信息(从SQL解析)
    table_name VARCHAR(100) COMMENT '主表名',

    -- 参数信息(可选)
    parameters TEXT COMMENT 'SQL参数(前200字符)',

    -- 扩展信息
    extra_info JSON COMMENT '扩展信息',

    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_query_date (query_date),
    INDEX idx_sql_hash (sql_hash),
    INDEX idx_duration (duration_ms),
    INDEX idx_table_name (table_name),
    INDEX idx_composite (query_date, duration_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='慢查询记录表';

-- 3. 前端慢资源表 (slow_frontend_resources)
CREATE TABLE IF NOT EXISTS slow_frontend_resources (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    resource_date DATE NOT NULL COMMENT '资源加载日期',
    resource_hour TINYINT NOT NULL COMMENT '资源加载小时(0-23)',

    -- 资源信息
    resource_type VARCHAR(20) NOT NULL COMMENT '资源类型(xhr/fetch/script/css/image/other)',
    url VARCHAR(1000) NOT NULL COMMENT '资源URL',
    url_path VARCHAR(500) COMMENT 'URL路径(用于归类)',

    -- 性能指标
    duration_ms INT NOT NULL COMMENT '加载耗时(毫秒)',
    transfer_size BIGINT COMMENT '传输大小(字节)',

    -- 页面信息
    page_url VARCHAR(500) COMMENT '所在页面URL',

    -- 扩展信息
    extra_info JSON COMMENT '扩展信息(如HTTP状态码、缓存状态等)',

    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_resource_date (resource_date),
    INDEX idx_resource_type (resource_type),
    INDEX idx_url_path (url_path(100)),
    INDEX idx_duration (duration_ms),
    INDEX idx_composite (resource_date, resource_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='前端慢资源加载记录表';
