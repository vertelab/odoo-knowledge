import logging
from datetime import datetime, timezone

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class JoplinRevision(models.Model):
    _name = 'joplin.revision'
    _description = 'Joplin Revision (Version History)'
    _order = 'created_time desc'
    _rec_name = 'joplin_id'

    joplin_id = fields.Char(string='Joplin ID', required=True, index=True, copy=False)
    parent_id = fields.Char(string='Parent ID')
    note_id = fields.Many2one('joplin.note', string='Note', required=True,
                               index=True, ondelete='cascade')
    item_type = fields.Integer(string='Item Type', default=1)
    item_id = fields.Char(string='Item ID', index=True)
    item_updated_time = fields.Datetime(string='Item Updated Time')

    title_diff = fields.Text(string='Title Diff')
    body_diff = fields.Text(string='Body Diff')
    metadata_diff = fields.Text(string='Metadata Diff')

    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    updated_time = fields.Datetime(string='Updated Time', default=fields.Datetime.now)
    encryption_cipher_text = fields.Text(string='Encryption Cipher Text')
    encryption_applied = fields.Boolean(string='Encryption Applied', default=False)

    _sql_constraints = [
        ('joplin_id_uniq', 'unique(joplin_id)', 'Joplin ID must be unique!'),
    ]

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
        return super().create(vals_list)

    @api.model
    def _generate_joplin_id(self):
        import secrets
        return secrets.token_hex(16)
