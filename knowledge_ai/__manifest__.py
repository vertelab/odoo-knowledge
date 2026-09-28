# -*- coding: utf-8 -*-
{
    'name': 'Knowledge: AI',
    'version': '18.0.1.0.0',
    'summary': 'OKF-indexering av joplin.note',
    'category': 'Hidden',
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bryggmodul för OKF-indexering av kunskapsanteckningar.

        Lägger `ai.okf.mixin` på joplin.note så att anteckningarna blir
        OKF-koncept.

        VARFÖR: en anteckning ÄR kunskap — det är hela dess syfte. Ändå
        ligger den i en Text-kolumn som varken BM25 eller embeddings ser.
        Här är kopplingen till OKF mest självklar av alla bryggor.

        MODELLVAL: `knowledge.article` finns inte i denna Odoo-installation
        (Odoo Enterprise). Kunskapsmodellen här är `joplin.note` från
        knowledge_joplin. Bryggan indexerar den.

        VERIFIERAD 2026-09-24 (okf_kn): installerar rent tillsammans med
        knowledge_joplin (c9729f7). En anteckning blir ett koncept med
        typen joplin_note, titeln som sammanfattning, kroppen ur body, och
        joplin_tag_ids som taggar.

        Modellen äger sina KÄLLOR; mixinen i ai_agent_core äger fälten
        och flaggan. Ingen domän nämns i kärnan.
    """,
    'depends': [
        'ai_agent_core',
        'knowledge_joplin',
    ],
    'data': [
        'data/okf_artifact_types_knowledge.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': False,
}
