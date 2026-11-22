from odoo import models, fields, api
from uuid import uuid4


class ResUsers(models.Model):
    _inherit = 'res.users'

    graph_topic = fields.Char(string='Graph DB Topic', readonly=True,
        help='Unique topic identifier for this user\'s graph database context')
    graph_model_ids = fields.One2many('knowledge.graph.model', 'user_id',
        string='AI Data Context',
        help='Model configurations synced to this user\'s graph database')

    @api.model
    def create(self, vals):
        user = super().create(vals)
        if not user.graph_topic:
            user._generate_graph_topic()
        return user

    def _generate_graph_topic(self):
        """Generate a unique graph topic based on login."""
        for user in self:
            topic = f"{user.login}-{uuid4().hex[:8]}"
            user.graph_topic = topic
            try:
                publisher = self.env['knowledge.graph.publisher']
                publisher.publish_admin('provision_database', {
                    'tenant_id': self.env.cr.dbname,
                    'graph_topic': topic,
                    'user_id': user.id,
                    'login': user.login,
                })
            except Exception:
                pass  # Publisher not yet available
