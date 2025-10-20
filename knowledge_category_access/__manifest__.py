{
    "name": "Document Category Access Group",
    "summary": "Adds access group capability to document category via document_page_access_group.",
    "description": """
        This module adds the ability to assign access groups to 'document category'
        by depending on the document_page_access_group from OCA/knowledge.
    """,
    "version": "18.0.1.0.0",
    "category": "Knowledge Management",
    "author": "Vertel AB",
    "depends": [
        "document_page_access_group",
    ],
    "license": "AGPL-3",
    "data": [
        'views/document_page.xml',
        'security/ir.model.access.csv',
        'security/security_post_rules.xml'
    ],
    "installable": True,
    "application": False,
}
