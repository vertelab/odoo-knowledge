{
    'name': 'Knowledge: Joplin Backend',
    'version': '18.0.1.0.0',
    'category': 'Knowledge',
    'summary': 'Joplin-compatible note-taking backend with REST API and sync protocol',
    'description': """
Implements Joplin's full REST API and sync protocol in Odoo.
Stores notes, folders, tags, resources, and revisions in joplin.* models.
Features Markdown to HTML conversion, chatter, follower-based sharing,
versioning via diffs, and personal notes with user_id isolation.
    """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/knowledge_joplin',
    'license': 'AGPL-3',
    'depends': ['mail', 'web'],
    'external_dependencies': {
        'python': ['markdown', 'diff-match-patch'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/joplin_note_views.xml',
        'views/joplin_folder_views.xml',
        'views/joplin_tag_views.xml',
        'views/joplin_resource_views.xml',
        'views/joplin_menus.xml',
    ],
    'demo': ['demo/demo_data.xml'],
    'application': True,
    'installable': True,
    'auto_install': False,
    'assets': {},
}
