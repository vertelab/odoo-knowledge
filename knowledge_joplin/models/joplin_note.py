import logging
import json
from datetime import datetime, timezone

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import html2plaintext

import markdown

_logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = [
    'fenced_code',
    'codehilite',
    'tables',
    'toc',
    'nl2br',
    'extra',
]


class JoplinNote(models.Model):
    _name = 'joplin.note'
    _description = 'Joplin Note'
    _order = 'updated_time desc'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    joplin_id = fields.Char(string='Joplin ID', required=True, index=True, copy=False)
    title = fields.Char(string='Title', required=True, tracking=True)
    body = fields.Text(string='Body (Markdown)', default='')
    body_html = fields.Html(string='Body (HTML)', compute='_compute_body_html',
                             sanitize=False, store=False)
    folder_id = fields.Many2one('joplin.folder', string='Folder',
                                 index=True, ondelete='set null')
    user_id = fields.Many2one('res.users', string='User', required=True,
                               default=lambda self: self.env.user,
                               ondelete='cascade', tracking=True)
    tag_ids = fields.Many2many('joplin.tag', 'joplin_tag_note_rel', 'note_id', 'tag_id',
                                string='Tags')
    resource_ids = fields.One2many('joplin.resource', 'note_id', string='Resources')
    revision_ids = fields.One2many('joplin.revision', 'note_id', string='Revisions')

    object_ref = fields.Reference(
        selection=lambda self: self._selection_object_ref(),
        string='Object',
    )

    is_todo = fields.Boolean(string='Is To-Do', default=False, tracking=True)
    todo_due = fields.Datetime(string='Due Date')
    todo_completed = fields.Datetime(string='Completed Date')
    author = fields.Char(string='Author')
    source_url = fields.Char(string='Source URL')
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    altitude = fields.Float(string='Altitude', digits=(10, 2))
    is_conflict = fields.Boolean(string='Is Conflict', default=False)
    order = fields.Float(string='Order', default=0)
    markup_language = fields.Integer(string='Markup Language', default=1)
    source = fields.Char(string='Source')
    source_application = fields.Char(string='Source Application')
    application_data = fields.Text(string='Application Data')

    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    updated_time = fields.Datetime(string='Updated Time', default=fields.Datetime.now)
    user_created_time = fields.Datetime(string='User Created Time')
    user_updated_time = fields.Datetime(string='User Updated Time')
    deleted_time = fields.Datetime(string='Deleted Time')

    is_shared = fields.Boolean(string='Is Shared', default=False)
    share_id = fields.Char(string='Share ID')
    conflict_original_id = fields.Char(string='Conflict Original ID')

    encryption_cipher_text = fields.Text(string='Encryption Cipher Text')
    encryption_applied = fields.Boolean(string='Encryption Applied', default=False)
    master_key_id = fields.Char(string='Master Key ID')

    active = fields.Boolean(string='Active', default=True, tracking=True)

    _sql_constraints = [
        ('joplin_id_uniq', 'unique(joplin_id)', 'Joplin ID must be unique!'),
    ]

    @api.model
    def _selection_object_ref(self):
        models = self.env['ir.model'].search([('transient', '=', False)])
        excluded = ('ir.', 'joplin.', 'mail.', 'bus.', 'base.', 'web.', 'website.', '_')
        return [
            (m.model, m.name)
            for m in models
            if not m.model.startswith(excluded)
        ]

    @api.depends('body', 'markup_language')
    def _compute_body_html(self):
        for note in self:
            if note.body and note.markup_language == 1:
                try:
                    note.body_html = markdown.markdown(note.body, extensions=MARKDOWN_EXTENSIONS)
                except Exception:
                    note.body_html = f'<pre>{note.body}</pre>'
            elif note.body:
                note.body_html = note.body
            else:
                note.body_html = ''

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'joplin_id' in fields_list and not res.get('joplin_id'):
            res['joplin_id'] = self._generate_joplin_id()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            now = datetime.utcnow()
            if not vals.get('joplin_id'):
                vals['joplin_id'] = self._generate_joplin_id()
            if not vals.get('created_time'):
                vals['created_time'] = now
            if not vals.get('updated_time'):
                vals['updated_time'] = now
        records = super().create(vals_list)
        records._log_event(1)
        return records

    def write(self, vals):
        now = datetime.utcnow()
        changed = any(k in vals for k in ('title', 'body', 'folder_id', 'is_todo', 'tag_ids'))
        if changed:
            new_vals = {'title': vals.get('title'), 'body': vals.get('body')}
            for note in self:
                self._create_revision(note, new_vals)
            vals['updated_time'] = now

        if 'active' in vals and not vals['active']:
            vals['deleted_time'] = now

        res = super().write(vals)

        if vals.get('active') is False:
            self._log_event(3)
        elif changed:
            self._log_event(2)
        return res

    def unlink(self):
        self._log_event(3)
        return super().unlink()

    def _create_revision(self, note, new_vals):
        diff_lib = self._get_diff_lib()
        if not diff_lib:
            return

        dmp = diff_lib.diff_match_patch()
        old_title = note.title or ''
        old_body = note.body or ''
        new_title = new_vals.get('title', old_title) or ''
        new_body = new_vals.get('body', old_body) or ''
        old_metadata = '{}'

        title_diff = dmp.diff_main(old_title, new_title)
        dmp.diff_cleanupSemantic(title_diff)
        title_patches = dmp.patch_make(title_diff)
        title_diff_str = dmp.patch_toText(title_patches)

        body_diff = dmp.diff_main(old_body, new_body)
        dmp.diff_cleanupSemantic(body_diff)
        body_patches = dmp.patch_make(body_diff)
        body_diff_str = dmp.patch_toText(body_patches)

        self.env['joplin.revision'].create({
            'note_id': note.id,
            'joplin_id': self._generate_joplin_id(),
            'item_id': note.joplin_id,
            'item_updated_time': datetime.utcnow(),
            'title_diff': title_diff_str,
            'body_diff': body_diff_str,
            'metadata_diff': old_metadata,
        })

    @api.model
    def _get_diff_lib(self):
        try:
            import diff_match_patch as dmp
            return dmp
        except ImportError:
            return None

    def _log_event(self, event_type):
        self.env['joplin.event'].create([
            {'item_type': 1, 'item_id': r.joplin_id, 'event_type': event_type}
            for r in self
        ])

    @api.model
    def _generate_joplin_id(self):
        import secrets
        return secrets.token_hex(16)

    def message_post(self, **kwargs):
        return super().message_post(**kwargs)

    def toggle_todo(self):
        self.write({'is_todo': not self.is_todo})

    @api.onchange('is_todo')
    def _onchange_is_todo(self):
        if self.is_todo and not self.todo_due:
            self.todo_due = fields.Datetime.now()

    def action_trash(self):
        self.write({'active': False})

    def action_restore(self):
        self.write({'active': True, 'deleted_time': False})

    def action_permanent_delete(self):
        return super().unlink()
