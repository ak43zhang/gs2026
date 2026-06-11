"""知识库 API 路由"""

from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

kb_bp = Blueprint('knowledge_base', __name__, url_prefix='/kb')


def _get_engine():
    from gs2026.utils.mysql_util import get_mysql_tool
    return get_mysql_tool().engine


@kb_bp.route('/')
def kb_page():
    """知识库页面"""
    return render_template('kb.html')


@kb_bp.route('/api/entries', methods=['GET'])
def list_entries():
    """获取条目列表（支持搜索和标签筛选）"""
    try:
        q = request.args.get('q', '').strip()
        tag = request.args.get('tag', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 50))
        offset = (page - 1) * page_size

        engine = _get_engine()
        with engine.connect() as conn:
            where = "is_deleted = 0"
            params = {'limit': page_size, 'offset': offset}

            if q:
                where += " AND MATCH(title, content) AGAINST(:q IN BOOLEAN MODE)"
                params['q'] = q
            if tag:
                where += " AND FIND_IN_SET(:tag, tags) > 0"
                params['tag'] = tag

            # 查询列表
            sql = text(f"""
                SELECT id, title, tags, 
                       LEFT(content, 200) as summary,
                       created_at, updated_at
                FROM kb_entry
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
            """)
            rows = conn.execute(sql, params).fetchall()

            # 查询总数
            count_sql = text(f"SELECT COUNT(*) FROM kb_entry WHERE {where}")
            total = conn.execute(count_sql, params).scalar()

            items = []
            for r in rows:
                items.append({
                    'id': r[0],
                    'title': r[1],
                    'tags': r[2].split(',') if r[2] else [],
                    'summary': r[3] or '',
                    'created_at': str(r[4]),
                    'updated_at': str(r[5])
                })

            return jsonify(success=True, items=items, total=total, page=page)
    except Exception as e:
        logger.error(f"[KB] list_entries error: {e}")
        return jsonify(success=False, message=str(e)), 500


@kb_bp.route('/api/entries/<int:entry_id>', methods=['GET'])
def get_entry(entry_id):
    """获取条目详情"""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            sql = text("SELECT id, title, content, tags, created_at, updated_at FROM kb_entry WHERE id=:id AND is_deleted=0")
            row = conn.execute(sql, {'id': entry_id}).fetchone()
            if not row:
                return jsonify(success=False, message='条目不存在'), 404
            return jsonify(success=True, data={
                'id': row[0],
                'title': row[1],
                'content': row[2] or '',
                'tags': row[3].split(',') if row[3] else [],
                'created_at': str(row[4]),
                'updated_at': str(row[5])
            })
    except Exception as e:
        logger.error(f"[KB] get_entry error: {e}")
        return jsonify(success=False, message=str(e)), 500


@kb_bp.route('/api/entries', methods=['POST'])
def create_entry():
    """新建条目"""
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title', '').strip()
        content = data.get('content', '')
        tags = ','.join([t.strip() for t in data.get('tags', []) if t.strip()])

        if not title:
            return jsonify(success=False, message='标题不能为空'), 400

        engine = _get_engine()
        with engine.connect() as conn:
            sql = text("INSERT INTO kb_entry (title, content, tags) VALUES (:title, :content, :tags)")
            result = conn.execute(sql, {'title': title, 'content': content, 'tags': tags})
            conn.commit()
            return jsonify(success=True, id=result.lastrowid, message='创建成功')
    except Exception as e:
        logger.error(f"[KB] create_entry error: {e}")
        return jsonify(success=False, message=str(e)), 500


@kb_bp.route('/api/entries/<int:entry_id>', methods=['PUT'])
def update_entry(entry_id):
    """编辑条目"""
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title', '').strip()
        content = data.get('content', '')
        tags = ','.join([t.strip() for t in data.get('tags', []) if t.strip()])

        if not title:
            return jsonify(success=False, message='标题不能为空'), 400

        engine = _get_engine()
        with engine.connect() as conn:
            sql = text("UPDATE kb_entry SET title=:title, content=:content, tags=:tags WHERE id=:id AND is_deleted=0")
            result = conn.execute(sql, {'title': title, 'content': content, 'tags': tags, 'id': entry_id})
            conn.commit()
            if result.rowcount == 0:
                return jsonify(success=False, message='条目不存在'), 404
            return jsonify(success=True, message='更新成功')
    except Exception as e:
        logger.error(f"[KB] update_entry error: {e}")
        return jsonify(success=False, message=str(e)), 500


@kb_bp.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    """删除条目（软删除）"""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            sql = text("UPDATE kb_entry SET is_deleted=1 WHERE id=:id")
            result = conn.execute(sql, {'id': entry_id})
            conn.commit()
            if result.rowcount == 0:
                return jsonify(success=False, message='条目不存在'), 404
            return jsonify(success=True, message='删除成功')
    except Exception as e:
        logger.error(f"[KB] delete_entry error: {e}")
        return jsonify(success=False, message=str(e)), 500


@kb_bp.route('/api/tags', methods=['GET'])
def list_tags():
    """获取所有已用标签"""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            sql = text("SELECT tags FROM kb_entry WHERE is_deleted=0 AND tags != ''")
            rows = conn.execute(sql).fetchall()
            tag_set = set()
            for r in rows:
                for t in r[0].split(','):
                    t = t.strip()
                    if t:
                        tag_set.add(t)
            return jsonify(success=True, tags=sorted(tag_set))
    except Exception as e:
        logger.error(f"[KB] list_tags error: {e}")
        return jsonify(success=False, message=str(e)), 500
