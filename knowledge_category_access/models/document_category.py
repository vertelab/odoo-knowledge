# Copyright 2022 Manuel Regidor <manuel.regidor@sygel.es>
# Copyright 2024 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError


class DocumentPage(models.Model):
    _inherit = "document.page"

    
    parent_groups_id = fields.Many2many(
        'res.groups',
        string="Parent Groups",
        related='parent_id.groups_id',
        readonly=True
    )
    parent_user_ids = fields.Many2many(
        'res.users',
        string="Parent Users",
        related='parent_id.user_ids',
        readonly=True
    )
