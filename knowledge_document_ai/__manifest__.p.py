# -*- coding: utf-8 -*-
{
    'name': 'Knowledge: Document AI',
    'version': '18.0.1.1.0',
    'summary': 'OKF indexing of document.page',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bridge module for OKF indexing of knowledge documents.

        Puts `ai.okf.mixin` on `document.page` so that knowledge pages
        become OKF concepts.

        WHY: a knowledge page IS knowledge — that is its entire purpose.
        Yet the text lives in `document.page.history` and is only reached
        via `history_head`; neither BM25 nor embeddings see it without
        this bridge.

        MODEL CHOICE: `document.page` comes from OCA's `document_page`
        (18.0.2.1.2). Odoo Enterprise `knowledge.article` does not exist
        in this installation. This is the stack's knowledge document —
        the same model that document_law, document_publish,
        knowledge_forum_website and knowledge_category_access build on.

        NOISE FILTER: `type == 'category'` is deliberately skipped (a
        category is a folder, not a document). Archived pages keep their
        flag and are re-indexed if reactivated.

        AUTOINSTALL: the module installs automatically as soon as both
        ai_agent_core and document_page are present — the same pattern as
        knowledge_joplin_ai. A knowledge page that cannot become knowledge
        is a page nobody finds; the bridge should not be a choice.

        The model owns its SOURCES; the mixin in ai_agent_core owns the
        fields and the flag. No domain is named in the core.
    """,
    'depends': [
        'ai_agent_core',
        'document_page',
    ],
    'data': [
        'data/okf_artifact_types_document.xml',
        'data/okf_debug_actions.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': True,
}
