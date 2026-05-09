#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GS2026 账号管理工具

功能说明:
    管理 GS2026 Dashboard 登录账号（存储在 MySQL accounts 表）

使用方法:
    python tools/auth_manager.py add <username> <password>     # 添加账号
    python tools/auth_manager.py list                          # 列出所有账号
    python tools/auth_manager.py reset <username> <new_pwd>    # 重置密码
    python tools/auth_manager.py delete <username>             # 删除账号

依赖配置:
    - common.url  - MySQL 连接 URL

作者: GS2026
版本: 1.0.0
日期: 2026-05-09
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash
from gs2026.utils import config_util

SERVICE_TYPE = 'gs2026'


def get_engine():
    """获取数据库引擎"""
    url = config_util.get_config('common.url')
    return create_engine(url)


def add_account(username: str, password: str):
    """添加账号"""
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    engine = get_engine()

    with engine.connect() as conn:
        # 检查是否已存在
        result = conn.execute(
            text('SELECT id FROM accounts WHERE username = :u AND service_type = :st'),
            {'u': username, 'st': SERVICE_TYPE}
        )
        if result.fetchone():
            print(f'[ERROR] 账号 {username} 已存在（service_type={SERVICE_TYPE}）')
            return

        conn.execute(
            text('INSERT INTO accounts (username, password, service_type) VALUES (:u, :p, :st)'),
            {'u': username, 'p': password_hash, 'st': SERVICE_TYPE}
        )
        conn.commit()
        print(f'[OK] 账号 {username} 添加成功')


def list_accounts():
    """列出所有账号"""
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                'SELECT username, is_locked, created_at, last_used '
                'FROM accounts WHERE service_type = :st ORDER BY id'
            ),
            {'st': SERVICE_TYPE}
        )
        rows = result.fetchall()

    if not rows:
        print('暂无 GS2026 账号')
        return

    print(f'\n{"用户名":<16} {"状态":<8} {"创建时间":<20} {"最后使用"}')
    print('-' * 70)
    for row in rows:
        status = '[LOCKED]' if row[1] else '[OK]'
        created = str(row[2])[:19] if row[2] else '-'
        last_used = str(row[3])[:19] if row[3] else '-'
        print(f'{row[0]:<16} {status:<8} {created:<20} {last_used}')
    print(f'\n共 {len(rows)} 个账号')


def delete_account(username: str):
    """删除账号"""
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text('DELETE FROM accounts WHERE username = :u AND service_type = :st'),
            {'u': username, 'st': SERVICE_TYPE}
        )
        conn.commit()

        if result.rowcount > 0:
            print(f'[OK] 账号 {username} 已删除')
        else:
            print(f'[ERROR] 账号 {username} 不存在（service_type={SERVICE_TYPE}）')


def reset_password(username: str, new_password: str):
    """重置密码"""
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text('UPDATE accounts SET password = :p WHERE username = :u AND service_type = :st'),
            {'p': password_hash, 'u': username, 'st': SERVICE_TYPE}
        )
        conn.commit()

        if result.rowcount > 0:
            print(f'[OK] 账号 {username} 密码已重置')
        else:
            print(f'[ERROR] 账号 {username} 不存在（service_type={SERVICE_TYPE}）')


def print_usage():
    """打印使用说明"""
    print(__doc__)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'add' and len(sys.argv) == 4:
        add_account(sys.argv[2], sys.argv[3])
    elif cmd == 'list':
        list_accounts()
    elif cmd == 'delete' and len(sys.argv) == 3:
        delete_account(sys.argv[2])
    elif cmd == 'reset' and len(sys.argv) == 4:
        reset_password(sys.argv[2], sys.argv[3])
    else:
        print_usage()
        sys.exit(1)
