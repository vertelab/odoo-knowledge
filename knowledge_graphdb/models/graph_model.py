from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GraphModelConfig(models.Model):
    _name = 'knowledge.graph.model'
    _description = 'Graph Database Model Configuration'
    _order = 'sequence, id desc'

    sequence = fields.Integer(string='Sequence', default=10)
    user_id = fields.Many2one('res.users', string='User', index=True,
        help='Empty = global configuration for admin use')
    model_id = fields.Many2one('ir.model', string='Model', required=True,
        domain="[('model', 'not in', ('knowledge.graph.model',))]")
    domain = fields.Char(string='Domain Filter', default='[]',
        help='Odoo domain expression to filter records for sync')
    target_queue = fields.Char(string='Target Queue', required=True,
        help='RabbitMQ target queue name')
    key_field_ids = fields.Many2many('ir.model.fields', string='Key Fields',
        domain="[('model_id', '=', model_id)]",
        help='Fields to include in the payload. Leave empty to include all fields.')
    record_count = fields.Integer(string='Record Count',
        compute='_compute_record_count',
        help='Number of records matching the current domain')
    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='State', default='active', tracking=True)
    graph_status = fields.Char(string='Graph DB Status', readonly=True,
        help='Status feedback from the graph database')

    @api.depends('model_id', 'domain')
    def _compute_record_count(self):
        for record in self:
            if record.model_id and record.domain:
                try:
                    domain = eval(record.domain)
                    if not isinstance(domain, list):
                        record.record_count = 0
                        continue
                    Model = self.env.get(record.model_id.model)
                    if not Model:
                        record.record_count = 0
                        continue
                    record.record_count = Model.sudo().search_count(domain)
                except Exception as e:
                    _logger.warning("Failed to compute record count for %s: %s", record.display_name, e)
                    record.record_count = 0
            else:
                record.record_count = 0

    def action_sync_now(self):
        """Sync all records matching the domain to RabbitMQ."""
        self.ensure_one()
        if not self.model_id or not self.domain:
            raise UserError("Model and domain must be set before syncing.")
        Model = self.env.get(self.model_id.model)
        if not Model:
            raise UserError(f"Model {self.model_id.model} not found.")
        domain = eval(self.domain)
        records = Model.sudo().search(domain)
        publisher = self.env['knowledge.graph.publisher']
        publisher.publish_batch(self, records)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Completed',
                'message': f'Synced {len(records)} records to {self.target_queue}',
                'sticky': False,
            },
        }

    def action_update_graph_db(self):
        """Send a refresh admin message for this config to the graph database."""
        self.ensure_one()
        publisher = self.env['knowledge.graph.publisher']
        publisher.publish_admin('refresh', {
            'config_id': self.id,
            'model': self.model_id.model,
            'domain': self.domain,
            'target_queue': self.target_queue,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Update Requested',
                'message': f'Refresh request sent for {self.model_id.name}',
                'sticky': False,
            },
        }

    @api.model
    def create(self, vals):
        record = super().create(vals)
        if record.state == 'active':
            record._ensure_automation()
        return record

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            for record in self:
                if record.state == 'active':
                    record._ensure_automation()
                else:
                    record._remove_automation()
        return res

    def unlink(self):
        for record in self:
            record._remove_automation()
        return super().unlink()

    def _ensure_automation(self):
        """Create or update base.automation for this config."""
        self.ensure_one()
        if self.state != 'active':
            return
        Automation = self.env['base.automation']
        name = f"GraphDB: {self.model_id.name} [{self.id}]"
        automation = Automation.search([('name', '=', name)], limit=1)
        if not automation:
            Action = self.env['ir.actions.server']
            action = Action.create({
                'name': name,
                'model_id': self.model_id.id,
                'state': 'code',
                'code': self._get_automation_code(),
            })
            automation = Automation.create({
                'name': name,
                'model_id': self.model_id.id,
                'trigger': 'on_create|on_write|on_unlink',
                'filter_pre_domain': self.domain or '[]',
                'state': 'code',
                'action_server_ids': [(4, action.id)],
            })
        else:
            automation.write({
                'filter_pre_domain': self.domain or '[]',
            })

    def _remove_automation(self):
        """Unlink associated base.automation and its server action."""
        self.ensure_one()
        name = f"GraphDB: {self.model_id.name} [{self.id}]"
        automation = self.env['base.automation'].search([('name', '=', name)], limit=1)
        if automation:
            automation.action_server_ids.unlink()
            automation.unlink()

    def _get_automation_code(self):
        """Return the Python code for the automation server action."""
        config_id = self.id
        return f"""
if records and model:
    config = env['knowledge.graph.model'].browse({config_id})
    if config.exists() and config.state == 'active':
        publisher = env['knowledge.graph.publisher']
        op_map = {{'create': 'create', 'write': 'write', 'unlink': 'unlink'}}
        operation = op_map.get(env.context.get('trigger_operation', 'write'), 'write')
        for record in records:
            publisher.publish(model, record.id, operation, config)
"""
