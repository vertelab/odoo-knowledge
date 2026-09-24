{
    'name': 'Knowledge: Graph Database Bridge',
    'version': '18.0.1.0.2',
    'category': 'Knowledge',
    'summary': 'Publish Odoo model changes to RabbitMQ for graph database sync',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/knowledge_graphdb',
    'license': 'AGPL-3',
    # 'base_automation' (Odoo core) owns the base.automation model used by
    # this module (self.env['base.automation']). This used to say 'automation',
    # which is the OCA module in OCA/automation — it is named 'automation_oca'
    # in 18.0 and was never installed, so the whole module set aborted with:
    #   UserError: You are trying to install module "knowledge_graphdb" which
    #   depends on module "automation", but the latter is not available.
    'depends': ['base', 'mail', 'base_automation'],
    'external_dependencies': {
        'python': ['pika'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/graph_model_views.xml',
        'views/res_users_views.xml',
        'data/data.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}
