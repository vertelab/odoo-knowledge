{
    'name': 'Knowledge: Graph Database Bridge',
    'version': '18.0.1.0.4',
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
    'author': 'Vertel Sverige AB',
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
    # Installable so the module keeps loading: it is INSTALLED in production
    # (ledningssystem, since 2026-10-12). `installable: False` does not just
    # hide a module from the Apps list — Odoo skips loading its code entirely,
    # so an installed module's models vanish from the registry and anything
    # touching them raises KeyError. That regression was hit on 2026-10-15.
    #
    # The module is being uninstalled in production (decision 2026-10-15);
    # once that is done this can go back to False to keep it out of module
    # sets. Until then it must stay True.
    'installable': True,
    'auto_install': False,
}
