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

import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

AGENT_XMLID = 'ai_agent_core.agent_odoo_business'


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

    # ── Agent attachment (joplin-note-ai-capability, design D5) ────────

    # `@api.model` + `records=None`, matching the house precedent
    # `ai_agent_core.ai.tool._ensure_builtin_tool_records` — the same
    # `<function ... eval="[obj()]"/>` call shape. `obj()` evaluates to an
    # empty recordset; `call_kw` passes it as a positional argument, so the
    # method must accept it (without `records` the call raises
    # "takes 1 positional argument but 2 were given").
    @api.model
    def _ensure_agent_attachment(self, records=None):
        """Attach the note skill and the three note tools to the specialist.

        Called from `data/joplin_agent_attach.xml` with a `<function>`
        placed OUTSIDE any noupdate block, so it runs on install AND on
        upgrade. A `<function>` inside `noupdate="1"` runs on install
        only — that is why the attachment previously did not survive an
        upgrade.

        `records` receives the empty recordset that `eval="[obj()]"`
        evaluates to; it is unused — the method operates on the
        environment.

        Idempotent: membership is checked before writing, so repeated
        runs (every upgrade) add nothing. Tolerates a missing agent:
        `ref(..., raise_if_not_found=False)` returns an empty recordset
        and the method returns early — a raising `ref()` would abort the
        install. Additive: `(4, id)` appends, so the agent's own
        `odoo-core` skill and seven model tools survive.
        """
        agent = self.env.ref(AGENT_XMLID, raise_if_not_found=False)
        if not agent:
            _logger.info(
                'knowledge_joplin_ai: agent %s not found — note skill and '
                'tools created but not attached', AGENT_XMLID)
            return

        skill = self.env.ref(
            'knowledge_joplin_ai.skill_joplin_note',
            raise_if_not_found=False)
        tools = self.env['ai.tool'].browse([
            self.env.ref('knowledge_joplin_ai.tool_note_create',
                         raise_if_not_found=False).id,
            self.env.ref('knowledge_joplin_ai.tool_note_create_from_record',
                         raise_if_not_found=False).id,
            self.env.ref(
                'knowledge_joplin_ai.tool_note_create_from_conversation',
                raise_if_not_found=False).id,
        ]).exists()

        vals = {}
        if skill and skill not in agent.skill_ids:
            vals['skill_ids'] = [(4, skill.id)]
        missing_tools = tools - agent.tool_ids
        if missing_tools:
            vals['tool_ids'] = [(4, t.id) for t in missing_tools]
        if vals:
            agent.write(vals)
            _logger.info(
                'knowledge_joplin_ai: attached note skill and %d tool(s) '
                'to %s', len(missing_tools), agent.name)
