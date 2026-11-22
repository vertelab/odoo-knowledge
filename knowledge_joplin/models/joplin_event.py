import logging
from datetime import datetime, timezone, timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class JoplinEvent(models.Model):
    _name = 'joplin.event'
    _description = 'Joplin Change Event (for delta sync)'
    _order = 'id asc'

    item_type = fields.Integer(string='Item Type', required=True)
    item_id = fields.Char(string='Item Joplin ID', required=True, index=True)
    event_type = fields.Integer(string='Event Type', required=True,
                                 help='1=Create, 2=Update, 3=Delete')
    created_time = fields.Datetime(string='Created Time', default=fields.Datetime.now)
    source = fields.Integer(string='Source', default=0)
    before_change_item = fields.Text(string='Before Change Item')

    @api.autovacuum
    def _cleanup_old_events(self):
        cutoff = datetime.utcnow() - timedelta(days=90)
        old = self.search([('created_time', '<', cutoff)])
        old.unlink()
        return len(old)
