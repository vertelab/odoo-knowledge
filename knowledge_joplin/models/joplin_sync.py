"""Joplin Server sync protocol — serialization + ORM mapping.

Implements the subset of the Joplin Server file-sync protocol needed to map
the desktop/mobile client's items onto the ``joplin.*`` models (note, folder,
tag, resource) instead of a raw file store.

Item file format (matches Joplin ``BaseItem.serialize``)::

    <title>

    <body>

    <key>: <value>
    ...
    type_: <n>

where ``type_`` is 1=note, 2=folder, 4=resource, 5=tag, 6=note_tag, 13=revision.
Resources also have a binary blob addressed at ``/.resource/<id>``.
"""
import base64
import hashlib
import logging
from datetime import datetime, timezone

from dateutil import parser as dateparser

from odoo import fields as odoo_fields

_logger = logging.getLogger(__name__)

TYPE_NOTE = 1
TYPE_FOLDER = 2
TYPE_SETTING = 3
TYPE_RESOURCE = 4
TYPE_TAG = 5
TYPE_NOTE_TAG = 6
TYPE_MASTER_KEY = 9
TYPE_REVISION = 13

_TIMESTAMP_KEYS = (
    'created_time', 'updated_time', 'user_created_time', 'user_updated_time',
    'todo_due', 'todo_completed', 'deleted_time', 'item_updated_time',
    'blob_updated_time',
)
_BOOL_KEYS = (
    'is_todo', 'is_conflict', 'is_shared', 'encryption_applied',
    'encryption_blob_encrypted', 'is_locked',
)
_FLOAT_KEYS = ('latitude', 'longitude', 'altitude', 'order', 'size')
_INT_KEYS = ('markup_language', 'ocr_status', 'ocr_driver_id', 'item_type')


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def to_ms(dt):
    if not dt:
        return 0
    if isinstance(dt, str):
        dt = dateparser.parse(dt)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 1000)


def from_ms(ms):
    if not ms:
        return False
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(tzinfo=None)


def ts_to_iso(value):
    """Convert a datetime or ms int to the ISO string Joplin expects."""
    if not value:
        return ''
    ms = value if isinstance(value, (int, float)) else to_ms(value)
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    except (OverflowError, OSError, ValueError):
        return ''


def iso_to_ts(raw):
    if not raw:
        return 0
    try:
        dt = dateparser.parse(raw)
    except (ValueError, OverflowError):
        return 0
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 1000)


def escape(value):
    """Mirror Joplin ``serialize_format`` escaping for prop values."""
    if value is None:
        return ''
    return (str(value)
            .replace('\\n', '\\\\n')
            .replace('\\r', '\\\\r')
            .replace('\n', '\\n')
            .replace('\r', '\\r'))


def unescape(value):
    """Mirror Joplin ``unserialize_format`` unescaping."""
    if value is None:
        return ''
    return (value
            .replace('\\n', '\n')
            .replace('\\r', '\r')
            .replace('\\\n', '\\n')
            .replace('\\\r', '\\r'))


def prop_to_joplin(key, value):
    if key in _TIMESTAMP_KEYS:
        return ts_to_iso(value)
    if key in _BOOL_KEYS:
        return '1' if value else '0'
    if value is None or value is False:
        return ''
    if key in _FLOAT_KEYS and isinstance(value, float):
        return repr(value)
    return escape(value)


def prop_to_odoo(key, raw):
    if key in _TIMESTAMP_KEYS:
        return iso_to_ts(raw)
    if key in _BOOL_KEYS:
        return raw in ('1', 'true', 'True', 1, True)
    if key in _FLOAT_KEYS:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    if key in _INT_KEYS:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0
    return unescape(raw) if raw else ''


def serialize_item(title, body, fields):
    """Build the Joplin item text.

    ``fields`` is an ordered list of ``(key, value_str)`` tuples.
    """
    parts = []
    if isinstance(title, str):
        parts.append(title)
    if body:
        parts.append(body)
    if fields:
        parts.append('\n'.join('%s: %s' % (k, v) for k, v in fields))
    return '\n\n'.join(parts)


def unserialize_item(content):
    """Parse the Joplin item text into a dict."""
    if content is None:
        content = ''
    lines = content.split('\n')
    props = {}
    body_lines = []
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if line == '':
            body_lines = lines[:i]
            break
        if ':' in line:
            key, val = line.split(':', 1)
            props[key.strip()] = val.strip()

    type_ = int(props.get('type_') or 0)
    title = ''
    body = ''
    if body_lines:
        title = body_lines[0] or ''
        rest = body_lines[1:]
        if rest and rest[0] == '':
            rest = rest[1:]
        if type_ == TYPE_NOTE:
            body = '\n'.join(rest)
    return {'type_': type_, 'title': title, 'body': body, 'props': props}


def notetag_id(note_joplin_id, tag_joplin_id):
    return hashlib.md5(('%s%s' % (note_joplin_id, tag_joplin_id)).encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Field maps: joplin field -> odoo field
# ---------------------------------------------------------------------------

_NOTE_FIELDS = (
    ('id', 'joplin_id'),
    ('parent_id', 'folder_id'),  # special: joplin_id of folder
    ('is_todo', 'is_todo'),
    ('todo_due', 'todo_due'),
    ('todo_completed', 'todo_completed'),
    ('author', 'author'),
    ('source_url', 'source_url'),
    ('latitude', 'latitude'),
    ('longitude', 'longitude'),
    ('altitude', 'altitude'),
    ('is_conflict', 'is_conflict'),
    ('conflict_original_id', 'conflict_original_id'),
    ('order', 'order'),
    ('markup_language', 'markup_language'),
    ('source', 'source'),
    ('source_application', 'source_application'),
    ('application_data', 'application_data'),
    ('created_time', 'created_time'),
    ('updated_time', 'updated_time'),
    ('user_created_time', 'user_created_time'),
    ('user_updated_time', 'user_updated_time'),
    ('deleted_time', 'deleted_time'),
    ('is_shared', 'is_shared'),
    ('share_id', 'share_id'),
    ('encryption_cipher_text', 'encryption_cipher_text'),
    ('encryption_applied', 'encryption_applied'),
    ('master_key_id', 'master_key_id'),
)

_FOLDER_FIELDS = (
    ('id', 'joplin_id'),
    ('parent_id', 'parent_id'),  # special: joplin_id of parent folder
    ('icon', 'icon'),
    ('is_shared', 'is_shared'),
    ('share_id', 'share_id'),
    ('encryption_cipher_text', 'encryption_cipher_text'),
    ('encryption_applied', 'encryption_applied'),
    ('master_key_id', 'master_key_id'),
    ('created_time', 'created_time'),
    ('updated_time', 'updated_time'),
    ('user_created_time', 'user_created_time'),
    ('user_updated_time', 'user_updated_time'),
    ('deleted_time', 'deleted_time'),
)

_TAG_FIELDS = (
    ('id', 'joplin_id'),
    ('parent_id', 'parent_id'),
    ('is_shared', 'is_shared'),
    ('encryption_cipher_text', 'encryption_cipher_text'),
    ('encryption_applied', 'encryption_applied'),
    ('created_time', 'created_time'),
    ('updated_time', 'updated_time'),
    ('user_created_time', 'user_created_time'),
    ('user_updated_time', 'user_updated_time'),
)

_RESOURCE_FIELDS = (
    ('id', 'joplin_id'),
    ('mime', 'mime'),
    ('filename', 'filename'),
    ('file_extension', 'file_extension'),
    ('size', 'file_size'),
    ('blob_updated_time', 'blob_updated_time'),
    ('is_shared', 'is_shared'),
    ('share_id', 'share_id'),
    ('encryption_cipher_text', 'encryption_cipher_text'),
    ('encryption_applied', 'encryption_applied'),
    ('encryption_blob_encrypted', 'encryption_blob_encrypted'),
    ('master_key_id', 'master_key_id'),
    ('ocr_text', 'ocr_text'),
    ('ocr_details', 'ocr_details'),
    ('ocr_status', 'ocr_status'),
    ('ocr_error', 'ocr_error'),
    ('ocr_driver_id', 'ocr_driver_id'),
    ('created_time', 'created_time'),
    ('updated_time', 'updated_time'),
    ('user_created_time', 'user_created_time'),
    ('user_updated_time', 'user_updated_time'),
)


# ---------------------------------------------------------------------------
# Record -> serialized text
# ---------------------------------------------------------------------------

def _note_to_item(note):
    fields = []
    for jkey, okey in _NOTE_FIELDS:
        if jkey == 'parent_id':
            val = note.folder_id.joplin_id if note.folder_id else ''
        else:
            val = note[okey]
        fields.append((jkey, prop_to_joplin(jkey, val)))
    fields.append(('type_', str(TYPE_NOTE)))
    return serialize_item(note.title or '', note.body or '', fields)


def _folder_to_item(folder):
    fields = []
    for jkey, okey in _FOLDER_FIELDS:
        if jkey == 'parent_id':
            val = folder.parent_id.joplin_id if folder.parent_id else ''
        else:
            val = folder[okey]
        fields.append((jkey, prop_to_joplin(jkey, val)))
    fields.append(('type_', str(TYPE_FOLDER)))
    return serialize_item(folder.name or '', None, fields)


def _tag_to_item(tag):
    fields = []
    for jkey, okey in _TAG_FIELDS:
        fields.append((jkey, prop_to_joplin(jkey, tag[okey])))
    fields.append(('type_', str(TYPE_TAG)))
    return serialize_item(tag.name or '', None, fields)


def _resource_to_item(res):
    fields = []
    for jkey, okey in _RESOURCE_FIELDS:
        fields.append((jkey, prop_to_joplin(jkey, res[okey])))
    fields.append(('type_', str(TYPE_RESOURCE)))
    return serialize_item(res.name or '', None, fields)


# ---------------------------------------------------------------------------
# Item text -> record vals
# ---------------------------------------------------------------------------

def _apply_fields(record, item, field_map, special_parent=False):
    vals = {}
    for jkey, okey in field_map:
        if jkey not in item['props']:
            continue
        raw = item['props'][jkey]
        if special_parent and jkey == 'parent_id':
            continue  # handled by caller
        vals[okey] = prop_to_odoo(jkey, raw)
    # timestamps must be naive datetimes for Odoo Datetime fields
    for okey in ('created_time', 'updated_time', 'user_created_time',
                 'user_updated_time', 'deleted_time', 'todo_due',
                 'todo_completed', 'blob_updated_time'):
        if okey in vals and vals[okey]:
            vals[okey] = from_ms(vals[okey]) if isinstance(vals[okey], (int, float)) else vals[okey]
    return vals


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------

def _parse_path(path):
    """Return ``(kind, id)`` for a sync path.

    kind is one of: info, delta, resource_blob, item, raw
    """
    if path.endswith(':'):
        path = path[:-1]
    if path in ('/info.json', 'info.json'):
        return 'info', None
    if path in ('//delta', '/:/delta', ':/delta'):
        return 'delta', None
    if path.startswith('/.resource/') or path.startswith('.resource/'):
        rid = path.split('/')[-1]
        return 'resource_blob', rid
    if path.startswith('/.sync/') or path.startswith('.sync/') or path.startswith('/locks/') or path.startswith('locks/'):
        return 'raw', path
    name = path.split('/')[-1]
    if name.endswith('.md'):
        return 'item', name[:-3]
    return 'raw', path


def _find_model_record(env, kind, jid):
    model = {
        'note': 'joplin.note',
        'folder': 'joplin.folder',
        'tag': 'joplin.tag',
        'resource': 'joplin.resource',
    }.get(kind)
    if not model:
        return None
    return env[model].with_context(active_test=False).search([('joplin_id', '=', jid)], limit=1)


def _record_kind_by_id(env, jid):
    for kind in ('note', 'folder', 'tag', 'resource'):
        rec = _find_model_record(env, kind, jid)
        if rec:
            return kind, rec
    return None, None


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

def ingest(env, path, content):
    """Handle a PUT of item content. Returns the resulting item id (joplin_id)."""
    kind, jid = _parse_path(path)

    if kind == 'resource_blob':
        res = _find_model_record(env, 'resource', jid)
        if not res:
            res = env['joplin.resource'].create({'joplin_id': jid})
        raw = content if isinstance(content, bytes) else (content or '').encode('utf-8')
        res.write({'datas': base64.b64encode(raw).decode('ascii'), 'file_size': len(raw)})
        return jid

    # Text content: decode bytes to str.
    if isinstance(content, bytes):
        content = content.decode('utf-8', 'replace')
    elif content is None:
        content = ''

    if kind != 'item':
        # Raw fallback (locks, .sync, etc.) -> joplin.item
        Item = env['joplin.item'].sudo()
        item = Item.search([('path', '=', path)], limit=1)
        vals = {'content': content,
                'updated_time': datetime.now(timezone.utc).replace(tzinfo=None)}
        if item:
            item.write(vals)
        else:
            item.create(dict(vals, path=path))
        return jid

    item = unserialize_item(content)
    type_ = item['type_']

    if type_ == TYPE_NOTE:
        return _ingest_note(env, jid, item)
    if type_ == TYPE_FOLDER:
        return _ingest_folder(env, jid, item)
    if type_ == TYPE_TAG:
        return _ingest_tag(env, jid, item)
    if type_ == TYPE_RESOURCE:
        return _ingest_resource(env, jid, item)
    if type_ == TYPE_NOTE_TAG:
        return _ingest_notetag(env, jid, item)
    if type_ == TYPE_REVISION:
        return _ingest_revision(env, jid, item)

    # Unsupported type -> raw fallback so nothing is lost.
    Item = env['joplin.item'].sudo()
    item_rec = Item.search([('path', '=', path)], limit=1)
    vals = {'content': content if isinstance(content, str) else (content or b'').decode('utf-8', 'replace'),
            'updated_time': datetime.now(timezone.utc).replace(tzinfo=None)}
    if item_rec:
        item_rec.write(vals)
    else:
        item_rec.create(dict(vals, path=path))
    return jid


def _ingest_note(env, jid, item):
    Note = env['joplin.note'].with_context(active_test=False)
    note = Note.search([('joplin_id', '=', jid)], limit=1)
    vals = _apply_fields(note, item, _NOTE_FIELDS)
    vals['title'] = item['title']
    vals['body'] = item['body']
    if 'parent_id' in item['props']:
        folder_jid = item['props']['parent_id']
        folder = env['joplin.folder'].search([('joplin_id', '=', folder_jid)], limit=1) if folder_jid else None
        vals['folder_id'] = folder.id if folder else False
    # deleted_time drives soft-delete in Joplin; mirror as active flag.
    if 'deleted_time' in vals:
        vals['active'] = not bool(vals['deleted_time'])
    if not note:
        vals['joplin_id'] = jid
        if 'user_id' not in vals:
            vals['user_id'] = env.user.id
        note = Note.create(vals)
    else:
        note.write(vals)
    return jid


def _ingest_folder(env, jid, item):
    Folder = env['joplin.folder'].with_context(active_test=False)
    folder = Folder.search([('joplin_id', '=', jid)], limit=1)
    vals = _apply_fields(folder, item, _FOLDER_FIELDS)
    vals['name'] = item['title']
    if 'parent_id' in item['props']:
        p_jid = item['props']['parent_id']
        parent = env['joplin.folder'].search([('joplin_id', '=', p_jid)], limit=1) if p_jid else None
        vals['parent_id'] = parent.id if parent else False
    if 'deleted_time' in vals:
        vals['active'] = not bool(vals['deleted_time'])
    if not folder:
        vals['joplin_id'] = jid
        if 'user_id' not in vals:
            vals['user_id'] = env.user.id
        folder = Folder.create(vals)
    else:
        folder.write(vals)
    return jid


def _ingest_tag(env, jid, item):
    Tag = env['joplin.tag'].with_context(active_test=False)
    tag = Tag.search([('joplin_id', '=', jid)], limit=1)
    vals = _apply_fields(tag, item, _TAG_FIELDS)
    vals['name'] = item['title']
    if not tag:
        vals['joplin_id'] = jid
        if 'user_id' not in vals:
            vals['user_id'] = env.user.id
        tag = Tag.create(vals)
    else:
        tag.write(vals)
    return jid


def _ingest_resource(env, jid, item):
    Resource = env['joplin.resource'].with_context(active_test=False)
    res = Resource.search([('joplin_id', '=', jid)], limit=1)
    vals = _apply_fields(res, item, _RESOURCE_FIELDS)
    vals['name'] = item['title']
    if not res:
        vals['joplin_id'] = jid
        if 'user_id' not in vals:
            vals['user_id'] = env.user.id
        res = Resource.create(vals)
    else:
        res.write(vals)
    return jid


def _ingest_notetag(env, jid, item):
    note_jid = item['props'].get('note_id', '')
    tag_jid = item['props'].get('tag_id', '')
    note = env['joplin.note'].search([('joplin_id', '=', note_jid)], limit=1) if note_jid else None
    tag = env['joplin.tag'].search([('joplin_id', '=', tag_jid)], limit=1) if tag_jid else None
    if note and tag:
        note.write({'tag_ids': [(4, tag.id)]})
    return jid


def _ingest_revision(env, jid, item):
    # Revisions are stored raw (diff serialization differs from note revision diffs).
    return jid


def content_for(env, path):
    """Return (content, mime_type) for a GET of item content, or None if absent."""
    kind, jid = _parse_path(path)

    if kind == 'info':
        return None, None  # handled by controller

    if kind == 'resource_blob':
        res = _find_model_record(env, 'resource', jid)
        if not res or not res.datas:
            return None, None
        return base64.b64decode(res.datas), res.mime or 'application/octet-stream'

    if kind == 'raw':
        Item = env['joplin.item'].sudo()
        item = Item.search([('path', '=', path)], limit=1)
        if not item:
            return None, None
        return item.content or '', 'text/plain'

    if kind != 'item':
        return None, None

    rec_kind, rec = _record_kind_by_id(env, jid)
    if not rec:
        return None, None
    if rec_kind == 'note':
        return _note_to_item(rec), 'text/plain'
    if rec_kind == 'folder':
        return _folder_to_item(rec), 'text/plain'
    if rec_kind == 'tag':
        return _tag_to_item(rec), 'text/plain'
    if rec_kind == 'resource':
        return _resource_to_item(rec), 'text/plain'
    return None, None


def stat_for(env, path):
    """Return metadata dict for a GET stat, or None if absent."""
    kind, jid = _parse_path(path)

    if kind == 'info':
        return {'id': 'root:/info.json', 'name': 'info.json',
                'mime_type': 'application/json', 'updated_time': 0}

    if kind == 'resource_blob':
        res = _find_model_record(env, 'resource', jid)
        if not res:
            return None
        return {'id': 'root:/.resource/%s' % jid, 'name': jid,
                'mime_type': res.mime or 'application/octet-stream',
                'updated_time': to_ms(res.updated_time),
                'jop_updated_time': to_ms(res.updated_time)}

    if kind == 'raw':
        Item = env['joplin.item'].sudo()
        item = Item.search([('path', '=', path)], limit=1)
        if not item:
            return None
        return {'id': 'root:%s' % path, 'name': path.split('/')[-1],
                'mime_type': 'text/plain', 'updated_time': to_ms(item.updated_time),
                'jop_updated_time': to_ms(item.updated_time)}

    if kind != 'item':
        return None

    rec_kind, rec = _record_kind_by_id(env, jid)
    if not rec:
        return None
    return {'id': 'root:/%s.md' % jid, 'name': '%s.md' % jid,
            'mime_type': 'text/plain',
            'updated_time': to_ms(rec.updated_time),
            'jop_updated_time': to_ms(rec.updated_time)}


def delete_for(env, path):
    """Handle a DELETE of an item. Returns True if it existed."""
    kind, jid = _parse_path(path)

    if kind == 'resource_blob':
        res = _find_model_record(env, 'resource', jid)
        if res:
            res.write({'datas': False})
        return True

    if kind == 'raw':
        Item = env['joplin.item'].sudo()
        item = Item.search([('path', '=', path)], limit=1)
        if item:
            item.unlink()
            return True
        return False

    if kind != 'item':
        return False

    rec_kind, rec = _record_kind_by_id(env, jid)
    if not rec:
        return False
    if rec_kind == 'note':
        rec.write({'active': False, 'deleted_time': datetime.now(timezone.utc).replace(tzinfo=None)})
    elif rec_kind == 'resource':
        rec.unlink()
    else:
        rec.unlink()
    return True


def delta_items(env):
    """Return the list of delta items for the authenticated user."""
    items = []

    notes = env['joplin.note'].with_context(active_test=False).search([])
    for n in notes:
        items.append({'item_name': '%s.md' % n.joplin_id, 'type': TYPE_NOTE,
                      'updated_time': to_ms(n.updated_time),
                      'jop_updated_time': to_ms(n.updated_time)})

    folders = env['joplin.folder'].with_context(active_test=False).search([])
    for f in folders:
        items.append({'item_name': '%s.md' % f.joplin_id, 'type': TYPE_FOLDER,
                      'updated_time': to_ms(f.updated_time),
                      'jop_updated_time': to_ms(f.updated_time)})

    tags = env['joplin.tag'].with_context(active_test=False).search([])
    for t in tags:
        items.append({'item_name': '%s.md' % t.joplin_id, 'type': TYPE_TAG,
                      'updated_time': to_ms(t.updated_time),
                      'jop_updated_time': to_ms(t.updated_time)})

    resources = env['joplin.resource'].with_context(active_test=False).search([])
    for r in resources:
        items.append({'item_name': '%s.md' % r.joplin_id, 'type': TYPE_RESOURCE,
                      'updated_time': to_ms(r.updated_time),
                      'jop_updated_time': to_ms(r.updated_time)})

    # NoteTag relations (synthesized stable ids)
    seen = set()
    for t in tags:
        for n in t.note_ids:
            key = (n.joplin_id, t.joplin_id)
            if key in seen:
                continue
            seen.add(key)
            items.append({'item_name': '%s.md' % notetag_id(n.joplin_id, t.joplin_id),
                          'type': TYPE_NOTE_TAG,
                          'updated_time': to_ms(t.updated_time),
                          'jop_updated_time': to_ms(t.updated_time)})

    return items
