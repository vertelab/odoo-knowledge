# -*- coding: utf-8 -*-
{
    'name': 'Knowledge: Joplin AI',
    'version': '18.0.1.1.0',
    'summary': 'OKF indexing of joplin.note + note-saving tools for the Odoo specialist',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bridge module for Joplin notes and the AI coworker.

        OKF INDEXING: puts `ai.okf.mixin` on `joplin.note` so that the
        notes become OKF concepts.

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

        NOTE-SAVING CAPABILITY (joplin-note-ai-capability): a skill and
        three tools that let the Odoo specialist preserve knowledge as
        Joplin notes — from free text, from an existing Odoo record, or
        from the current conversation. All creation goes through
        `joplin.note.create()`, so notes carry a generated identifier and
        a creation event. The tools are `write`-risk and pass the same
        approval gate as the agent's other write tools.

        The skill and tools are attached to the Odoo specialist from
        `data/joplin_agent_attach.xml` — a `<function>` calling
        `joplin.note._ensure_agent_attachment()`, placed outside any
        noupdate block so it runs on install AND on upgrade. The method
        resolves the agent with `raise_if_not_found=False`, so the link
        is additive and the module installs whether or not the agent
        exists. Nothing is added to ai_agent_core: an installation
        without knowledge_joplin carries no part of this.
    """,
    'depends': [
        'ai_agent_core',
        'knowledge_joplin',
    ],
    'data': [
        'data/okf_artifact_types_joplin.xml',
        'data/okf_debug_actions.xml',
        'data/joplin_skills.xml',
        'data/joplin_tools.xml',
        'data/joplin_agent_attach.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': True,
}
