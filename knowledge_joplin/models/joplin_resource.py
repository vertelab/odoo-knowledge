import logging
import base64
import mimetypes
from datetime import datetime, timezone

from odoo import models, fields, api
from odoo.exceptions import ValidationError

try:
    import magic as pymagic
except ImportError:
    pymagic = None

_logger = logging.getLogger(__name__)


class JoplinResource(models.Model):
    _name = 'joplin.resource'
    _description = 'Joplin Resource (Attachment)'
    _order = 'created_time desc'
    _rec_name = 'name'

    joplin_id = fields.Char(string='Joplin ID', required=True, index=True, copy=False)
    name = fields.Char(string='Name')
    mime = fields.Char(string='MIME Type')
    filename = fields.Char(string='Filename')
    file_extension = fields.Char(string='File Extension')
    datas = fields.Binary(string='File Data', attachment=True)
    datas_fname = fields.Char(string='File Name')
    file_size = fields.Integer(string='File Size (bytes)')

    note_id = fields.Many2one('joplin.note', string='Note', index=True,
                               ondelete='cascade',
                               default=lambda self:
                                   self.env.context.get('default_note_id')
                                   or (self.env.context.get('active_id')
                                       if self.env.context.get('active_model') == 'joplin.note'
                                       else False))
    user_id = fields.Many2one('res.users', string='User', required=True,
                               default=lambda self: self.env.user,
                               ondelete='cascade')

    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    updated_time = fields.Datetime(string='Updated Time', default=fields.Datetime.now)
    user_created_time = fields.Datetime(string='User Created Time')
    user_updated_time = fields.Datetime(string='User Updated Time')
    blob_updated_time = fields.Datetime(string='Blob Updated Time')

    is_shared = fields.Boolean(string='Is Shared', default=False)
    share_id = fields.Char(string='Share ID')

    ocr_text = fields.Text(string='OCR Text')
    ocr_details = fields.Text(string='OCR Details')
    ocr_status = fields.Integer(string='OCR Status', default=0)
    ocr_error = fields.Text(string='OCR Error')
    ocr_driver_id = fields.Integer(string='OCR Driver ID')

    encryption_cipher_text = fields.Text(string='Encryption Cipher Text')
    encryption_applied = fields.Boolean(string='Encryption Applied', default=False)
    encryption_blob_encrypted = fields.Boolean(string='Blob Encrypted', default=False)
    master_key_id = fields.Char(string='Master Key ID')

    active = fields.Boolean(string='Active', default=True)

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
            filename = vals.get('filename') or vals.get('datas_fname', '')
            if filename:
                if '.' in filename:
                    vals['file_extension'] = filename.rsplit('.', 1)[1]
                if not vals.get('name'):
                    vals['name'] = filename
            if not vals.get('mime'):
                if filename:
                    guessed = mimetypes.guess_type(filename)[0]
                    if guessed:
                        vals['mime'] = guessed
            if vals.get('datas'):
                raw = base64.b64decode(vals['datas'])
                vals['file_size'] = len(raw)
                if not vals.get('mime') and pymagic:
                    try:
                        mime = pymagic.from_buffer(raw, mime=True)
                        if mime:
                            vals['mime'] = mime
                    except Exception:
                        pass
        records = super().create(vals_list)
        records._log_event(1)
        return records

    def write(self, vals):
        if 'name' in vals or 'datas' in vals or 'filename' in vals:
            vals['updated_time'] = datetime.utcnow()
            if vals.get('datas'):
                raw = base64.b64decode(vals['datas'])
                vals['file_size'] = len(raw)
                filename = vals.get('filename') or vals.get('datas_fname', '')
                if filename:
                    if '.' in filename:
                        vals['file_extension'] = filename.rsplit('.', 1)[1]
                    if not vals.get('name'):
                        vals['name'] = filename
                if 'mime' not in vals:
                    if filename:
                        guessed = mimetypes.guess_type(filename)[0]
                        if guessed:
                            vals['mime'] = guessed
                    if 'mime' not in vals and pymagic:
                        try:
                            mime = pymagic.from_buffer(raw, mime=True)
                            if mime:
                                vals['mime'] = mime
                        except Exception:
                            pass
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
            {'item_type': 4, 'item_id': r.joplin_id, 'event_type': event_type}
            for r in self
        ])

    @api.model
    def _generate_joplin_id(self):
        import secrets
        return secrets.token_hex(16)
