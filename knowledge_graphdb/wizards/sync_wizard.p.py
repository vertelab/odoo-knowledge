from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GraphSyncWizard(models.TransientModel):
    _name = 'knowledge.graph.sync.wizard'
    _description = 'Graph Sync Wizard'

    config_id = fields.Many2one('knowledge.graph.model', string='Configuration',
        required=True, readonly=True)
    model_name = fields.Char(string='Model', related='config_id.model_id.model',
        readonly=True)
    domain = fields.Char(string='Domain', related='config_id.domain',
        readonly=True)
    record_count = fields.Integer(string='Records to Sync',
        compute='_compute_record_count')
    state = fields.Selection([
        ('draft', 'Ready'),
        ('syncing', 'Syncing...'),
        ('done', 'Completed'),
    ], string='Status', default='draft')

    @api.depends('config_id', 'domain')
    def _compute_record_count(self):
        for wizard in self:
            if wizard.config_id and wizard.domain:
                try:
                    Model = self.env.get(wizard.model_name)
                    if Model:
                        wizard.record_count = Model.sudo().search_count(
                            eval(wizard.domain))
                        return
                except Exception:
                    _logger.warning("Failed to count records", exc_info=True)
            wizard.record_count = 0

    def action_sync(self):
        self.ensure_one()
        self.state = 'syncing'
        config = self.config_id
        if not config.model_id or not config.domain:
            raise UserError("Model and domain must be configured.")
        Model = self.env.get(config.model_id.model)
        if not Model:
            raise UserError(f"Model {config.model_id.model} not found.")
        domain = eval(config.domain)
        records = Model.sudo().search(domain)
        publisher = self.env['knowledge.graph.publisher']
        publisher.publish_batch(config, records)
        self.state = 'done'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Completed',
                'message': f'Synced {len(records)} records to {config.target_queue}',
                'sticky': False,
            },
        }
