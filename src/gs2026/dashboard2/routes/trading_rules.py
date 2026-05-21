"""
交易门规路由

API:
    GET  /api/trading-rules/list              → 门规列表
    POST /api/trading-rules/create            → 新增门规
    POST /api/trading-rules/update/<id>       → 修改门规
    POST /api/trading-rules/delete/<id>       → 废除门规
    POST /api/trading-rules/reorder           → 排序
    POST /api/trading-rules/violate/<id>      → 记录犯规
    GET  /api/trading-rules/violations        → 犯规记录
"""
from datetime import date as date_type
from flask import Blueprint, request, session, jsonify
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

rules_bp = Blueprint('trading_rules', __name__)

CATEGORIES = ['铁律', '买入戒律', '卖出戒律', '心法']
CN_NUMBERS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖', '拾',
              '拾壹', '拾贰', '拾叁', '拾肆', '拾伍', '拾陆', '拾柒', '拾捌', '拾玖', '贰拾']


def _get_engine():
    url = config_util.get_config('common.url')
    url = url.replace('charset=utf8&', 'charset=utf8mb4&').replace('charset=utf8"', 'charset=utf8mb4"')
    if 'charset=' not in url:
        url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
    return create_engine(url)


def _current_user():
    return session.get('username')


@rules_bp.route('/api/trading-rules/list')
def rules_list():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT id, category, level, sort_order, content, is_active, created_at '
            'FROM user_trading_rules '
            'WHERE username = :u '
            'ORDER BY is_active DESC, FIELD(category, "铁律","买入戒律","卖出戒律","心法"), sort_order, id'
        ), {'u': username})
        cols = r.keys()
        rules = [dict(zip(cols, row)) for row in r.fetchall()]

        # 添加中文序号
        active_idx = 0
        for rule in rules:
            rule['created_at'] = str(rule['created_at'])
            if rule['is_active']:
                active_idx += 1
                rule['cn_number'] = CN_NUMBERS[active_idx] if active_idx < len(CN_NUMBERS) else str(active_idx)
            else:
                rule['cn_number'] = '—'

        # 本月犯规统计
        month = date_type.today().strftime('%Y-%m')
        year_val = int(month.split('-')[0])
        month_val = int(month.split('-')[1])
        r2 = conn.execute(text(
            'SELECT COUNT(*) FROM user_rule_violations '
            'WHERE username = :u AND YEAR(trade_date) = :y AND MONTH(trade_date) = :m'
        ), {'u': username, 'y': year_val, 'm': month_val})
        violations_this_month = r2.fetchone()[0]

    return jsonify(success=True, data=rules, categories=CATEGORIES,
                   violations_this_month=violations_this_month)


@rules_bp.route('/api/trading-rules/create', methods=['POST'])
def rules_create():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    content = (body.get('content') or '').strip()
    if not content:
        return jsonify(success=False, message='门规内容不能为空'), 400

    category = body.get('category', '铁律')
    if category not in CATEGORIES:
        category = '铁律'
    level = int(body.get('level', 1))

    engine = _get_engine()
    with engine.connect() as conn:
        # 获取当前分类最大排序号
        r = conn.execute(text(
            'SELECT COALESCE(MAX(sort_order), 0) FROM user_trading_rules '
            'WHERE username = :u AND category = :cat'
        ), {'u': username, 'cat': category})
        max_order = r.fetchone()[0]

        conn.execute(text(
            'INSERT INTO user_trading_rules (username, category, level, sort_order, content) '
            'VALUES (:u, :cat, :lvl, :ord, :content)'
        ), {'u': username, 'cat': category, 'lvl': level, 'ord': max_order + 1, 'content': content})
        conn.commit()

    return jsonify(success=True, message='门规已立')


@rules_bp.route('/api/trading-rules/update/<int:rid>', methods=['POST'])
def rules_update(rid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    sets, params = [], {'id': rid, 'u': username}

    if 'content' in body:
        sets.append('content = :content')
        params['content'] = body['content'].strip()
    if 'category' in body and body['category'] in CATEGORIES:
        sets.append('category = :category')
        params['category'] = body['category']
    if 'level' in body:
        sets.append('level = :level')
        params['level'] = int(body['level'])
    if 'is_active' in body:
        sets.append('is_active = :is_active')
        params['is_active'] = int(body['is_active'])

    if not sets:
        return jsonify(success=False, message='无更新字段'), 400

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            f'UPDATE user_trading_rules SET {", ".join(sets)} '
            f'WHERE id = :id AND username = :u'
        ), params)
        conn.commit()

    return jsonify(success=True, message='已修改')


@rules_bp.route('/api/trading-rules/delete/<int:rid>', methods=['POST'])
def rules_delete(rid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            'UPDATE user_trading_rules SET is_active = 0 WHERE id = :id AND username = :u'
        ), {'id': rid, 'u': username})
        conn.commit()

    return jsonify(success=True, message='门规已废除')


@rules_bp.route('/api/trading-rules/reorder', methods=['POST'])
def rules_reorder():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    order_list = body.get('order', [])  # [{id: 1, sort_order: 0}, ...]

    if not order_list:
        return jsonify(success=False, message='排序数据为空'), 400

    engine = _get_engine()
    with engine.connect() as conn:
        for item in order_list:
            # 支持跨类别拖拽：同时更新 sort_order 和 category
            if 'category' in item:
                conn.execute(text(
                    'UPDATE user_trading_rules SET sort_order = :ord, category = :cat '
                    'WHERE id = :id AND username = :u'
                ), {'ord': item['sort_order'], 'cat': item['category'], 'id': item['id'], 'u': username})
            else:
                conn.execute(text(
                    'UPDATE user_trading_rules SET sort_order = :ord '
                    'WHERE id = :id AND username = :u'
                ), {'ord': item['sort_order'], 'id': item['id'], 'u': username})
        conn.commit()

    return jsonify(success=True, message='排序已更新')


@rules_bp.route('/api/trading-rules/violate/<int:rid>', methods=['POST'])
def rules_violate(rid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    trade_date = body.get('date', str(date_type.today()))
    notes = body.get('notes', '')
    punishment = body.get('punishment', '')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT id FROM user_trading_rules WHERE id = :id AND username = :u'
        ), {'id': rid, 'u': username})
        if not r.fetchone():
            return jsonify(success=False, message='门规不存在'), 404

        conn.execute(text(
            'INSERT INTO user_rule_violations (username, rule_id, trade_date, notes, punishment) '
            'VALUES (:u, :rid, :d, :notes, :punishment)'
        ), {'u': username, 'rid': rid, 'd': trade_date, 'notes': notes, 'punishment': punishment})
        conn.commit()

    return jsonify(success=True, message='犯规已记录，谨记戒律！')


@rules_bp.route('/api/trading-rules/punished/<int:vid>', methods=['POST'])
def rules_punished(vid):
    """标记惩戒完成"""
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            'UPDATE user_rule_violations SET is_punished = 1, punished_at = NOW() '
            'WHERE id = :id AND username = :u'
        ), {'id': vid, 'u': username})
        conn.commit()

    return jsonify(success=True, message='惩戒已完成，引以为戒')


@rules_bp.route('/api/trading-rules/violations')
def rules_violations():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    month = request.args.get('month', date_type.today().strftime('%Y-%m'))
    year_val = int(month.split('-')[0])
    month_val = int(month.split('-')[1])

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT v.id, v.rule_id, v.rule_ids, v.trade_date, v.notes, v.punishment, '
            'v.is_punished, v.punished_at, v.created_at, r.content, r.category '
            'FROM user_rule_violations v '
            'JOIN user_trading_rules r ON v.rule_id = r.id '
            'WHERE v.username = :u AND YEAR(v.trade_date) = :y AND MONTH(v.trade_date) = :m '
            'ORDER BY v.trade_date DESC, v.id DESC'
        ), {'u': username, 'y': year_val, 'm': month_val})
        cols = r.keys()
        violations = [dict(zip(cols, row)) for row in r.fetchall()]
        
        # 查询所有门规用于解析 rule_ids
        r_rules = conn.execute(text(
            'SELECT id, content, category FROM user_trading_rules WHERE username = :u'
        ), {'u': username})
        rules_map = {row[0]: {'content': row[1], 'category': row[2]} for row in r_rules.fetchall()}
        
        for v in violations:
            v['trade_date'] = str(v['trade_date'])
            v['created_at'] = str(v['created_at'])
            v['punished_at'] = str(v['punished_at']) if v['punished_at'] else None
            # 解析 rule_ids，构建违反门规列表
            rule_ids_str = v.get('rule_ids') or str(v['rule_id'])
            violated_rules = []
            for rid_str in rule_ids_str.split(','):
                rid = int(rid_str.strip())
                rule = rules_map.get(rid)
                if rule:
                    violated_rules.append({'id': rid, 'content': rule['content'], 'category': rule['category']})
            v['violated_rules'] = violated_rules

    return jsonify(success=True, data=violations)


@rules_bp.route('/api/trading-rules/violate-batch', methods=['POST'])
def rules_violate_batch():
    """批量记录犯规（一次触犯多条门规 → 单条记录）"""
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    rule_ids = body.get('rule_ids', [])
    notes = (body.get('notes') or '').strip()
    punishment = (body.get('punishment') or '').strip()
    trade_date = body.get('date') or date_type.today().strftime('%Y-%m-%d')

    if not rule_ids:
        return jsonify(success=False, message='请至少选择一条门规'), 400

    engine = _get_engine()
    with engine.connect() as conn:
        # 验证所有门规存在且属于当前用户
        for rid in rule_ids:
            r = conn.execute(text(
                'SELECT id FROM user_trading_rules WHERE id = :id AND username = :u'
            ), {'id': rid, 'u': username})
            if not r.fetchone():
                return jsonify(success=False, message='门规不存在'), 404

        # 【修改】创建单条记录，rule_id存第一条，rule_ids存所有
        rule_ids_str = ','.join(str(rid) for rid in rule_ids)
        conn.execute(text(
            'INSERT INTO user_rule_violations (username, rule_id, rule_ids, trade_date, notes, punishment) '
            'VALUES (:u, :rid, :rids, :d, :notes, :punishment)'
        ), {
            'u': username, 'rid': rule_ids[0], 'rids': rule_ids_str,
            'd': trade_date, 'notes': notes, 'punishment': punishment
        })
        conn.commit()

    return jsonify(success=True, message=f'已记录犯规（违反 {len(rule_ids)} 条门规），谨记戒律！')


@rules_bp.route('/api/trading-rules/violation/delete/<int:vid>', methods=['POST'])
def rules_violation_delete(vid):
    """删除犯规记录"""
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT id FROM user_rule_violations WHERE id = :id AND username = :u'
        ), {'id': vid, 'u': username})
        if not r.fetchone():
            return jsonify(success=False, message='记录不存在'), 404

        conn.execute(text(
            'DELETE FROM user_rule_violations WHERE id = :id AND username = :u'
        ), {'id': vid, 'u': username})
        conn.commit()

    return jsonify(success=True, message='犯规记录已删除')
