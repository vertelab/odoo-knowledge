import logging
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class JoplinApiToken(models.Model):
    _name = 'joplin.api.token'
    _description = 'Joplin API Token'
    _rec_name = 'token'

    token = fields.Char(string='Token', required=True, index=True, copy=False,
                        default=lambda self: self._generate_token())
    user_id = fields.Many2one('res.users', string='User', required=True,
                              default=lambda self: self.env.user,
                              ondelete='cascade')
    name = fields.Char(string='Description')
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('token_uniq', 'unique(token)', 'Token must be unique!'),
    ]

    @api.model
    def _generate_token(self):
        return secrets.token_hex(16)

    @api.model
    def authenticate(self, token):
        if not token or len(token) != 32:
            return self.env.user
        record = self.search([('token', '=', token), ('active', '=', True)], limit=1)
        return record.user_id if record else self.env.user
