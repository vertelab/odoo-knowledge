{
    'name': 'Knowledge: Graph Database Bridge',
    'version': '18.0.1.0.0',
    'category': 'Knowledge',
    'summary': 'Publish Odoo model changes to RabbitMQ for graph database sync.',
    'description': '''
Graph Database Bridge
=====================

    Publish Odoo model changes to RabbitMQ for graph database sync.

    Features:

        - Guided Wizards: Step-by-step dialogs for data entry.
        - UI Integration: Extends 2 view(s) in the Odoo interface.
        - Extends Odoo: Builds on knowledge.graph.model, knowledge.graph.publisher.
    ''',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/knowledge_graphdb',
    'license': 'AGPL-3',
    'depends': ['base', 'mail', 'automation'],
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
