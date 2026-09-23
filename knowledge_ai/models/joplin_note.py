# -*- coding: utf-8 -*-
"""joplin.note — OKF-indexerbar (knowledge_ai).

VARFÖR: en anteckning ÄR kunskap — det är hela dess syfte. Ändå ligger
den i en Text-kolumn som varken BM25 eller embeddings ser. Här är
kopplingen till OKF mest självklar av alla bryggor.

Källor:
    title         — anteckningens namn
    body          — Markdown-texten (det egentliga innehållet)

`body_html` är compute (av `body`) och hoppas över av den generiska
källan — att läsa båda vore att indexera samma text två gånger.

Modellen äger sina KÄLLOR; `ai.okf.mixin` äger fälten och flaggan.
"""

from odoo import models, fields


class JoplinNote(models.Model):
    _name = 'joplin.note'
    _inherit = ['joplin.note', 'ai.okf.mixin']

    # OKF-taggar: egen relationstabell (en many2many kan inte ligga
    # pa en abstrakt mixin — den ger samma tabell for alla arvande).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'joplin_note_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    # ── Källor ─────────────────────────────────────────────────────────
    #
    # `okf_body` är generisk och fångar `title` + `body`.
    # `okf_tags`  är generisk och fångar `joplin_tag_ids` (målmodellen
    #             joplin.tag innehåller 'tag').
    # `okf_links` är generisk och fångar `folder_id` när/om joplin.folder
    #             får mixinen.

    def _okf_artifact_type(self):
        """Bryggans egen typ (okf-mixin D12)."""
        return 'joplin_note'

    def _okf_summary_source(self):
        """Anteckningens titel ÄR dess sammanfattning.

        Deterministisk och gratis — ingen LLM behövs för att veta det.
        """
        self.ensure_one()
        return self.title or None

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        `body_html` är compute av `body` och behöver inte listas.
        `encryption_cipher_text` är krypterad text — den säger inget.
        """
        return {'title', 'body', 'tag_ids', 'folder_id', 'is_todo',
                'todo_completed', 'active'}

    def _okf_skip_reason(self):
        """Arkiverad anteckning = "tomt just nu", inte "tomt för alltid"."""
        return None

    # ── Registrering (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Registrera modellen för dirty-indexering.

        Registrering, inte överridning: `_okf_indexable_models()` är
        `@api.model` på en abstrakt modell (mätt på luke18 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('joplin.note')
        return res
