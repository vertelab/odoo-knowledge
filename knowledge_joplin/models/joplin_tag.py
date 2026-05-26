import logging
from datetime import datetime, timezone

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class JoplinTag(models.Model):
    _name = 'joplin.tag'
    _description = 'Joplin Tag'
    _order = 'name'
    _rec_name = 'name'

    joplin_id = fields.Char(string='Joplin ID', required=True, index=True, copy=False)
    name = fields.Char(string='Name', required=True, translate=True)
    user_id = fields.Many2one('res.users', string='User', required=True,
                               default=lambda self: self.env.user, ondelete='cascade')
    note_ids = fields.Many2many('joplin.note', 'joplin_tag_note_rel', 'tag_id', 'note_id',
                                 string='Notes')
    note_count = fields.Integer(string='Note Count', compute='_compute_note_count')

    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    updated_time = fields.Datetime(string='Updated Time', default=fields.Datetime.now)
    user_created_time = fields.Datetime(string='User Created Time')
    user_updated_time = fields.Datetime(string='User Updated Time')

    is_shared = fields.Boolean(string='Is Shared', default=False)
    parent_id = fields.Char(string='Parent ID')
    encryption_cipher_text = fields.Text(string='Encryption Cipher Text')
    encryption_applied = fields.Boolean(string='Encryption Applied', default=False)

    color = fields.Integer(string='Color', default=0)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('joplin_id_uniq', 'unique(joplin_id)', 'Joplin ID must be unique!'),
    ]

    @api.depends('note_ids')
    def _compute_note_count(self):
        for tag in self:
            tag.note_count = len(tag.note_ids)

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
        if 'name' in vals:
            vals['updated_time'] = datetime.utcnow()
        res = super().write(vals)
        if vals.get('active') is False:
            self._log_event(3)
        elif 'name' in vals:
            self._log_event(2)
        return res

    def unlink(self):
        self._log_event(3)
        return super().unlink()

    def _log_event(self, event_type):
        self.env['joplin.event'].create([
            {'item_type': 5, 'item_id': r.joplin_id, 'event_type': event_type}
            for r in self
        ])

    @api.model
    def _generate_joplin_id(self):
        import secrets
        return secrets.token_hex(16)


class JoplinNoteTag(models.Model):
    _name = 'joplin.note.tag'
    _description = 'Joplin Note-Tag Relation'

    note_id = fields.Many2one('joplin.note', string='Note', required=True,
                               ondelete='cascade')
    tag_id = fields.Many2one('joplin.tag', string='Tag', required=True,
                              ondelete='cascade')

    _sql_constraints = [
        ('note_tag_uniq', 'unique(note_id, tag_id)', 'Note-Tag relation must be unique!'),
    ]
