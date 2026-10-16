# -*- coding: utf-8 -*-
"""document.law — OKF-indexable (document_law_ai).

WHY: a Swedish statute IS knowledge. `document_law` is in active
production use — thousands of law records refreshed daily from the
Riksdag RSS feed — but the records are plain rows that neither BM25 nor
embeddings can reach as knowledge. This bridge makes them OKF concepts,
so a law can be found by meaning and not only by its designation.

MODEL CHOICE (design D1): `document.law` is its own model. It merely
*depends* on `document_page`; it does not inherit it. Bridging
`document.page` again would be a second bridge on a model that already
has one (`knowledge_document_ai`) and would index nothing about the
laws. The bridge therefore inherits `document.law`, with its own
relation table.

Sources:
    rss_beteckning — the designation ("SFS 2024:123"), the summary
    rss_titel      — the title
    rss_text       — the plain-text body (NOT `rss_html`; the model
                     already stores plain text, so reading the Html and
                     converting it would be work with no benefit)

The model owns its SOURCES; `ai.okf.mixin` owns the fields and the flag.
"""

import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

AGENT_XMLID = 'document_law_ai.agent_law_specialist'
COWORKER_XMLID = 'ai_agent_core.coworker_default_assistent'


class DocumentLaw(models.Model):
    _name = 'document.law'
    _inherit = ['document.law', 'ai.okf.mixin']

    # OKF tags: own relation table (a many2many cannot live on an
    # abstract mixin — it would give every inheriting model the same table).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'document_law_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    # ── Sources ────────────────────────────────────────────────────────
    #
    # `okf_body`  overridden below (designation + title + text).
    # `okf_tags`  generic: no tag source exists on document.law — the list
    #             comes back empty, not wrong.
    # `okf_links` generic: `company_id` (res.company via base_ai).

    def _okf_artifact_type(self):
        """The bridge's own type (okf-mixin D12)."""
        return 'document_law'

    def _okf_body_source(self):
        """The law's content: designation + title + plain text.

        Design D2. A law is identified by its designation ("SFS 2024:123")
        and named by its title; both belong to its meaning. `rss_text` is
        the plain-text body — the model already stores it, so we read it
        rather than converting `rss_html`.

        If `rss_text` is empty the body falls back to designation + title
        rather than to the Html (design D2): an empty body means "empty for
        now" and the indexer keeps the flag, rather than indexing markup.
        """
        self.ensure_one()
        parts = [self.rss_beteckning or '', self.rss_titel or '']
        if self.rss_text:
            parts.append(self.rss_text)
        return '\n\n'.join(p for p in parts if p) or None

    def _okf_summary_source(self):
        """The designation IS the law's summary.

        Design D2: the designation ("SFS 2024:123") is deterministic and
        free — no LLM needed to know what summarises a law. The title is
        the fallback when the designation is missing.
        """
        self.ensure_one()
        return self.rss_beteckning or self.rss_titel or None

    def _okf_dirty_fields(self):
        """Fields whose change makes the OKF fields stale.

        `rss_text` changes what the law says; `rss_beteckning` and
        `rss_titel` change how it is identified and named; `active` is the
        archive flag. `rss_html` is NOT listed — the body reads `rss_text`,
        and the two are written together by the RSS cron.
        """
        return {'rss_text', 'rss_beteckning', 'rss_titel', 'rss_organ',
                'rss_datum', 'active'}

    def _okf_skip_reason(self):
        """Nothing on a law is filtered out.

        Decision (task 3.6): unlike `document.page` (where `type ==
        'category'` is a folder, not a document) a `document.law` row is
        always a law. An archived law (`active == False`) is "empty for
        now", NOT "empty forever": it keeps `okf_dirty` and is re-indexed
        if it is reactivated. We therefore return None here, not a skip
        reason.
        """
        self.ensure_one()
        return None

    # ── Registration (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Register the model for dirty indexing.

        Registration, not overriding: `_okf_indexable_models()` is an
        `@api.model` on an abstract model (measured on luke18 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('document.law')
        return res

    # ── Agent attachment (design D7) ───────────────────────────────────

    # `@api.model` + `records=None`, matching the house precedent
    # `ai_agent_core.ai.tool._ensure_builtin_tool_records` — the same
    # `<function ... eval="[obj()]"/>` call shape. `obj()` evaluates to an
    # empty recordset; `call_kw` passes it as a positional argument, so the
    # method must accept it (without `records` the call raises
    # "takes 1 positional argument but 2 were given").
    @api.model
    def _ensure_agent_attachment(self, records=None):
        """Attach the law agent to Allmän assistent, additively.

        Called from `data/law_agent_attach.xml` with a `<function>` placed
        OUTSIDE any noupdate block, so it runs on install AND on upgrade.
        A `<function>` inside `noupdate="1"` runs on install only — the
        defect found and fixed in `knowledge_joplin_ai`.

        `records` receives the empty recordset that `eval="[obj()]"`
        evaluates to; it is unused — the method operates on the
        environment.

        Idempotent: membership is checked before writing, so repeated runs
        (every upgrade) add nothing. Tolerates a missing coworker:
        `ref(..., raise_if_not_found=False)` returns an empty recordset and
        the method returns early — a raising `ref()` would abort the
        install. Additive: a link row is created only when none exists, so
        the assistant's pre-existing agents survive.

        The attachment is a new `ai.coworker.agent` row, not a `(4, id)`
        write: `ai.coworker.agent_ids` is a **One2many** to
        `ai.coworker.agent`, so it cannot take `(4, id)`. This matches the
        house pattern (`ai_coworker._ensure_link`, and the
        `coworker_agent_*` records in `default_coworker.xml`).
        """
        coworker = self.env.ref(COWORKER_XMLID, raise_if_not_found=False)
        if not coworker:
            _logger.info(
                'document_law_ai: coworker %s not found — law agent created '
                'but not attached', COWORKER_XMLID)
            return

        agent = self.env.ref(AGENT_XMLID, raise_if_not_found=False)
        if not agent:
            _logger.info(
                'document_law_ai: agent %s not found — nothing to attach',
                AGENT_XMLID)
            return

        link = self.env['ai.coworker.agent'].search([
            ('coworker_id', '=', coworker.id),
            ('agent_id', '=', agent.id),
        ], limit=1)
        if link:
            return

        self.env['ai.coworker.agent'].create({
            'coworker_id': coworker.id,
            'agent_id': agent.id,
            'role': 'member',
            'sequence': 60,
        })
        _logger.info(
            'document_law_ai: attached law agent %s to %s',
            agent.name, coworker.name)
