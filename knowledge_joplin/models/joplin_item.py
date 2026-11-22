import logging
from datetime import datetime, timezone

from odoo import models, fields

_logger = logging.getLogger(__name__)


class JoplinItem(models.Model):
    """Joplin sync item — generic path/content entry used by the Joplin
    WebDAV-style sync API (delta, batch_items, stat, read, write, delete)."""

    _name = 'joplin.item'
    _description = 'Joplin Item'
    _order = 'updated_time asc'
    _rec_name = 'path'

    path = fields.Char(string='Path', required=True, index=True)
    content = fields.Text(string='Content', default='')
    updated_time = fields.Datetime(
        string='Updated Time',
        default=lambda self: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )

    _sql_constraints = [
        ('path_uniq', 'UNIQUE (path)', 'Item path must be unique.'),
    ]
