"""
Dashboard2 - 登录认证路由

功能：
    - GET  /login  → 渲染登录页面
    - POST /login  → 校验用户名密码，写入 session
    - GET  /logout → 清除 session，重定向到 /login
"""

from flask import Blueprint, render_template, request, redirect, session, url_for
from sqlalchemy import create_engine, text
from werkzeug.security import check_password_hash
from gs2026.utils import config_util

auth_bp = Blueprint('auth', __name__)


def _get_auth_config():
    """获取认证配置"""
    config = config_util.load_config()
    return config.get('auth', {})


def _get_engine():
    """获取数据库引擎"""
    url = config_util.get_config('common.url')
    return create_engine(url)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    auth_config = _get_auth_config()

    # 登录功能未启用，直接跳转首页
    if not auth_config.get('enabled', False):
        return redirect('/')

    # 已登录，跳转首页
    if session.get('logged_in'):
        return redirect('/')

    if request.method == 'GET':
        return render_template('login.html')

    # POST 登录校验
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if not username or not password:
        return render_template('login.html', error='请输入用户名和密码')

    # 查询数据库
    service_type = auth_config.get('service_type', 'gs2026')

    try:
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    'SELECT password FROM accounts '
                    'WHERE username = :u AND service_type = :st AND is_locked = 0'
                ),
                {'u': username, 'st': service_type}
            )
            row = result.fetchone()
    except Exception as e:
        print(f"[Auth] 数据库查询失败: {e}")
        return render_template('login.html', error='系统异常，请稍后重试')

    if row and check_password_hash(row[0], password):
        # 登录成功（会话cookie，关闭浏览器即过期）
        session.permanent = False
        session['logged_in'] = True
        session['username'] = username
        return redirect('/')
    else:
        return render_template('login.html', error='用户名或密码错误')


@auth_bp.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect('/login')
