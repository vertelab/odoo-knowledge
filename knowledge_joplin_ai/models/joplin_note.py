# -*- coding: utf-8 -*-
"""joplin.note — OKF-indexable (knowledge_joplin_ai).

WHY: a note IS knowledge — that is its entire purpose. Yet it lives in a
Text column that neither BM25 nor embeddings can see. Of all the bridges,
this is the most self-evident link to OKF.

Sources:
    title         — the note's name
    body          — the Markdown text (the actual content)

`body_html` is computed (from `body`) and is skipped by the generic
source — reading both would index the same text twice.

The model owns its SOURCES; `ai.okf.mixin` owns the fields and the flag.
"""

from odoo import models, fields


class JoplinNote(models.Model):
    _name = 'joplin.note'
    _inherit = ['joplin.note', 'ai.okf.mixin']

    # OKF tags: own relation table (a many2many cannot live on an
    # abstract mixin — it would give every inheriting model the same table).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'joplin_note_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    # ── Sources ────────────────────────────────────────────────────────
    #
    # `okf_body`  generic, captures `title` + `body`.
    # `okf_tags`  generic, captures `tag_ids` (the field name matches the
    #             word boundary 'tag'; the comodel joplin.tag does too).
    # `okf_links` generic, captures `folder_id` when/if joplin.folder
    #             carries the mixin.

    def _okf_artifact_type(self):
        """The bridge's own type (okf-mixin D12)."""
        return 'joplin_note'

    def _okf_summary_source(self):
        """The note's title IS its summary.

        Deterministic and free — no LLM needed to know that.
        """
        self.ensure_one()
        return self.title or None

    def _okf_dirty_fields(self):
        """Fields whose change makes the OKF fields stale.

        `body_html` is computed from `body` and need not be listed.
        `encryption_cipher_text` is encrypted text — it says nothing.
        """
        return {'title', 'body', 'tag_ids', 'folder_id', 'is_todo',
                'todo_completed', 'active'}

    def _okf_skip_reason(self):
        """Archived note = "empty for now", not "empty forever"."""
        return None

    # ── Registration (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Register the model for dirty indexing.

        Registration, not overriding: `_okf_indexable_models()` is an
        `@api.model` on an abstract model (measured on luke18 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('joplin.note')
        return res
