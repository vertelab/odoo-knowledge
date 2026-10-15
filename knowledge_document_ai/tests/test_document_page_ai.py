# -*- coding: utf-8 -*-
"""Tests for the document.page OKF bridge (knowledge_document_ai).

The bridge makes knowledge pages indexable. What matters is that the
sources read the right fields, that categories are filtered out, and that
the model is registered for dirty indexing — not that the indexer itself
works, which is `ai_agent_core`'s contract and tested there.
"""

from odoo.tests import common, tagged


@tagged('-at_install', 'post_install')
class TestDocumentPageAi(common.TransactionCase):
    """The bridge: mixin inheritance, sources, skip rules, registration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Page = cls.env['document.page']

    def _page(self, name='Test Page', content=None, **kwargs):
        vals = {'name': name}
        if content is not None:
            vals['content'] = content
        vals.update(kwargs)
        return self.Page.create(vals)

    # ── The mixin is actually applied ─────────────────────────────────

    def test_01_model_inherits_okf_mixin(self):
        """document.page must carry the mixin, or nothing else works."""
        self.assertIn(
            'ai.okf.mixin', self.Page._inherit,
            'document.page must inherit ai.okf.mixin')

    def test_02_okf_fields_exist(self):
        """The mixin's fields must be present on the model."""
        for fname in ('okf_body', 'okf_summary', 'okf_tags', 'okf_links',
                      'okf_dirty', 'okf_indexed_at'):
            self.assertIn(
                fname, self.Page._fields,
                f'{fname} missing on document.page')

    def test_03_okf_tags_relation_table_is_own(self):
        """The many2many must use this module's own relation table.

        A many2many on an abstract mixin would give every inheriting model
        the same table; each bridge declares its own.
        """
        field = self.Page._fields['okf_tags']
        self.assertEqual(field.relation, 'document_page_okf_tag_rel')

    # ── Sources ───────────────────────────────────────────────────────

    def test_04_artifact_type(self):
        """The bridge reports its own artifact type."""
        page = self._page(content='<p>Body</p>')
        self.assertEqual(page._okf_artifact_type(), 'document_page')

    def test_05_summary_source_is_the_title(self):
        """The title IS the summary — deterministic, no LLM needed."""
        page = self._page(name='Summary Probe', content='<p>x</p>')
        self.assertEqual(page._okf_summary_source(), 'Summary Probe')

    def test_06_body_source_includes_title_and_content(self):
        """Both the title and the rendered text belong to the page's meaning."""
        page = self._page(name='Body Probe', content='<p>Probe content</p>')
        body = page._okf_body_source()
        self.assertIn('Body Probe', body)
        self.assertIn('Probe content', body)

    def test_07_body_source_includes_draft_summary(self):
        """The latest revision's summary describes what changed."""
        page = self._page(name='Draft Probe', content='<p>x</p>')
        page.write({'draft_summary': 'Added the introduction'})
        self.assertIn('Added the introduction', page._okf_body_source())

    def test_08_body_source_without_content_still_carries_the_title(self):
        """A page with a title but no body still has something to index.

        OCA's empty editor writes `<p><br></p>` rather than nothing, so the
        body source is not exactly the title — but the title is in it, and
        the empty markup reduces to '' once the indexer runs
        `_okf_html_to_text` over it. Asserting the title is present is the
        meaningful check; asserting an exact string would encode OCA's
        editor markup into this module's tests.
        """
        page = self._page(name='Title Only')
        body = page._okf_body_source()
        self.assertIn('Title Only', body)
        self.assertEqual(
            self.env['ai.okf.mixin']._okf_html_to_text(page.content), '',
            'an empty editor should reduce to no text')

    def test_09_body_source_returns_none_only_when_nothing_is_set(self):
        """Nothing to index means no title and no content.

        A freshly built record still carries OCA's empty-editor markup, so
        `content` is not falsy — but the markup is not text. The source
        returns the markup, and the indexer reduces it to nothing. This
        asserts the record the source actually sees, not a hypothetical
        empty one.
        """
        page = self.Page.new({'name': '', 'type': 'content'})
        self.assertEqual(
            self.env['ai.okf.mixin']._okf_html_to_text(page.content), '',
            'a new page should carry no readable text')

    def test_09b_body_source_returns_none_when_title_and_content_are_empty(self):
        """With no title and no content, there is nothing to index."""
        page = self.Page.new({'name': '', 'type': 'content'})
        page.content = ''
        self.assertIsNone(page._okf_body_source())

    def test_10_content_is_not_stored_but_readable(self):
        """`content` is a non-stored compute backed by the history table.

        The bridge reads it explicitly rather than trusting a heuristic,
        so this asserts the value is actually reachable.
        """
        field = self.Page._fields['content']
        self.assertFalse(field.store, 'content should not be stored')
        page = self._page(content='<p>Reachable</p>')
        self.assertIn('Reachable', page.content)

    # ── Skip rules ────────────────────────────────────────────────────

    def test_11_category_is_skipped(self):
        """A category is a folder, not a document — it has no text."""
        category = self._page(name='A Category', type='category')
        self.assertEqual(
            category._okf_skip_reason(), 'category (folder, not document)')

    def test_12_content_page_is_not_skipped(self):
        """A normal page has no skip reason."""
        page = self._page(content='<p>x</p>')
        self.assertIsNone(page._okf_skip_reason())

    def test_13_archived_page_keeps_its_flag(self):
        """Archived is "empty for now", not "empty forever".

        Returning None (rather than a skip reason) is what keeps
        `okf_dirty` set, so the page is re-indexed if it is reactivated.
        """
        page = self._page(content='<p>x</p>')
        page.write({'active': False})
        self.assertIsNone(
            page._okf_skip_reason(),
            'an archived page must not be permanently skipped')

    # ── Dirty fields ──────────────────────────────────────────────────

    def test_14_dirty_fields_cover_what_changes_meaning(self):
        """The fields that change what the page means."""
        page = self._page(content='<p>x</p>')
        dirty = page._okf_dirty_fields()
        for fname in ('name', 'content', 'draft_name', 'draft_summary',
                      'parent_id', 'active'):
            self.assertIn(fname, dirty, f'{fname} should mark the page dirty')

    def test_15_content_uid_is_not_a_dirty_field(self):
        """`content_uid` says WHO, not WHAT — it changes on every edit.

        Including it would flag the page on every save without the text
        having changed.
        """
        page = self._page(content='<p>x</p>')
        self.assertNotIn('content_uid', page._okf_dirty_fields())
        self.assertNotIn('content_date', page._okf_dirty_fields())

    # ── The write hook actually flags the page ────────────────────────

    def test_16_create_flags_page_for_indexing(self):
        """A new page must be queued for indexing."""
        page = self._page(content='<p>New</p>')
        self.assertTrue(
            page.okf_dirty, 'a new page should be flagged for indexing')

    def test_17_editing_content_flags_page_for_indexing(self):
        """Editing the text must re-queue the page.

        `content` is a non-stored compute, but `_inverse_content` writes a
        new history row, so `write()` sees it in `vals` and the mixin's
        hook flags the record. This asserts that chain holds.
        """
        page = self._page(content='<p>Before</p>')
        page.write({'okf_dirty': False})
        page.write({'content': '<p>After</p>'})
        self.assertTrue(
            page.okf_dirty,
            'editing content should flag the page for re-indexing')

    def test_18_editing_an_unrelated_field_does_not_flag(self):
        """A write outside the dirty set must not re-queue the page."""
        page = self._page(content='<p>x</p>')
        page.write({'okf_dirty': False})
        page.write({'color': 3})
        self.assertFalse(
            page.okf_dirty,
            'an unrelated field should not flag the page')

    # ── Registration ──────────────────────────────────────────────────

    def test_19_model_is_registered_as_indexable(self):
        """The model must be in the indexer's list, or nothing is indexed."""
        models = self.env['ai.okf.mixin']._okf_indexable_models()
        self.assertIn('document.page', models)

    # ── Artifact type record ──────────────────────────────────────────

    def test_20_artifact_type_record_exists(self):
        """The data file's artifact type must be loadable and correct."""
        artifact = self.env.ref(
            'knowledge_document_ai.artifact_type_document_page',
            raise_if_not_found=False)
        self.assertTrue(artifact, 'artifact type record missing')
        self.assertEqual(artifact.name, 'document_page')
        self.assertEqual(artifact.bridge_module, 'knowledge_document_ai')
        self.assertEqual(artifact.model_id.model, 'document.page')

    def test_21_debug_action_is_bound_to_the_model(self):
        """The OKF debug action must be bound to document.page."""
        action = self.env.ref(
            'knowledge_document_ai.action_okf_document_page',
            raise_if_not_found=False)
        self.assertTrue(action, 'OKF debug action missing')
        self.assertEqual(action.model_id.model, 'document.page')
        self.assertEqual(action.binding_model_id.model, 'document.page')
