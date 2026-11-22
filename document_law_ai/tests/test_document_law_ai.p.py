# -*- coding: utf-8 -*-
"""Tests for the document.law AI capability (document_law_ai).

Two halves, tested separately:

  * the OKF bridge — mixin inheritance, sources, skip rules, registration
  * the agent capability — the skill, the three tools, the attachment

What matters is that the sources read the right fields, that the tools
behave (bounded, honest about truncation, refusing to guess the company),
and that the attachment is additive and survives an upgrade — not that the
indexer itself works, which is `ai_agent_core`'s contract and tested there.
"""

import json
import os
import xml.etree.ElementTree as ET

from odoo.tests import common, tagged

from odoo.addons.document_law_ai.models.document_law import (
    AGENT_XMLID, COWORKER_XMLID)


@tagged('-at_install', 'post_install')
class TestDocumentLawAi(common.TransactionCase):
    """The bridge: mixin inheritance, sources, skip rules, registration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Law = cls.env['document.law']

    def _law(self, designation='SFS 2024:123', title='Test Law',
             text='The law text.', **kwargs):
        vals = {
            'rss_beteckning': designation,
            'rss_titel': title,
            'rss_text': text,
            'rss_dok_id': 'sfs-2024-123',
        }
        vals.update(kwargs)
        return self.Law.create(vals)

    # ── 7.1 the mixin is actually applied ─────────────────────────────

    def test_01_model_inherits_okf_mixin(self):
        """document.law must carry the mixin, or nothing else works."""
        self.assertIn(
            'ai.okf.mixin', self.Law._inherit,
            'document.law must inherit ai.okf.mixin')

    def test_02_okf_fields_exist(self):
        """The mixin's fields must be present on the model."""
        for fname in ('okf_body', 'okf_summary', 'okf_tags', 'okf_links',
                      'okf_dirty', 'okf_indexed_at'):
            self.assertIn(
                fname, self.Law._fields,
                f'{fname} missing on document.law')

    def test_03_okf_tags_relation_table_is_own(self):
        """The many2many must use this module's own relation table.

        A many2many on an abstract mixin would give every inheriting model
        the same table; each bridge declares its own.
        """
        field = self.Law._fields['okf_tags']
        self.assertEqual(field.relation, 'document_law_okf_tag_rel')

    # ── 7.2 sources ───────────────────────────────────────────────────

    def test_04_artifact_type(self):
        """The bridge reports its own artifact type."""
        law = self._law()
        self.assertEqual(law._okf_artifact_type(), 'document_law')

    def test_05_body_source_contains_designation_title_and_text(self):
        """All three parts belong to the law's meaning (design D2)."""
        law = self._law(
            designation='SFS 2024:123', title='Dataskyddslagen',
            text='1 § Denna lag gäller personuppgifter.')
        body = law._okf_body_source()
        self.assertIn('SFS 2024:123', body)
        self.assertIn('Dataskyddslagen', body)
        self.assertIn('personuppgifter', body)

    def test_06_body_source_without_text_falls_back_to_designation_title(self):
        """An empty `rss_text` falls back to designation + title, not HTML."""
        law = self._law(text=False)
        body = law._okf_body_source()
        self.assertIn('SFS 2024:123', body)
        self.assertIn('Test Law', body)

    def test_07_summary_source_is_the_designation(self):
        """The designation IS the summary — deterministic, no LLM needed."""
        law = self._law(designation='SFS 2024:123', title='Dataskyddslagen')
        self.assertEqual(law._okf_summary_source(), 'SFS 2024:123')

    def test_08_summary_source_falls_back_to_title(self):
        """Without a designation the title summarises the law."""
        law = self._law(designation=False, title='Dataskyddslagen')
        self.assertEqual(law._okf_summary_source(), 'Dataskyddslagen')

    # ── dirty fields and skip rules ───────────────────────────────────

    def test_09_dirty_fields_cover_what_changes_meaning(self):
        """The fields that change what the law means."""
        law = self._law()
        dirty = law._okf_dirty_fields()
        for fname in ('rss_text', 'rss_beteckning', 'rss_titel', 'active'):
            self.assertIn(fname, dirty, f'{fname} should mark the law dirty')

    def test_10_nothing_is_skipped(self):
        """A law is never filtered out (task 3.6)."""
        law = self._law()
        self.assertIsNone(law._okf_skip_reason())

    def test_11_archived_law_keeps_its_flag(self):
        """Archived is "empty for now", not "empty forever"."""
        law = self._law()
        law.write({'active': False})
        self.assertIsNone(
            law._okf_skip_reason(),
            'an archived law must not be permanently skipped')

    def test_12_create_flags_law_for_indexing(self):
        """A new law must be queued for indexing."""
        law = self._law()
        self.assertTrue(
            law.okf_dirty, 'a new law should be flagged for indexing')

    # ── 7.3 registration ──────────────────────────────────────────────

    def test_13_model_is_registered_as_indexable(self):
        """The model must be in the indexer's list, or nothing is indexed."""
        models = self.env['ai.okf.mixin']._okf_indexable_models()
        self.assertIn('document.law', models)

    # ── artifact type record ──────────────────────────────────────────

    def test_14_artifact_type_record_exists(self):
        """The data file's artifact type must be loadable and correct."""
        artifact = self.env.ref(
            'document_law_ai.artifact_type_document_law',
            raise_if_not_found=False)
        self.assertTrue(artifact, 'artifact type record missing')
        self.assertEqual(artifact.name, 'document_law')
        self.assertEqual(artifact.bridge_module, 'document_law_ai')
        self.assertEqual(artifact.model_id.model, 'document.law')

    def test_15_debug_action_is_bound_to_the_model(self):
        """The OKF debug action must be bound to document.law."""
        action = self.env.ref(
            'document_law_ai.action_okf_document_law',
            raise_if_not_found=False)
        self.assertTrue(action, 'OKF debug action missing')
        self.assertEqual(action.model_id.model, 'document.law')
        self.assertEqual(action.binding_model_id.model, 'document.law')


@tagged('-at_install', 'post_install')
class TestDocumentLawAiCapability(common.TransactionCase):
    """The agent: skill, three tools, attachment to the general assistant."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tool = cls.env['ai.tool']
        cls.Law = cls.env['document.law']
        cls.Agent = cls.env.ref(AGENT_XMLID)

    def _tool(self, name):
        return self.Tool.search([('name', '=', name)], limit=1)

    def _law(self, designation='SFS 2024:123', title='Test Law',
             text='The law text.', **kwargs):
        vals = {
            'rss_beteckning': designation,
            'rss_titel': title,
            'rss_text': text,
            'rss_dok_id': 'sfs-2024-123',
        }
        vals.update(kwargs)
        return self.Law.create(vals)

    # ── 7.4 agent, skill and tools exist and are attached ─────────────

    def test_16_skill_exists_and_attached(self):
        skill = self.env.ref('document_law_ai.skill_law_reading')
        self.assertTrue(skill.active)
        self.assertTrue(skill.recipe_text)
        self.assertIn(skill, self.Agent.skill_ids)

    def test_17_tools_exist_and_are_attached(self):
        names = ['law_search', 'law_get', 'law_interpret']
        for name in names:
            tool = self._tool(name)
            self.assertTrue(tool, f'tool {name} missing')
            self.assertEqual(tool.risk_level, 'read_only')
            self.assertIn(tool, self.Agent.tool_ids)

    def test_18_agent_exists_and_is_active(self):
        self.assertTrue(self.Agent.active)
        self.assertEqual(self.Agent.status, 'active')
        self.assertTrue(self.Agent.ai_role)

    # ── 5.2 the no-legal-advice boundary is in the skill ──────────────

    def test_19_skill_states_the_no_legal_advice_boundary(self):
        skill = self.env.ref('document_law_ai.skill_law_reading')
        recipe = skill.recipe_text
        # Assert the substance, not one exact phrasing: the recipe must tell
        # the agent it cannot determine compliance and must defer to a
        # qualified person. Pinning an exact sentence would break on any
        # rewording while proving nothing extra.
        self.assertIn('cannot determine compliance', recipe)
        self.assertIn('qualified', recipe)
        self.assertIn('legal determination', recipe)

    # ── 7.5 the attachment is additive and pre-existing agents survive ─

    def test_20_agent_attached_to_general_assistant(self):
        coworker = self.env.ref(COWORKER_XMLID)
        link = self.env['ai.coworker.agent'].search([
            ('coworker_id', '=', coworker.id),
            ('agent_id', '=', self.Agent.id),
        ])
        self.assertEqual(len(link), 1, 'law agent must be attached once')
        self.assertEqual(link.role, 'member')

    def test_21_pre_existing_agents_survive(self):
        """The attachment is additive: the assistant's agents remain."""
        coworker = self.env.ref(COWORKER_XMLID)
        pre_existing = [
            'ai_agent_core.agent_default_core',
            'ai_agent_core.agent_odoo_business',
            'ai_agent_core.agent_office_dokument',
            'ai_agent_core.agent_news_watcher',
        ]
        attached = coworker.agent_ids.mapped('agent_id')
        for xmlid in pre_existing:
            agent = self.env.ref(xmlid, raise_if_not_found=False)
            if agent:
                self.assertIn(
                    agent, attached,
                    f'{xmlid} must survive the law attachment')

    def test_22_ensure_attachment_is_idempotent(self):
        """Calling the method twice must not duplicate link rows.

        It runs on every upgrade, so repeated runs must add nothing — and
        it must use `(4, id)`-style append, not `(6, 0, [...])` replace.
        """
        coworker = self.env.ref(COWORKER_XMLID)
        before = self.env['ai.coworker.agent'].search_count([
            ('coworker_id', '=', coworker.id),
            ('agent_id', '=', self.Agent.id),
        ])
        self.Law._ensure_agent_attachment()
        after = self.env['ai.coworker.agent'].search_count([
            ('coworker_id', '=', coworker.id),
            ('agent_id', '=', self.Agent.id),
        ])
        self.assertEqual(before, after)
        self.assertEqual(after, 1)

    def test_23_ensure_attachment_tolerates_missing_coworker(self):
        """`_ensure_agent_attachment` must not raise when the coworker is gone.

        A raising `ref()` would abort the install, so the method resolves
        the coworker with `raise_if_not_found=False` and returns early.
        """
        orig_ref = self.env.ref

        def fake_ref(xmlid, raise_if_not_found=True):
            if xmlid == COWORKER_XMLID:
                return self.env['ai.coworker']
            return orig_ref(xmlid, raise_if_not_found=raise_if_not_found)

        self.env.__class__.ref = staticmethod(fake_ref)
        try:
            self.Law._ensure_agent_attachment()  # must not raise
        finally:
            self.env.__class__.ref = staticmethod(orig_ref)

    # ── 7.6 the <function> runs on upgrade too ────────────────────────

    def test_24_attach_function_is_outside_noupdate(self):
        """The regression guard: the <function> must run on upgrade.

        A `<function>` inside `noupdate="1"` runs on install only. Parse
        the data file and walk the function's parent chain — if any
        ancestor carries `noupdate="1"`, the attachment would not survive
        an upgrade.
        """
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'law_agent_attach.xml')
        root = ET.parse(path).getroot()

        parents = {child: parent for parent in root.iter()
                   for child in parent}
        functions = [el for el in root.iter()
                     if el.tag == 'function'
                     and el.get('name') == '_ensure_agent_attachment']
        self.assertEqual(
            len(functions), 1,
            'expected exactly one _ensure_agent_attachment <function>')

        node = functions[0]
        while node in parents:
            node = parents[node]
            self.assertNotEqual(
                node.get('noupdate'), '1',
                'the <function> sits inside a noupdate block — it would '
                'run on install only and not survive an upgrade')

    # ── 4.x tool behaviour ────────────────────────────────────────────

    def test_25_law_search_finds_by_free_text(self):
        self._law(designation='SFS 2024:1', title='Dataskyddslagen',
                  text='Om personuppgifter och integritet.')
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool({'query': 'personuppgifter'}))
        self.assertGreaterEqual(out['count'], 1)
        self.assertTrue(any('Dataskyddslagen' in (r['title'] or '')
                            for r in out['results']))

    def test_26_law_search_finds_by_designation(self):
        self._law(designation='SFS 2024:777', title='Särskild lag',
                  text='x')
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool({'designation': '2024:777'}))
        self.assertEqual(out['count'], 1)
        self.assertEqual(out['results'][0]['designation'], 'SFS 2024:777')

    def test_27_law_search_narrows_by_department(self):
        self._law(designation='SFS 2024:2', title='A',
                  rss_organ='Finansdepartementet')
        self._law(designation='SFS 2024:3', title='B',
                  rss_organ='Justitiedepartementet', rss_dok_id='sfs-2024-3')
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool(
            {'department': 'Finansdepartementet'}))
        self.assertEqual(out['count'], 1)
        self.assertEqual(out['results'][0]['department'],
                         'Finansdepartementet')

    def test_28_law_search_narrows_by_date_range(self):
        self._law(designation='SFS 2020:1', title='Old', rss_dok_id='old',
                  rss_datum='2020-01-01')
        self._law(designation='SFS 2024:1', title='New', rss_dok_id='new',
                  rss_datum='2024-01-01')
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool(
            {'date_from': '2023-01-01', 'date_to': '2025-01-01'}))
        self.assertEqual(out['count'], 1)
        self.assertEqual(out['results'][0]['title'], 'New')

    # ── 7.8 truncation is reported, not silent ────────────────────────

    def test_29_law_search_reports_truncation(self):
        """A capped search must say so, or the agent assumes it saw all."""
        for i in range(5):
            self._law(designation='SFS 2024:%d' % i,
                      title='Truncation probe', rss_dok_id='trunc-%d' % i)
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool(
            {'query': 'Truncation probe', 'limit': 2}))
        self.assertTrue(out['truncated'])
        self.assertEqual(out['count'], 2)
        self.assertGreater(out['total_matches'], 2)
        self.assertIn('message', out)

    def test_30_law_search_reports_empty_plainly(self):
        """Nothing matching must be said plainly — no invented law."""
        tool = self._tool('law_search')
        out = json.loads(tool._execute_tool(
            {'query': 'zzz-no-such-law-zzz'}))
        self.assertEqual(out['count'], 0)
        self.assertIn('message', out)

    def test_31_law_get_returns_text_not_html(self):
        """`law_get` returns readable text, not raw markup."""
        self._law(designation='SFS 2024:9', title='Text probe',
                  text='1 § Klartext utan markup.',
                  rss_html='<p>1 § Klartext utan markup.</p>',
                  rss_dok_id='text-probe')
        tool = self._tool('law_get')
        out = json.loads(tool._execute_tool({'document_id': 'text-probe'}))
        self.assertIn('Klartext utan markup', out['text'])
        self.assertNotIn('<p>', out['text'])

    def test_32_law_get_reports_truncation(self):
        """A long law must report truncation so the agent can ask for more."""
        self._law(designation='SFS 2024:10', title='Long',
                  text='x' * 500, rss_dok_id='long-law')
        tool = self._tool('law_get')
        out = json.loads(tool._execute_tool(
            {'document_id': 'long-law', 'max_chars': 100}))
        self.assertTrue(out['truncated'])
        self.assertEqual(len(out['text']), 100)
        self.assertEqual(out['text_chars'], 500)

    def test_33_law_get_missing_law_errors(self):
        tool = self._tool('law_get')
        out = json.loads(tool._execute_tool({'document_id': 'nope'}))
        self.assertIn('error', out)
        self.assertFalse(out.get('retryable', True))

    # ── 7.7 law_interpret refuses when no company can be resolved ─────

    def test_34_law_interpret_fails_without_a_company(self):
        """No company → an actionable error, never a guess (design D5)."""
        self._law(designation='SFS 2024:11', title='Company probe',
                  rss_dok_id='company-probe')
        tool = self._tool('law_interpret')

        # Strip every resolution path: no session in context, no coworker
        # in context, and an empty env.company. `company` is a lazy_property
        # that caches on the instance, so assigning it on the env overrides
        # the lookup for this call only.
        env = self.env(context=dict(
            self.env.context,
            _ai_context_model=False,
            _ai_context_id=False,
            ai_coworker_id=False,
        ))
        env.company = self.env['res.company']
        out = json.loads(tool.with_env(env)._execute_tool(
            {'document_id': 'company-probe'}))

        self.assertIn('error', out)
        self.assertIn('company', out['error'].lower())

    def test_35_law_interpret_returns_context_and_law_text(self):
        """With a company, the tool returns context plus law text (D4)."""
        law = self._law(designation='SFS 2024:12', title='Interpret probe',
                        text='1 § Lagen kräver X.', rss_dok_id='interp')
        tool = self._tool('law_interpret')
        out = json.loads(tool._execute_tool({'law_id': law.id}))
        self.assertEqual(out['company']['id'], self.env.company.id)
        self.assertIn('Lagen kräver X', out['law']['text'])
        self.assertIn('company_context', out)
        self.assertIn('company_context_empty', out)

    # ── 4.5 no tool calls an LLM itself ───────────────────────────────

    def test_36_no_tool_calls_an_llm(self):
        """The interpreting is the agent's job (design D4).

        The tools must not invoke a model themselves. Note that reading the
        session's coworker is NOT an LLM call — it is how `law_interpret`
        finds the current company (design D4/D5), so the word 'coworker' is
        legitimate. What must not appear is an actual LLM invocation.
        """
        for name in ('law_search', 'law_get', 'law_interpret'):
            code = self._tool(name).code or ''
            for forbidden in ('run(', 'provider', 'chat(',
                              '_okf_summarize_with_coworker',
                              '.generate(', 'completion('):
                self.assertNotIn(
                    forbidden, code,
                    f'{name} must not call an LLM (found {forbidden!r})')

    # ── sandbox safety ────────────────────────────────────────────────

    def test_37_tool_code_does_not_catch_bare_exception_names(self):
        """The sandbox's `__builtins__` is a restricted dict with no
        exception classes, so a bare `except Exception` / `except
        (TypeError, ValueError)` raises NameError the moment the clause is
        evaluated. The tools must reach the classes through `builtins`
        (aliased at the top of the code) or avoid catching altogether.
        """
        import re
        for name in ('law_search', 'law_get', 'law_interpret'):
            code = self._tool(name).code or ''
            # Names the tool itself binds (e.g. `Exception = _b.Exception`).
            aliased = set(re.findall(r'^(\w+)\s*=\s*_b\.\w+', code,
                                     re.MULTILINE))
            for match in re.finditer(r'except\s+([^:\n]+):', code):
                clause = match.group(1).strip()
                # Drop the `as <var>` binding.
                clause = re.sub(r'\s+as\s+\w+$', '', clause).strip()
                parts = ([p.strip() for p in clause.strip('()').split(',')]
                         if clause.startswith('(') else [clause])
                for part in parts:
                    self.assertTrue(
                        part.startswith('_b.') or part in aliased,
                        f'{name}: except clause references {part!r}, which '
                        'is not bound in the tool namespace — it would '
                        'raise NameError in the sandbox')
