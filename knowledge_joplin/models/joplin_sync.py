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

# Page size for the delta. The client follows has_more until it is False.
_DELTA_PAGE_SIZE = 200

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
        # Odoo Datetime fields take a datetime or False — never a raw ms int.
        # Joplin sends 0 (or '') for unset timestamps.
        return from_ms(iso_to_ts(raw))
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
    # Joplin carries deleted_time on EVERY item type, tags included. Without
    # it the tag model gained a deleted_time column that nothing reads or
    # writes, so a tag deletion could never be reported to the client.
    ('deleted_time', 'deleted_time'),
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
    # prop_to_odoo already normalizes timestamps to naive datetimes/False;
    # guard again in case a caller bypasses it.
    for okey in ('created_time', 'updated_time', 'user_created_time',
                 'user_updated_time', 'deleted_time', 'todo_due',
                 'todo_completed', 'blob_updated_time'):
        if okey in vals and isinstance(vals[okey], (int, float)):
            vals[okey] = from_ms(vals[okey])
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
        folder = _resolve_folder(env, folder_jid) if folder_jid else None
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
        parent = _resolve_folder(env, p_jid) if p_jid else None
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


def _resolve_folder(env, jid, name=None):
    """Return the folder for *jid*, creating an empty shell if it is absent.

    A note's parent must never silently become "no notebook": that is what
    made the Android client show an empty notebook list while every note was
    present and searchable. The real folder arrives in the same delta and
    overwrites the shell.
    """
    Folder = env['joplin.folder'].with_context(active_test=False)
    folder = Folder.search([('joplin_id', '=', jid)], limit=1)
    if folder:
        return folder
    return Folder.create({
        'joplin_id': jid,
        'name': name or jid,
        'user_id': env.user.id,
    })


def _ingest_tag(env, jid, item):
    Tag = env['joplin.tag'].with_context(active_test=False)
    tag = Tag.search([('joplin_id', '=', jid)], limit=1)
    vals = _apply_fields(tag, item, _TAG_FIELDS)
    vals['name'] = item['title']
    if 'deleted_time' in vals:
        vals['active'] = not bool(vals['deleted_time'])
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
    elif note_jid and tag_jid:
        # The relation can legitimately arrive before either end (the sync
        # target delivers items in no guaranteed order). Creating a shell for
        # whichever side is missing keeps the tag assignment instead of
        # dropping it silently — the real item overwrites the shell when it
        # arrives. Same reasoning as _resolve_folder().
        if not note:
            note = env['joplin.note'].create({
                'joplin_id': note_jid,
                'title': note_jid,
                'body': '',
                'user_id': env.user.id,
            })
        if not tag:
            tag = env['joplin.tag'].create({
                'joplin_id': tag_jid,
                'name': tag_jid,
                'user_id': env.user.id,
            })
        note.write({'tag_ids': [(4, tag.id)]})
    return jid


def _ingest_revision(env, jid, item):
    # Revisions are stored raw (diff serialization differs from note revision diffs).
    return jid


def _notetag_pairs(env):
    """Yield ``(notetag_id, note, tag)`` for every note/tag relation.

    Note-tag items exist only as a relation between a note and a tag; they have
    no table row of their own, so :func:`_record_kind_by_id` can never find
    them. The same enumeration that ``delta_items`` advertises is used here, so
    a GET can resolve every type-6 item the delta hands out.
    """
    tags = env['joplin.tag'].with_context(active_test=False).search([], order='id')
    for tag in tags:
        for note in tag.note_ids:
            yield notetag_id(note.joplin_id, tag.joplin_id), note, tag


def _find_notetag(env, jid):
    """Return ``(note, tag)`` for a note-tag id, or ``None``."""
    for ntid, note, tag in _notetag_pairs(env):
        if ntid == jid:
            return note, tag
    return None


def _notetag_to_item(note, tag):
    """Serialise a note/tag relation as a Joplin type-6 item.

    Mirrors :func:`_ingest_notetag`, which reads ``note_id`` and ``tag_id`` from
    ``props`` — so emitting those two keys makes the item round-trip.
    """
    fields = [('note_id', note.joplin_id), ('tag_id', tag.joplin_id),
              ('type_', str(TYPE_NOTE_TAG))]
    return serialize_item('', '', fields)


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

    # Note-tags are advertised by delta_items() as type 6 but are not rows of
    # any model, so they must be resolved before _record_kind_by_id() (which
    # would report them absent and turn every fetch into a 404).
    pair = _find_notetag(env, jid)
    if pair:
        return _notetag_to_item(*pair), 'text/plain'

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

    pair = _find_notetag(env, jid)
    if pair:
        note, tag = pair
        # The relation carries no timestamp; the tag's is what delta_items()
        # uses as the proxy, so stat must agree with it or a client re-fetches
        # the same item forever.
        ts = to_ms(tag.updated_time)
        return {'id': 'root:/%s.md' % jid, 'name': '%s.md' % jid,
                'mime_type': 'text/plain',
                'updated_time': ts, 'jop_updated_time': ts}

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


def _encode_cursor(updated_time, item_name):
    """Opaque delta cursor: the (updated_time, item_name) pair of the last item sent.

    A bare millisecond timestamp cannot separate items sharing a timestamp,
    which made a paged client skip or repeat them. ``item_name`` is the
    protocol's own identity for an item and is unique across ALL item types,
    so it breaks the tie globally.

    An internal database id would NOT do: ids are only unique within one
    table, so the same (updated_time, id) pair can name a note and a folder
    at once — measured as a one-item overlap between consecutive pages.
    """
    return '%s|%s' % (to_ms(updated_time), item_name)


def _decode_cursor(cursor):
    """Return ``(updated_time, item_name)``. Tolerates junk.

    The timestamp comes back as a NAIVE UTC datetime, the same shape the
    column holds, so it can go straight into an ORM domain.
    """
    if cursor in (None, '', 0, '0', False):
        return None, ''
    raw = str(cursor)
    if '|' not in raw:
        # A legacy numeric cursor (the old wall-clock stamp) or garbage:
        # fall back to a full delta rather than silently sending nothing.
        return None, ''
    raw_time, item_name = raw.split('|', 1)
    try:
        return from_ms(int(raw_time)), item_name
    except (ValueError, TypeError):
        return None, ''


def _decode_cursor_ms(cursor):
    """Return ``(epoch_ms or None, item_name)`` for ordering comparisons.

    Comparisons happen in the millisecond domain, not the datetime domain.
    ``to_ms()`` truncates to whole milliseconds, so ``from_ms(to_ms(dt))``
    lands BEFORE the stored microsecond-precision value. Comparing the two
    shapes made a page's last item reappear on the next page.
    """
    if cursor in (None, '', 0, '0', False):
        return None, ''
    raw = str(cursor)
    if '|' not in raw:
        return None, ''
    raw_time, item_name = raw.split('|', 1)
    try:
        return int(raw_time), item_name
    except (ValueError, TypeError):
        return None, ''


# Model and joplin item type. joplin.item is deliberately absent: it holds
# raw protocol debris (locks, .sync state, unrecognised payloads) and is
# reachable only by path, for the raw fallback.
_DELTA_SOURCES = (
    ('joplin.note', TYPE_NOTE),
    ('joplin.folder', TYPE_FOLDER),
    ('joplin.tag', TYPE_TAG),
    ('joplin.resource', TYPE_RESOURCE),
)


def delta_items(env, cursor=None, limit=None):
    """Return ``(items, new_cursor, has_more)`` for the authenticated user.

    The single enumeration used by BOTH the sync-target route
    (``root:/:/delta``) and the legacy REST route (``/joplin/api/delta``).
    Items come back ordered by ``(updated_time, item_name)`` — a total order
    across all item types — and the cursor is the pair of the last item
    actually returned, so it never advances past items that were not sent.
    """
    limit = limit or _DELTA_PAGE_SIZE
    after_time, after_name = _decode_cursor(cursor)
    after_ms, _after_name_ms = _decode_cursor_ms(cursor)

    collected = []
    for model_name, type_ in _DELTA_SOURCES:
        domain = []
        if after_time:
            domain = [('updated_time', '>=', after_time)]
        records = env[model_name].with_context(active_test=False).search(
            domain, order='updated_time, id')
        for rec in records:
            collected.append(
                (rec.updated_time, '%s.md' % rec.joplin_id, type_))

    # Note-tag relations. They carry no timestamp of their own; the tag's is
    # the best available proxy and is what the client uses to notice a
    # re-tagging.
    tags = env['joplin.tag'].with_context(active_test=False).search(
        [], order='updated_time, id')
    seen = set()
    for tag in tags:
        for note in tag.note_ids:
            key = (note.joplin_id, tag.joplin_id)
            if key in seen:
                continue
            seen.add(key)
            collected.append((
                tag.updated_time,
                '%s.md' % notetag_id(note.joplin_id, tag.joplin_id),
                TYPE_NOTE_TAG,
            ))

    # Total order across every item type. The '>=' domain above is an index
    # hint; the exact cut happens here, in Python, so a tie on updated_time
    # is resolved by item_name instead of by a table-local id. Both sides of
    # the comparison are in epoch milliseconds.
    if after_ms is not None:
        collected = [row for row in collected
                     if (to_ms(row[0]), row[1]) > (after_ms, after_name)]

    collected.sort(key=lambda row: (to_ms(row[0]), row[1]))

    page = collected[:limit]
    has_more = len(collected) > limit

    items = []
    new_cursor = cursor
    for updated_time, item_name, type_ in page:
        items.append({
            'item_name': item_name,
            'type': type_,
            'updated_time': to_ms(updated_time),
            'jop_updated_time': to_ms(updated_time),
        })
        new_cursor = _encode_cursor(updated_time, item_name)

    if not page:
        # Nothing changed: keep the caller's cursor so the next poll starts
        # from the right place.
        if cursor not in (None, '', 0, False):
            new_cursor = cursor
        else:
            new_cursor = '0|'

    return items, new_cursor, has_more
