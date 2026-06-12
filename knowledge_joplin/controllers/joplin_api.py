import json
import time
import logging
from datetime import datetime, timezone
from dateutil import parser as dateparser

from odoo import http
from odoo.http import request
from odoo.tools import html2plaintext

import markdown

_logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = [
    'fenced_code', 'codehilite', 'tables', 'toc', 'nl2br', 'extra',
]

JOPLIN_ITEM_TYPES = {
    'note': 1, 'folder': 2, 'setting': 3, 'resource': 4, 'tag': 5,
    'note_tag': 6, 'search': 7, 'alarm': 8, 'master_key': 9,
    'item_change': 10, 'note_resource': 11, 'resource_local_state': 12,
    'revision': 13, 'migration': 14, 'smart_filter': 15, 'command': 16,
}

ITEM_TYPE_NAMES = {v: k for k, v in JOPLIN_ITEM_TYPES.items()}


def _to_ms_timestamp(dt):
    if not dt:
        return 0
    if isinstance(dt, str):
        dt = dateparser.parse(dt)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 1000)


def _from_ms_timestamp(ms):
    if not ms:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _get_user():
    auth_header = request.httprequest.headers.get('X-API-AUTH', '')
    if auth_header:
        user = request.env['joplin.api.token'].sudo().authenticate(auth_header)
        if user:
            request.update_env(user=user.id)
            return user
    token = request.params.get('token')
    if token:
        user = request.env['joplin.api.token'].sudo().authenticate(token)
        if user:
            request.update_env(user=user.id)
            return user
    return request.env['res.users']


def _paginate(Model, domain, params):
    page = int(params.get('page', 1))
    limit = min(int(params.get('limit', 100)), 100)
    offset = (page - 1) * limit
    order_by = params.get('order_by', 'updated_time')
    order_dir = params.get('order_dir', 'DESC')
    order = f'{order_by} {order_dir}' if order_by else 'updated_time desc'

    total = Model.search_count(domain)
    records = Model.search(domain, offset=offset, limit=limit, order=order)
    has_more = (offset + limit) < total

    return records, has_more


def _fields_filter(record, fields_param):
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {f: record[f] for f in field_list if f in record}
    return {
        'id': record['joplin_id'],
        'parent_id': record.get('parent_id', ''),
        'title': record.get('name') or record.get('title', ''),
    }


def _note_to_dict(note, fields_param=None):
    note = note.sudo()
    data = {
        'id': note.joplin_id,
        'parent_id': note.folder_id.joplin_id if note.folder_id else '',
        'title': note.title,
        'body': note.body or '',
        'created_time': _to_ms_timestamp(note.created_time),
        'updated_time': _to_ms_timestamp(note.updated_time),
        'is_conflict': 1 if note.is_conflict else 0,
        'latitude': note.latitude or 0.0,
        'longitude': note.longitude or 0.0,
        'altitude': note.altitude or 0.0,
        'author': note.author or '',
        'source_url': note.source_url or '',
        'is_todo': 1 if note.is_todo else 0,
        'todo_due': _to_ms_timestamp(note.todo_due) if note.todo_due else 0,
        'todo_completed': _to_ms_timestamp(note.todo_completed) if note.todo_completed else 0,
        'source': note.source or '',
        'source_application': note.source_application or '',
        'application_data': note.application_data or '',
        'order': note.order or 0,
        'user_created_time': _to_ms_timestamp(note.user_created_time) if note.user_created_time else _to_ms_timestamp(note.created_time),
        'user_updated_time': _to_ms_timestamp(note.user_updated_time) if note.user_updated_time else _to_ms_timestamp(note.updated_time),
        'encryption_cipher_text': note.encryption_cipher_text or '',
        'encryption_applied': 1 if note.encryption_applied else 0,
        'markup_language': note.markup_language or 1,
        'is_shared': 1 if note.is_shared else 0,
        'share_id': note.share_id or '',
        'conflict_original_id': note.conflict_original_id or '',
        'master_key_id': note.master_key_id or '',
        'user_data': '',
        'deleted_time': _to_ms_timestamp(note.deleted_time) if note.deleted_time else 0,
        'active': 1 if note.active else 0,
    }
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {k: v for k, v in data.items() if k in field_list}
    return data


def _folder_to_dict(folder, fields_param=None, include_children=True):
    folder = folder.sudo()
    data = {
        'id': folder.joplin_id,
        'title': folder.name,
        'created_time': _to_ms_timestamp(folder.created_time),
        'updated_time': _to_ms_timestamp(folder.updated_time),
        'user_created_time': _to_ms_timestamp(folder.user_created_time) if folder.user_created_time else _to_ms_timestamp(folder.created_time),
        'user_updated_time': _to_ms_timestamp(folder.user_updated_time) if folder.user_updated_time else _to_ms_timestamp(folder.updated_time),
        'encryption_cipher_text': folder.encryption_cipher_text or '',
        'encryption_applied': 1 if folder.encryption_applied else 0,
        'parent_id': folder.parent_id.joplin_id if folder.parent_id else '',
        'is_shared': 1 if folder.is_shared else 0,
        'share_id': folder.share_id or '',
        'master_key_id': folder.master_key_id or '',
        'icon': folder.icon or '',
        'user_data': '',
        'deleted_time': 0,
    }
    if include_children:
        children = request.env['joplin.folder'].search([('parent_id', '=', folder.id)])
        if children:
            data['children'] = [_folder_to_dict(c, fields_param, True) for c in children]
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {k: v for k, v in data.items() if k in field_list}
    return data


def _tag_to_dict(tag, fields_param=None):
    tag = tag.sudo()
    data = {
        'id': tag.joplin_id,
        'title': tag.name,
        'created_time': _to_ms_timestamp(tag.created_time),
        'updated_time': _to_ms_timestamp(tag.updated_time),
        'user_created_time': _to_ms_timestamp(tag.user_created_time) if tag.user_created_time else _to_ms_timestamp(tag.created_time),
        'user_updated_time': _to_ms_timestamp(tag.user_updated_time) if tag.user_updated_time else _to_ms_timestamp(tag.updated_time),
        'encryption_cipher_text': tag.encryption_cipher_text or '',
        'encryption_applied': 1 if tag.encryption_applied else 0,
        'is_shared': 1 if tag.is_shared else 0,
        'parent_id': tag.parent_id or '',
        'user_data': '',
    }
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {k: v for k, v in data.items() if k in field_list}
    return data


def _resource_to_dict(res, fields_param=None):
    res = res.sudo()
    data = {
        'id': res.joplin_id,
        'title': res.name or '',
        'mime': res.mime or '',
        'filename': res.filename or '',
        'created_time': _to_ms_timestamp(res.created_time),
        'updated_time': _to_ms_timestamp(res.updated_time),
        'user_created_time': _to_ms_timestamp(res.user_created_time) if res.user_created_time else _to_ms_timestamp(res.created_time),
        'user_updated_time': _to_ms_timestamp(res.user_updated_time) if res.user_updated_time else _to_ms_timestamp(res.updated_time),
        'file_extension': res.file_extension or '',
        'encryption_cipher_text': res.encryption_cipher_text or '',
        'encryption_applied': 1 if res.encryption_applied else 0,
        'encryption_blob_encrypted': 1 if res.encryption_blob_encrypted else 0,
        'size': res.file_size or 0,
        'is_shared': 1 if res.is_shared else 0,
        'share_id': res.share_id or '',
        'master_key_id': res.master_key_id or '',
        'user_data': '',
        'blob_updated_time': _to_ms_timestamp(res.blob_updated_time) if res.blob_updated_time else 0,
        'ocr_text': res.ocr_text or '',
        'ocr_details': res.ocr_details or '',
        'ocr_status': res.ocr_status or 0,
        'ocr_error': res.ocr_error or '',
        'ocr_driver_id': res.ocr_driver_id or 0,
    }
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {k: v for k, v in data.items() if k in field_list}
    return data


def _revision_to_dict(rev, fields_param=None):
    rev = rev.sudo()
    data = {
        'id': rev.joplin_id,
        'parent_id': rev.parent_id or '',
        'item_type': rev.item_type or 1,
        'item_id': rev.item_id or '',
        'item_updated_time': _to_ms_timestamp(rev.item_updated_time) if rev.item_updated_time else 0,
        'title_diff': rev.title_diff or '',
        'body_diff': rev.body_diff or '',
        'metadata_diff': rev.metadata_diff or '',
        'encryption_cipher_text': rev.encryption_cipher_text or '',
        'encryption_applied': 1 if rev.encryption_applied else 0,
        'updated_time': _to_ms_timestamp(rev.updated_time),
        'created_time': _to_ms_timestamp(rev.created_time),
    }
    if fields_param:
        field_list = [f.strip() for f in fields_param.split(',')]
        return {k: v for k, v in data.items() if k in field_list}
    return data


class JoplinApi(http.Controller):

    def _auth(self):
        user = _get_user()
        if not user or not user.id:
            return http.Response(
                json.dumps({'error': 'Authentication required'}),
                status=401,
                content_type='application/json',
            )
        return None

    def _response(self, data, status=200):
        return http.Response(
            json.dumps(data, default=str),
            status=status,
            content_type='application/json',
        )

    def _paginated_response(self, items, has_more):
        return self._response({
            'items': items,
            'has_more': has_more,
        })

    # ---- PING ----

    @http.route('/joplin/ping', type='http', auth='none', methods=['GET'], csrf=False)
    def ping(self, **params):
        return http.Response(
            'JoplinClipperServer',
            status=200,
            content_type='text/plain',
        )

    @http.route('/joplin/api/ping', type='http', auth='none', methods=['GET'], csrf=False)
    def api_ping(self, **params):
        return http.Response(
            'JoplinClipperServer',
            status=200,
            content_type='text/plain',
        )

    @http.route('/joplin/api/sessions', type='http', auth='none', methods=['POST'], csrf=False)
    def create_session(self, **params):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params

        email = data.get('email', '')
        password = data.get('password', '')

        if not email or not password:
            return self._response({'error': 'Email and password required'}, 400)

        auth_info = request.env['res.users'].sudo().authenticate(
            request.env.cr.dbname,
            {'type': 'password', 'login': email, 'password': password},
            {})
        uid = auth_info.get('uid') if auth_info else False
        if not uid:
            return self._response({'error': 'Invalid credentials'}, 401)

        user = request.env['res.users'].sudo().browse(uid)

        token = request.env['joplin.api.token'].sudo().search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ], limit=1)
        if not token:
            token = request.env['joplin.api.token'].sudo().create({
                'name': 'Joplin session - ' + user.name,
                'user_id': user.id,
            })

        return self._response({
            'id': token.token,
            'token': token.token,
        })

    # ---- NOTES ----

    @http.route(['/joplin/notes', '/joplin/api/notes'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_notes(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Note = request.env['joplin.note']
        domain = [('active', '=', True)]
        if not params.get('include_deleted'):
            domain.append(('active', '=', True))
        if not params.get('include_conflicts'):
            domain.append(('is_conflict', '=', False))
        if params.get('parent_id'):
            domain.append(('folder_id.joplin_id', '=', params['parent_id']))
        records, has_more = _paginate(Note, domain, params)
        items = [_note_to_dict(n, params.get('fields')) for n in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/notes/<string:joplin_id>', '/joplin/api/notes/<string:joplin_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_note(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        return self._response(_note_to_dict(note, params.get('fields')))

    @http.route(['/joplin/notes/<string:joplin_id>/tags', '/joplin/api/notes/<string:joplin_id>/tags'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_note_tags(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        items = [_tag_to_dict(t, params.get('fields')) for t in note.tag_ids]
        return self._paginated_response(items, False)

    @http.route(['/joplin/notes/<string:joplin_id>/resources', '/joplin/api/notes/<string:joplin_id>/resources'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_note_resources(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        items = [_resource_to_dict(r, params.get('fields')) for r in note.resource_ids]
        return self._paginated_response(items, False)

    @http.route(['/joplin/notes', '/joplin/api/notes'], type='http', auth='none', methods=['POST'], csrf=False)
    def create_note(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params

        vals = {'title': data.get('title', 'Untitled')}
        if data.get('body'):
            vals['body'] = data['body']
        elif data.get('body_html'):
            vals['body'] = html2plaintext(data['body_html'])
            vals['markup_language'] = 0

        if data.get('parent_id'):
            folder = request.env['joplin.folder'].search([('joplin_id', '=', data['parent_id'])], limit=1)
            if folder:
                vals['folder_id'] = folder.id

        if data.get('id'):
            vals['joplin_id'] = data['id']
        if data.get('is_todo'):
            vals['is_todo'] = bool(data['is_todo'])
        if data.get('todo_due'):
            vals['todo_due'] = _from_ms_timestamp(data['todo_due'])
        if data.get('todo_completed'):
            vals['todo_completed'] = _from_ms_timestamp(data['todo_completed'])
        if data.get('author'):
            vals['author'] = data['author']
        if data.get('source_url'):
            vals['source_url'] = data['source_url']
        if data.get('latitude'):
            vals['latitude'] = float(data['latitude'])
        if data.get('longitude'):
            vals['longitude'] = float(data['longitude'])
        if data.get('altitude'):
            vals['altitude'] = float(data['altitude'])
        if data.get('order'):
            vals['order'] = float(data['order'])
        if data.get('markup_language') is not None:
            vals['markup_language'] = int(data['markup_language'])
        if data.get('source'):
            vals['source'] = data['source']
        if data.get('source_application'):
            vals['source_application'] = data['source_application']

        try:
            note = request.env['joplin.note'].create(vals)
            return self._response(_note_to_dict(note), 201)
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/notes/<string:joplin_id>', '/joplin/api/notes/<string:joplin_id>'], type='http', auth='none', methods=['PUT'], csrf=False)
    def update_note(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params

        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)

        vals = {}
        for key, odoo_key in [
            ('title', 'title'), ('body', 'body'), ('author', 'author'),
            ('source_url', 'source_url'), ('source', 'source'),
            ('source_application', 'source_application'),
            ('application_data', 'application_data'),
        ]:
            if key in data:
                vals[odoo_key] = data[key]

        if 'parent_id' in data:
            folder = request.env['joplin.folder'].search([('joplin_id', '=', data['parent_id'])], limit=1)
            vals['folder_id'] = folder.id if folder else False
        if 'is_todo' in data:
            vals['is_todo'] = bool(data['is_todo'])
        if 'todo_due' in data:
            vals['todo_due'] = _from_ms_timestamp(data['todo_due'])
        if 'todo_completed' in data:
            vals['todo_completed'] = _from_ms_timestamp(data['todo_completed'])
        if 'latitude' in data:
            vals['latitude'] = float(data['latitude'])
        if 'longitude' in data:
            vals['longitude'] = float(data['longitude'])
        if 'altitude' in data:
            vals['altitude'] = float(data['altitude'])
        if 'order' in data:
            vals['order'] = float(data['order'])
        if 'markup_language' in data:
            vals['markup_language'] = int(data['markup_language'])
        if 'is_conflict' in data:
            vals['is_conflict'] = bool(data['is_conflict'])

        try:
            note.write(vals)
            return self._response(_note_to_dict(note))
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/notes/<string:joplin_id>', '/joplin/api/notes/<string:joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_note(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        if params.get('permanent') == '1':
            note.unlink()
        else:
            note.write({'active': False})
        return self._response({'deleted': True})

    @http.route(['/joplin/notes/<string:joplin_id>/revisions', '/joplin/api/notes/<string:joplin_id>/revisions'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_note_revisions(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        note = request.env['joplin.note'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        note.revision_ids.unlink()
        return self._response({'deleted': True})

    # ---- FOLDERS ----

    @http.route(['/joplin/folders', '/joplin/api/folders'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_folders(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Folder = request.env['joplin.folder']
        all_folders = Folder.search([('active', '=', True), ('parent_id', '=', False)], order='name')
        items = [_folder_to_dict(f, params.get('fields')) for f in all_folders]
        return self._paginated_response(items, False)

    @http.route(['/joplin/folders/<string:joplin_id>', '/joplin/api/folders/<string:joplin_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_folder(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        folder = request.env['joplin.folder'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not folder:
            return self._response({'error': 'Folder not found'}, 404)
        return self._response(_folder_to_dict(folder, params.get('fields')))

    @http.route(['/joplin/folders/<string:joplin_id>/notes', '/joplin/api/folders/<string:joplin_id>/notes'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_folder_notes(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        folder = request.env['joplin.folder'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not folder:
            return self._response({'error': 'Folder not found'}, 404)
        Note = request.env['joplin.note']
        domain = [('folder_id', '=', folder.id), ('active', '=', True)]
        records, has_more = _paginate(Note, domain, params)
        items = [_note_to_dict(n, params.get('fields')) for n in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/folders', '/joplin/api/folders'], type='http', auth='none', methods=['POST'], csrf=False)
    def create_folder(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        vals = {'name': data.get('title', 'New Folder')}
        if data.get('id'):
            vals['joplin_id'] = data['id']
        if data.get('parent_id'):
            parent = request.env['joplin.folder'].search([('joplin_id', '=', data['parent_id'])], limit=1)
            if parent:
                vals['parent_id'] = parent.id
        if data.get('icon'):
            vals['icon'] = data['icon']
        try:
            folder = request.env['joplin.folder'].create(vals)
            return self._response(_folder_to_dict(folder), 201)
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/folders/<string:joplin_id>', '/joplin/api/folders/<string:joplin_id>'], type='http', auth='none', methods=['PUT'], csrf=False)
    def update_folder(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        folder = request.env['joplin.folder'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not folder:
            return self._response({'error': 'Folder not found'}, 404)
        vals = {}
        if 'title' in data:
            vals['name'] = data['title']
        if 'parent_id' in data:
            if data['parent_id']:
                parent = request.env['joplin.folder'].search([('joplin_id', '=', data['parent_id'])], limit=1)
                vals['parent_id'] = parent.id if parent else False
            else:
                vals['parent_id'] = False
        if 'icon' in data:
            vals['icon'] = data['icon']
        try:
            folder.write(vals)
            return self._response(_folder_to_dict(folder))
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/folders/<string:joplin_id>', '/joplin/api/folders/<string:joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_folder(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        folder = request.env['joplin.folder'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not folder:
            return self._response({'error': 'Folder not found'}, 404)
        if params.get('permanent') == '1':
            folder.unlink()
        else:
            folder.write({'active': False})
        return self._response({'deleted': True})

    # ---- TAGS ----

    @http.route(['/joplin/tags', '/joplin/api/tags'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_tags(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Tag = request.env['joplin.tag']
        domain = [('active', '=', True)]
        records, has_more = _paginate(Tag, domain, params)
        items = [_tag_to_dict(t, params.get('fields')) for t in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/tags/<string:joplin_id>', '/joplin/api/tags/<string:joplin_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_tag(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        return self._response(_tag_to_dict(tag, params.get('fields')))

    @http.route(['/joplin/tags/<string:joplin_id>/notes', '/joplin/api/tags/<string:joplin_id>/notes'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_tag_notes(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        records, has_more = _paginate(request.env['joplin.note'], [('tag_ids', 'in', tag.id), ('active', '=', True)], params)
        items = [_note_to_dict(n, params.get('fields')) for n in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/tags/<string:joplin_id>/notes', '/joplin/api/tags/<string:joplin_id>/notes'], type='http', auth='none', methods=['POST'], csrf=False)
    def add_tag_to_note(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        note = request.env['joplin.note'].search([('joplin_id', '=', data.get('id'))], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        note.write({'tag_ids': [(4, tag.id)]})
        return self._response({'added': True})

    @http.route(['/joplin/tags', '/joplin/api/tags'], type='http', auth='none', methods=['POST'], csrf=False)
    def create_tag(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        vals = {'name': data.get('title', 'New Tag')}
        if data.get('id'):
            vals['joplin_id'] = data['id']
        try:
            tag = request.env['joplin.tag'].create(vals)
            return self._response(_tag_to_dict(tag), 201)
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/tags/<string:joplin_id>', '/joplin/api/tags/<string:joplin_id>'], type='http', auth='none', methods=['PUT'], csrf=False)
    def update_tag(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        if 'title' in data:
            tag.write({'name': data['title']})
        return self._response(_tag_to_dict(tag))

    @http.route(['/joplin/tags/<string:joplin_id>', '/joplin/api/tags/<string:joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_tag(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        tag.unlink()
        return self._response({'deleted': True})

    @http.route(['/joplin/tags/<string:joplin_id>/notes/<string:note_joplin_id>', '/joplin/api/tags/<string:joplin_id>/notes/<string:note_joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def remove_tag_from_note(self, joplin_id, note_joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        tag = request.env['joplin.tag'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not tag:
            return self._response({'error': 'Tag not found'}, 404)
        note = request.env['joplin.note'].search([('joplin_id', '=', note_joplin_id)], limit=1)
        if not note:
            return self._response({'error': 'Note not found'}, 404)
        note.write({'tag_ids': [(3, tag.id)]})
        return self._response({'removed': True})

    # ---- RESOURCES ----

    @http.route(['/joplin/resources', '/joplin/api/resources'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_resources(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Resource = request.env['joplin.resource']
        domain = [('active', '=', True)]
        records, has_more = _paginate(Resource, domain, params)
        items = [_resource_to_dict(r, params.get('fields')) for r in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/resources/<string:joplin_id>', '/joplin/api/resources/<string:joplin_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_resource(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        res = request.env['joplin.resource'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not res:
            return self._response({'error': 'Resource not found'}, 404)
        return self._response(_resource_to_dict(res, params.get('fields')))

    @http.route(['/joplin/resources/<string:joplin_id>/file', '/joplin/api/resources/<string:joplin_id>/file'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_resource_file(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        res = request.env['joplin.resource'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not res or not res.datas:
            return self._response({'error': 'Resource not found'}, 404)
        import base64
        content = base64.b64decode(res.datas)
        headers = [('Content-Type', res.mime or 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{res.filename or "file"}"')]
        return request.make_response(content, headers)

    @http.route(['/joplin/resources/<string:joplin_id>/notes', '/joplin/api/resources/<string:joplin_id>/notes'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_resource_notes(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        res = request.env['joplin.resource'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not res:
            return self._response({'error': 'Resource not found'}, 404)
        if not res.note_id:
            return self._paginated_response([], False)
        items = [{'id': res.note_id.joplin_id}]
        return self._paginated_response(items, False)

    @http.route(['/joplin/resources', '/joplin/api/resources'], type='http', auth='none', methods=['POST'], csrf=False)
    def create_resource(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = params
            if request.httprequest.mimetype and 'multipart' in request.httprequest.mimetype:
                file_data = request.httprequest.files.get('data')
                props_str = request.httprequest.form.get('props', '{}')
                props = json.loads(props_str)
                if file_data:
                    import base64
                    content = file_data.read()
                    data['datas'] = base64.b64encode(content).decode('utf-8')
                    data['filename'] = file_data.filename or props.get('filename', '')
                    data['mime'] = file_data.mimetype or props.get('mime', 'application/octet-stream')
                for k, v in props.items():
                    if k not in data:
                        data[k] = v
            else:
                raw = json.loads(request.httprequest.data)
                data.update(raw)

            vals = {}
            if data.get('title'):
                vals['name'] = data['title']
            if data.get('mime'):
                vals['mime'] = data['mime']
            if data.get('filename'):
                vals['filename'] = data['filename']
            if data.get('datas'):
                vals['datas'] = data['datas']
            if data.get('id'):
                vals['joplin_id'] = data['id']
            if data.get('note_id'):
                note = request.env['joplin.note'].search([('joplin_id', '=', data['note_id'])], limit=1)
                if note:
                    vals['note_id'] = note.id

            res = request.env['joplin.resource'].create(vals)
            return self._response(_resource_to_dict(res), 201)
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/resources/<string:joplin_id>', '/joplin/api/resources/<string:joplin_id>'], type='http', auth='none', methods=['PUT'], csrf=False)
    def update_resource(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        res = request.env['joplin.resource'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not res:
            return self._response({'error': 'Resource not found'}, 404)
        vals = {}
        if 'title' in data:
            vals['name'] = data['title']
        if 'mime' in data:
            vals['mime'] = data['mime']
        if 'filename' in data:
            vals['filename'] = data['filename']
        try:
            res.write(vals)
            return self._response(_resource_to_dict(res))
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/resources/<string:joplin_id>', '/joplin/api/resources/<string:joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_resource(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        res = request.env['joplin.resource'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not res:
            return self._response({'error': 'Resource not found'}, 404)
        res.unlink()
        return self._response({'deleted': True})

    # ---- REVISIONS ----

    @http.route(['/joplin/revisions', '/joplin/api/revisions'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_revisions(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Rev = request.env['joplin.revision']
        domain = []
        records, has_more = _paginate(Rev, domain, params)
        items = [_revision_to_dict(r, params.get('fields')) for r in records]
        return self._paginated_response(items, has_more)

    @http.route(['/joplin/revisions/<string:joplin_id>', '/joplin/api/revisions/<string:joplin_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_revision(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        rev = request.env['joplin.revision'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not rev:
            return self._response({'error': 'Revision not found'}, 404)
        return self._response(_revision_to_dict(rev, params.get('fields')))

    @http.route(['/joplin/revisions', '/joplin/api/revisions'], type='http', auth='none', methods=['POST'], csrf=False)
    def create_revision(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        vals = {}
        if data.get('id'):
            vals['joplin_id'] = data['id']
        if data.get('item_id'):
            vals['item_id'] = data['item_id']
            note = request.env['joplin.note'].search([('joplin_id', '=', data['item_id'])], limit=1)
            if note:
                vals['note_id'] = note.id
        if data.get('title_diff'):
            vals['title_diff'] = data['title_diff']
        if data.get('body_diff'):
            vals['body_diff'] = data['body_diff']
        if data.get('metadata_diff'):
            vals['metadata_diff'] = data['metadata_diff']
        if data.get('item_updated_time'):
            vals['item_updated_time'] = _from_ms_timestamp(data['item_updated_time'])
        try:
            rev = request.env['joplin.revision'].create(vals)
            return self._response(_revision_to_dict(rev), 201)
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/revisions/<string:joplin_id>', '/joplin/api/revisions/<string:joplin_id>'], type='http', auth='none', methods=['PUT'], csrf=False)
    def update_revision(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        rev = request.env['joplin.revision'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not rev:
            return self._response({'error': 'Revision not found'}, 404)
        vals = {}
        if 'title_diff' in data:
            vals['title_diff'] = data['title_diff']
        if 'body_diff' in data:
            vals['body_diff'] = data['body_diff']
        if 'metadata_diff' in data:
            vals['metadata_diff'] = data['metadata_diff']
        try:
            rev.write(vals)
            return self._response(_revision_to_dict(rev))
        except Exception as e:
            return self._response({'error': str(e)}, 400)

    @http.route(['/joplin/revisions/<string:joplin_id>', '/joplin/api/revisions/<string:joplin_id>'], type='http', auth='none', methods=['DELETE'], csrf=False)
    def delete_revision(self, joplin_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        rev = request.env['joplin.revision'].search([('joplin_id', '=', joplin_id)], limit=1)
        if not rev:
            return self._response({'error': 'Revision not found'}, 404)
        rev.unlink()
        return self._response({'deleted': True})

    # ---- EVENTS ----

    @http.route(['/joplin/events', '/joplin/api/events'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_events(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        Event = request.env['joplin.event']
        domain = []
        cursor = params.get('cursor')
        if cursor:
            domain.append(('id', '>', int(cursor)))
        limit = min(int(params.get('limit', 100)), 100)
        events = Event.search(domain, order='id asc', limit=limit + 1)
        has_more = len(events) > limit
        items = events[:limit]
        new_cursor = str(items[-1].id) if items else cursor
        return self._response({
            'items': [{
                'id': e.id,
                'item_type': e.item_type,
                'item_id': e.item_id,
                'type': e.event_type,
                'created_time': _to_ms_timestamp(e.created_time),
                'source': e.source,
                'before_change_item': e.before_change_item or '',
            } for e in items],
            'has_more': has_more,
            'cursor': new_cursor,
        })

    @http.route(['/joplin/events/<int:event_id>', '/joplin/api/events/<int:event_id>'], type='http', auth='none', methods=['GET'], csrf=False)
    def get_event(self, event_id, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        event = request.env['joplin.event'].browse(event_id)
        if not event.exists():
            return self._response({'error': 'Event not found'}, 404)
        return self._response({
            'id': event.id,
            'item_type': event.item_type,
            'item_id': event.item_id,
            'type': event.event_type,
            'created_time': _to_ms_timestamp(event.created_time),
            'source': event.source,
            'before_change_item': event.before_change_item or '',
        })

    # ---- SEARCH ----

    @http.route(['/joplin/search', '/joplin/api/search'], type='http', auth='none', methods=['GET'], csrf=False)
    def search(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        query = params.get('query', '').strip()
        if not query:
            return self._paginated_response([], False)

        search_type = params.get('type', 'note')
        fields = params.get('fields')

        if search_type == 'folder':
            folders = request.env['joplin.folder'].search([
                '|', ('name', 'ilike', query),
                ('joplin_id', 'ilike', query),
                ('active', '=', True),
            ])
            items = [_folder_to_dict(f, fields) for f in folders]
            return self._paginated_response(items, False)
        elif search_type == 'tag':
            tags = request.env['joplin.tag'].search([
                '|', ('name', 'ilike', query),
                ('joplin_id', 'ilike', query),
                ('active', '=', True),
            ])
            items = [_tag_to_dict(t, fields) for t in tags]
            return self._paginated_response(items, False)
        else:
            Note = request.env['joplin.note']
            domain = [
                '&', ('active', '=', True),
                '|', '|',
                ('title', 'ilike', query),
                ('body', 'ilike', query),
                ('joplin_id', 'ilike', query),
            ]
            records, has_more = _paginate(Note, domain, params)
            items = [_note_to_dict(n, fields) for n in records]
            return self._paginated_response(items, has_more)


    # ---- SHARES ----

    @http.route('/joplin/api/share_users', type='http', auth='none', methods=['GET'], csrf=False)
    def get_share_users(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        return self._response({"items": []})

    @http.route('/joplin/api/shares', type='http', auth='none', methods=['GET'], csrf=False)
    def get_shares(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        return self._response({"items": []})


    # ---- DELTA ----

    @http.route('/joplin/api/delta', type='http', auth='none', methods=['POST'], csrf=False)
    def delta_sync(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        cursor = data.get('cursor', 0) if isinstance(data, dict) else 0
        Item = request.env["joplin.item"].sudo()
        domain = []
        if cursor:
            from_dt = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc)
            domain = [('updated_time', '>=', from_dt)]
        items = Item.search(domain, order='updated_time', limit=50)
        new_cursor = int(time.time() * 1000)
        return self._response({
            "items": [{
                "id": f"root:{item.path}",
                "name": item.path.split("/")[-1],
                "mime_type": "text/plain",
                "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
                "jop_updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
            } for item in items],
            "has_more": False,
            "cursor": new_cursor,
        })

    # ---- BATCH ITEMS ----

    @http.route('/joplin/api/batch_items', type='http', auth='none', methods=['POST', 'PUT'], csrf=False)
    def batch_items(self, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        items = data.get('items', []) if isinstance(data, dict) else data if isinstance(data, list) else []
        results = []
        for item in items:
            path = item.get('path', '')
            content = item.get('content', '')
            if path:
                # Save to joplin.item
                Item = request.env['joplin.item'].sudo()
                jitem = Item.search([('path', '=', path)], limit=1)
                if jitem:
                    jitem.write({'content': content, 'updated_time': datetime.now(timezone.utc).replace(tzinfo=None)})
                else:
                    Item.create({'path': path, 'content': content, 'updated_time': datetime.now(timezone.utc).replace(tzinfo=None)})
            results.append({})
        return self._response({'items': results})

    # ---- JOPLIN SERVER SYNC (items API) ----
    # Used by sync.target = 9 (Joplin Server)
    # Path format: /api/items/<owner>:<path>:/content

    @http.route('/joplin/api/items/<path:item_path>', type="http", auth="none", methods=["GET"], csrf=False)
    def get_sync_item(self, item_path, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        want_content = item_path.endswith(":/content")
        if want_content:
            item_path = item_path[:-len(":/content")]
        colon_pos = item_path.find(":")
        if colon_pos < 0:
            return self._response({"error": "Invalid path"}, 400)
        owner = item_path[:colon_pos]
        path = item_path[colon_pos + 1:]
        if owner == "root" and path == "/info.json":
            user = _get_user()
            if want_content:
                return self._response({
                    "version": "3.0.0",
                    "user": {
                        "id": str(user.id) if user else "",
                        "email": user.login if user else "",
                    }
                })
            return self._response({
                "id": "root:/info.json",
                "name": "info.json",
                "mime_type": "application/json",
                "updated_time": 0,
            })
        if owner == "root" and path.startswith("/.sync/"):
            Item = request.env["joplin.item"].sudo()
            if path == "/.sync/" or path == "/.sync":
                # List all items in .sync directory
                items = Item.search([])
                return self._response({
                    "items": [{
                        "id": f"root:{item.path}",
                        "name": item.path.split("/")[-1],
                        "mime_type": "text/plain",
                        "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
                    } for item in items],
                })
            item = Item.search([("path", "=", path)], limit=1)
            if not item:
                return self._response({"error": "Not found"}, 404)
            if want_content:
                return http.Response(
                    item.content or "",
                    status=200,
                    content_type="text/plain",
                )
            return self._response({
                "id": f"{owner}:{path}",
                "name": path.split("/")[-1],
                "mime_type": "text/plain",
                "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
            })
        # Handle delta endpoint: root:/:/delta
        if path == "//delta" or path == "/:/delta":
            Item = request.env["joplin.item"].sudo()
            items = Item.search([], order='updated_time', limit=100)
            return self._response({
                "items": [{
                    "id": f"root:{item.path}",
                    "item_name": item.path,
                    "mime_type": "text/plain",
                    "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
                    "jop_updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
                    "type": 1,
                } for item in items],
                "has_more": False,
                "cursor": str(int(time.time() * 1000)),
            })

        # Handle all items stored in joplin.item
        Item = request.env["joplin.item"].sudo()
        if path.endswith(":"):
            path = path[:-1]
        item = Item.search([("path", "=", path)], limit=1)
        if not item and not path.startswith("/.sync/"):
            # Joplin temp files etc - create on read to return default stat
            item = Item.create({
                "path": path,
                "content": "",
                "updated_time": datetime.now(timezone.utc).replace(tzinfo=None),
            })
        if item:
            if want_content:
                return http.Response(
                    item.content or "",
                    status=200,
                    content_type="text/plain",
                )
            return self._response({
                "id": f"{owner}:{path}",
                "name": path.split("/")[-1],
                "mime_type": "text/plain",
                "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
            })
        return self._response({"error": "Not found"}, 404)

    @http.route("/joplin/api/items/<path:item_path>", type="http", auth="none", methods=["PUT"], csrf=False)
    def put_sync_item(self, item_path, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            data = params
        if item_path.endswith(":/content"):
            item_path = item_path[:-len(":/content")]
        colon_pos = item_path.find(":")
        if colon_pos < 0:
            return self._response({"error": "Invalid path"}, 400)
        owner = item_path[:colon_pos]
        path = item_path[colon_pos + 1:]
        Item = request.env["joplin.item"].sudo()
        item = Item.search([("path", "=", path)], limit=1)
        if item:
            item.write({
                "content": data.get("content", item.content),
                "updated_time": _from_ms_timestamp(data.get("updated_time", 0)),
            })
        else:
            item = Item.create({
                "path": path,
                "content": data.get("content", ""),
                "updated_time": _from_ms_timestamp(data.get("updated_time", 0)),
            })
        return self._response({
            "id": f"{owner}:{path}",
            "name": path.split("/")[-1],
            "mime_type": "text/plain",
            "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
        })

    @http.route("/joplin/api/items/<path:item_path>", type="http", auth="none", methods=["POST"], csrf=False)
    def post_sync_item(self, item_path, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        # Used for lock operations - just return success with the existing item
        if item_path.endswith(":/content"):
            item_path = item_path[:-len(":/content")]
        colon_pos = item_path.find(":")
        if colon_pos < 0:
            return self._response({"error": "Invalid path"}, 400)
        owner = item_path[:colon_pos]
        path = item_path[colon_pos + 1:]
        Item = request.env["joplin.item"].sudo()
        item = Item.search([("path", "=", path)], limit=1)
        if item:
            return self._response({
                "id": f"{owner}:{path}",
                "name": path.split("/")[-1],
                "mime_type": "text/plain",
                "updated_time": _to_ms_timestamp(item.updated_time) if item.updated_time else 0,
            })
        return self._response({"error": "Not found"}, 404)

    @http.route("/joplin/api/items/<path:item_path>", type="http", auth="none", methods=["DELETE"], csrf=False)
    def delete_sync_item(self, item_path, **params):
        auth_err = self._auth()
        if auth_err:
            return auth_err
        if item_path.endswith(":/content"):
            item_path = item_path[:-len(":/content")]
        colon_pos = item_path.find(":")
        if colon_pos < 0:
            return self._response({"error": "Invalid path"}, 400)
        path = item_path[colon_pos + 1:]
        Item = request.env["joplin.item"].sudo()
        item = Item.search([("path", "=", path)], limit=1)
        if item:
            item.unlink()
        return self._response({})
