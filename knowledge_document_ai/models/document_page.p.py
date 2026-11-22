# -*- coding: utf-8 -*-
"""document.page — OKF-indexable (knowledge_document_ai).

WHY: a knowledge page IS knowledge. `content` (Html) lives in a history
table (`document.page.history`) and is reached via `history_head` —
neither BM25 nor embeddings see it without this bridge.

MODEL CHOICE: `document.page` comes from OCA's `document_page`
(18.0.2.1.2), not Odoo Enterprise `knowledge.article` — the latter does
not exist in this installation. This is the stack's knowledge document:
the same model that `document_law`, `document_publish`,
`knowledge_forum_website` and `knowledge_category_access` build on.

Sources:
    name            — the page title (the summary)
    content         — the Html text (compute + inverse + search, NOT stored)
    draft_name      — latest revision's name (related -> history_head)
    draft_summary   — latest revision's summary (related -> history_head)

`content` is NOT stored on `document.page` — it lives in the history and
is exposed as a compute. It is still readable, and the generic
`_okf_body_source()` does capture Html fields. We read it explicitly
anyway, for the same reason `project_ai` reads `description`: we want to
know exactly what gets indexed rather than trust a heuristic.

The model owns its SOURCES; `ai.okf.mixin` owns the fields and the flag.
"""

from odoo import models, fields


class DocumentPage(models.Model):
    _name = 'document.page'
    _inherit = ['document.page', 'ai.okf.mixin']

    # OKF tags: own relation table (a many2many cannot live on an
    # abstract mixin — it would give every inheriting model the same table).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'document_page_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    # ── Sources ────────────────────────────────────────────────────────
    #
    # `okf_body`  overridden below (name + content).
    # `okf_tags`  generic: no tag source exists on document.page (OCA's
    #             document_page_tag is a separate module not installed
    #             here) — the list comes back empty, not wrong.
    # `okf_links` generic: `parent_id` (document.page carries the mixin),
    #             `company_id` (res.company via base_ai),
    #             `content_uid` (res.users via base_ai)

    def _okf_artifact_type(self):
        """The bridge's own type (okf-mixin D12)."""
        return 'document_page'

    def _okf_body_source(self):
        """The page content: the title plus the rendered text.

        `content` is Html and may contain markup — the mixin's
        `_okf_html_to_text()` is called by the indexer, not here. We
        return the parts and let the indexer do its job.

        `draft_name`/`draft_summary` are included: they describe WHAT was
        changed and belong to the page's meaning. They are `related` to
        `history_head` and change as the history grows.
        """
        self.ensure_one()
        parts = [self.name or '']
        if self.draft_summary:
            parts.append(self.draft_summary)
        if self.content:
            parts.append(self.content)
        return '\n\n'.join(p for p in parts if p) or None

    def _okf_summary_source(self):
        """No own summary — let the fallback chain build one from the body.

        WHY NOT THE TITLE: `summary` is what gets embedded and what
        `search_vector` is generated from (`summary || title`). Returning the
        title here made every page indexable only by its name — the body was
        read into `source_text` but never reached the vector. Measured on
        ledningssystem 2026-10-26: a 12 000-character page produced a
        34-character summary, and searching for any word in the body returned
        nothing.

        Returning None hands over to `_okf_build_summary()`:
            2. text within the limit   (free, deterministic)
            3. Allman assistent        (LLM, only when the body is too long)
            4. truncation              (logged warning)

        `source_text` is unchanged by this — the body is still the version
        key, so an unchanged page still produces no new version.
        """
        self.ensure_one()
        return None

    def _okf_dirty_fields(self):
        """Fields whose change makes the OKF fields stale.

        `content` is a compute (not stored) but changes through
        `_inverse_content`, which writes a new `document.page.history`
        row — the `write()` hook therefore sees `content` in `vals` and
        flags the record. Verified against OCA's implementation
        (document_page.py lines 31-35).

        `content_uid`/`content_date` are related+stored to the history and
        change on every edit — they say WHO and WHEN, not WHAT, and are
        therefore excluded (they would flag the record on every save
        without the text having changed).
        """
        return {'name', 'content', 'draft_name', 'draft_summary',
                'parent_id', 'active'}

    def _okf_skip_reason(self):
        """Two cases are deliberately skipped; the rest is "empty for now".

        1. `type == 'category'` — a category is a FOLDER, not a document.
           It has no text of its own (only `template` for its children).
           Indexing it would create one empty concept per folder. The same
           class of noise filter as `knowledge_joplin`'s Junk/Trash.

        2. `active == False` — an archived page is "empty for now", NOT
           "empty forever". It keeps `okf_dirty` and is re-indexed if it
           is reactivated. We therefore return None here, not a skip
           reason.
        """
        self.ensure_one()
        if self.type == 'category':
            return 'category (folder, not document)'
        return None

    # ── Registration (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Register the model for dirty indexing.

        Registration, not overriding: `_okf_indexable_models()` is an
        `@api.model` on an abstract model (measured on luke18 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('document.page')
        return res
