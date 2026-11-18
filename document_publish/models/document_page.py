from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class DocumentPage(models.Model):
    _inherit = "document.page"

    def open_page(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action = {
            'type': 'ir.actions.act_url',
            "name": "Document Page Manual",
            "url": f"{base_url}/knowledge/page/{self.id}",
            "target": "new"
        }
        return action

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
