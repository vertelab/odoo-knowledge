# -*- coding: utf-8 -*-
{
    'name': 'Knowledge: Joplin AI',
    'version': '18.0.1.0.0',
    'summary': 'OKF indexing of joplin.note',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bridge module for OKF indexing of Joplin notes.

        Puts `ai.okf.mixin` on `joplin.note` so that the notes become OKF
        concepts.

        WHY: a note IS knowledge — that is its entire purpose. Yet it
        lives in a Text column that neither BM25 nor embeddings can see.
        Of all the bridges, this is the most self-evident link to OKF.

        AUTOINSTALL: the module installs automatically as soon as both
        ai_agent_core and knowledge_joplin are present. A note that cannot
        become knowledge is a note nobody finds — the bridge should not be
        a choice.

        VERIFIED 2026-09-24 (okf_kn): installs cleanly together with
        knowledge_joplin (c9729f7). A note becomes a concept of type
        joplin_note, with the title as summary, the body from body, and
        tag_ids as tags.

        The model owns its SOURCES; the mixin in ai_agent_core owns the
        fields and the flag. No domain is named in the core.
    """,
    'depends': [
        'ai_agent_core',
        'knowledge_joplin',
    ],
    'data': [
        'data/okf_artifact_types_joplin.xml',
        'data/okf_debug_actions.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': True,
}
