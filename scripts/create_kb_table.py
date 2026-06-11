"""创建知识库表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import text
from gs2026.utils.mysql_util import get_mysql_tool

mysql_tool = get_mysql_tool()

sql = text("""
CREATE TABLE IF NOT EXISTS kb_entry (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content MEDIUMTEXT,
    tags VARCHAR(200) DEFAULT '',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    is_deleted TINYINT DEFAULT 0,
    FULLTEXT idx_search (title, content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""")

with mysql_tool.engine.connect() as conn:
    conn.execute(sql)
    conn.commit()
    print('Table kb_entry created successfully')
