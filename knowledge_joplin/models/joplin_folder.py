import logging
from datetime import datetime, timezone

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class JoplinFolder(models.Model):
    _name = 'joplin.folder'
    _description = 'Joplin Folder (Notebook)'
    _order = 'name'
    _rec_name = 'name'

    joplin_id = fields.Char(string='Joplin ID', required=True, index=True, copy=False)
    name = fields.Char(string='Name', required=True, translate=True)
    parent_id = fields.Many2one('joplin.folder', string='Parent Folder',
                                 index=True, ondelete='cascade')
    child_ids = fields.One2many('joplin.folder', 'parent_id', string='Subfolders')
    user_id = fields.Many2one('res.users', string='User', required=True,
                               default=lambda self: self.env.user, ondelete='cascade')
    note_ids = fields.One2many('joplin.note', 'folder_id', string='Notes')
    note_count = fields.Integer(string='Note Count', compute='_compute_note_count')

    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    updated_time = fields.Datetime(string='Updated Time', default=fields.Datetime.now)
    user_created_time = fields.Datetime(string='User Created Time')
    user_updated_time = fields.Datetime(string='User Updated Time')

    is_shared = fields.Boolean(string='Is Shared', default=False)
    share_id = fields.Char(string='Share ID')
    icon = fields.Char(string='Icon')

    encryption_cipher_text = fields.Text(string='Encryption Cipher Text')
    encryption_applied = fields.Boolean(string='Encryption Applied', default=False)
    master_key_id = fields.Char(string='Master Key ID')

    # Joplin carries deleted_time on EVERY item type, not only on notes.
    # Without it the sync protocol cannot report a deleted notebook, and
    # _FOLDER_FIELDS (which maps it) raised a KeyError on every folder.
    # No 'tracking' here: joplin.folder does not inherit mail.thread.
    deleted_time = fields.Datetime(string='Deleted Time')
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('joplin_id_uniq', 'unique(joplin_id)', 'Joplin ID must be unique!'),
    ]

    @api.depends('note_ids')
    def _compute_note_count(self):
        for folder in self:
            folder.note_count = len(folder.note_ids)

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
        changed = any(k in vals for k in ('name', 'parent_id', 'icon'))
        # Trust the client's updated_time when it supplies one: the sync
        # ingest passes the timestamp from the Joplin item, and overwriting
        # it here made every ingest look like a modification.
        if changed and 'updated_time' not in vals:
            vals['updated_time'] = datetime.utcnow()

        if 'active' in vals and not vals['active'] and 'deleted_time' not in vals:
            vals['deleted_time'] = datetime.utcnow()

        res = super().write(vals)
        if vals.get('active') is False:
            self._log_event(3)
        elif changed:
            self._log_event(2)
        return res

    def action_trash(self):
        self.write({'active': False})

    def action_restore(self):
        self.write({'active': True, 'deleted_time': False})

    def unlink(self):
        self._log_event(3)
        return super().unlink()

    def _log_event(self, event_type):
        self.env['joplin.event'].create([
            {'item_type': 2, 'item_id': r.joplin_id, 'event_type': event_type}
            for r in self
        ])

    @api.model
    def _generate_joplin_id(self):
        import secrets
        return secrets.token_hex(16)
