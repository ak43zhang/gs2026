"""创建挑战系统数据库表"""
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
url = url.replace('charset=utf8&', 'charset=utf8mb4&').replace('charset=utf8"', 'charset=utf8mb4"')
if 'charset=' not in url:
    url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
engine = create_engine(url)

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_challenges (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL COMMENT '用户名',
            name VARCHAR(200) NOT NULL COMMENT '挑战名称',
            target_days INT NOT NULL DEFAULT 21 COMMENT '目标天数',
            description VARCHAR(500) DEFAULT '' COMMENT '描述',
            color VARCHAR(16) DEFAULT '#667eea' COMMENT '主题色',
            icon VARCHAR(32) DEFAULT '🎯' COMMENT '图标',
            status TINYINT DEFAULT 1 COMMENT '0=暂停,1=进行中,2=已完成',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_deleted TINYINT DEFAULT 0,
            KEY idx_user (username),
            KEY idx_status (username, status),
            UNIQUE KEY uk_name (username, name, is_deleted)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户挑战主表'
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_challenge_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            challenge_id INT NOT NULL,
            log_date DATE NOT NULL COMMENT '打卡日期',
            notes VARCHAR(500) DEFAULT '' COMMENT '当日备注',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_deleted TINYINT DEFAULT 0,
            UNIQUE KEY uk_challenge_date (username, challenge_id, log_date, is_deleted),
            KEY idx_challenge (username, challenge_id),
            KEY idx_date (username, log_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='挑战打卡记录'
    """))
    conn.commit()
    print('OK: tables created')
