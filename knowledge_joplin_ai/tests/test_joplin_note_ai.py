from odoo.tests import common, tagged
import json

from odoo.addons.knowledge_joplin_ai.models.joplin_note import AGENT_XMLID


@tagged('-at_install', 'post_install')
class TestJoplinNoteAiCapability(common.TransactionCase):
    """The joplin-note-ai-capability: skill, three tools, agent link."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tool = cls.env['ai.tool']
        cls.Note = cls.env['joplin.note']
        cls.Folder = cls.env['joplin.folder']
        cls.Tag = cls.env['joplin.tag']
        cls.Agent = cls.env.ref('ai_agent_core.agent_odoo_business')

    def _tool(self, name):
        return self.Tool.search([('name', '=', name)], limit=1)

    # ── 7.1 skill and tools exist and are attached ─────────────────────

    def test_01_skill_exists_and_attached(self):
        skill = self.env.ref('knowledge_joplin_ai.skill_joplin_note')
        self.assertTrue(skill.active)
        self.assertEqual(skill.category, 'general')
        self.assertEqual(skill.compatibility, 'odoo')
        self.assertIn('joplin', skill.trigger_keywords.lower())
        self.assertTrue(skill.recipe_text)
        self.assertIn(skill, self.Agent.skill_ids)

    def test_02_tools_exist_and_are_attached(self):
        names = ['note_create', 'note_create_from_record',
                 'note_create_from_conversation']
        for name in names:
            tool = self._tool(name)
            self.assertTrue(tool, f'tool {name} missing')
            self.assertEqual(tool.risk_level, 'write')
            self.assertIn(tool, self.Agent.tool_ids)

    # ── 7.2 pre-existing contributions survive ─────────────────────────

    def test_03_agent_pre_existing_survive(self):
        odoo_core = self.env.ref('ai_agent_core.skill_odoo_core')
        self.assertIn(odoo_core, self.Agent.skill_ids)
        for name in ('describe_model', 'odoo_search', 'odoo_create',
                     'odoo_call_method', 'odoo_write', 'odoo_unlink',
                     'okf_search'):
            tool = self.env.ref(f'ai_agent_core.tool_{name}')
            self.assertIn(tool, self.Agent.tool_ids)

    # ── 7.3 notes carry identifier, revision, creation event ───────────

    def test_04_note_create_well_formed(self):
        tool = self._tool('note_create')
        result = json.loads(tool._execute_tool(
            {'title': 'Well formed', 'body': '# Body'}))
        note = self.Note.browse(result['id'])
        self.assertTrue(note.joplin_id)
        self.assertEqual(
            self.env['joplin.event'].search_count([
                ('item_id', '=', note.joplin_id), ('event_type', '=', 1)]),
            1)
        # NOTE: the note model's create() logs the event but does NOT
        # create an initial revision (only write() does). The spec's
        # "initial revision" scenario is therefore not satisfied by
        # create() alone — see the change report.

    def test_05_note_create_from_record_well_formed(self):
        task = self.env['project.task'].create({'name': 'Record source'})
        tool = self._tool('note_create_from_record')
        result = json.loads(tool._execute_tool(
            {'model': 'project.task', 'res_id': task.id}))
        note = self.Note.browse(result['id'])
        self.assertTrue(note.joplin_id)
        self.assertIn('Record source', note.title)
        self.assertEqual(
            self.env['joplin.event'].search_count([
                ('item_id', '=', note.joplin_id), ('event_type', '=', 1)]),
            1)

    def test_06_note_create_from_conversation_well_formed(self):
        tool = self._tool('note_create_from_conversation')
        result = json.loads(tool._execute_tool(
            {'title': 'Conversation', 'body': '# Summary'}))
        note = self.Note.browse(result['id'])
        self.assertTrue(note.joplin_id)
        self.assertEqual(
            self.env['joplin.event'].search_count([
                ('item_id', '=', note.joplin_id), ('event_type', '=', 1)]),
            1)

    # ── 7.4 record tool denies a model outside scope ───────────────────

    def test_07_record_tool_scope_denied(self):
        tool = self._tool('note_create_from_record').with_env(
            self.env(context=dict(self.env.context,
                                  _ai_scoped_models={'crm.lead'})))
        out = tool._execute_tool({'model': 'res.partner', 'res_id': 1})
        self.assertIn('error', out)
        self.assertIn('scope', out.lower())
        self.assertEqual(
            self.Note.search_count([('title', 'like', 'res.partner')]), 0)

    def test_08_record_tool_missing_record(self):
        tool = self._tool('note_create_from_record')
        out = tool._execute_tool({'model': 'project.task', 'res_id': 999999})
        self.assertIn('error', out)
        self.assertIn('not found', out)
        self.assertEqual(
            self.Note.search_count([('title', 'like', '999999')]), 0)

    def test_09_conversation_tool_empty_body(self):
        tool = self._tool('note_create_from_conversation')
        out = tool._execute_tool({'title': 'Empty', 'body': '   '})
        self.assertIn('error', out)
        self.assertIn('body', out)
        self.assertEqual(self.Note.search_count([('title', '=', 'Empty')]), 0)

    def test_10_create_tool_missing_title(self):
        tool = self._tool('note_create')
        out = tool._execute_tool({'title': '  '})
        self.assertIn('error', out)
        self.assertIn('title', out)

    # ── 4.x folder and tag resolution ──────────────────────────────────

    def test_11_folder_and_tag_created_on_miss(self):
        tool = self._tool('note_create')
        result = json.loads(tool._execute_tool({
            'title': 'FolderTag', 'folder': 'MyFolder',
            'tags': ['Tag1', 'Tag2']}))
        note = self.Note.browse(result['id'])
        self.assertEqual(note.folder_id.name, 'MyFolder')
        self.assertEqual(self.Folder.search_count([('name', '=', 'MyFolder')]), 1)
        self.assertEqual(set(note.tag_ids.mapped('name')), {'Tag1', 'Tag2'})
        self.assertEqual(self.Tag.search_count([('name', '=', 'Tag1')]), 1)
        self.assertEqual(self.Tag.search_count([('name', '=', 'Tag2')]), 1)

    def test_12_folder_lookup_is_case_insensitive(self):
        tool = self._tool('note_create')
        tool._execute_tool({'title': 'A', 'folder': 'Projekt'})
        tool._execute_tool({'title': 'B', 'folder': 'projekt'})
        self.assertEqual(self.Folder.search_count([('name', '=ilike', 'projekt')]), 1)

    # ── 7.5 module tolerates a missing agent ───────────────────────────

    def test_13_ensure_attachment_tolerates_missing_agent(self):
        """`_ensure_agent_attachment` must not raise when the agent is gone.

        A raising `ref()` would abort the install, so the method resolves
        the agent with `raise_if_not_found=False` and returns early.
        """
        orig_ref = self.env.ref

        def fake_ref(xmlid, raise_if_not_found=True):
            if xmlid == AGENT_XMLID:
                return self.env['ai.agent']
            return orig_ref(xmlid, raise_if_not_found=raise_if_not_found)

        self.env.__class__.ref = staticmethod(fake_ref)
        try:
            self.Note._ensure_agent_attachment()  # must not raise
        finally:
            self.env.__class__.ref = staticmethod(orig_ref)

    # ── 5.4 the <function> runs on upgrade too ─────────────────────────

    def test_14_attach_function_is_outside_noupdate(self):
        """The regression guard: the <function> must run on upgrade.

        A `<function>` inside `noupdate="1"` runs on install only. Parse
        the data file and walk the function's parent chain — if any
        ancestor carries `noupdate="1"`, the attachment would not survive
        an upgrade.
        """
        import os
        import xml.etree.ElementTree as ET

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'joplin_agent_attach.xml')
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

    def test_15_ensure_attachment_is_idempotent(self):
        """Calling the method twice must not duplicate link rows.

        It runs on every upgrade, so repeated runs must add nothing.
        """
        skill = self.env.ref('knowledge_joplin_ai.skill_joplin_note')
        tool_ids = {
            self._tool(name).id for name in (
                'note_create', 'note_create_from_record',
                'note_create_from_conversation')}

        self.Note._ensure_agent_attachment()
        skills_after_first = self.Agent.skill_ids.ids.count(skill.id)
        tools_after_first = len(
            set(self.Agent.tool_ids.ids) & tool_ids)

        self.Note._ensure_agent_attachment()
        self.assertEqual(
            self.Agent.skill_ids.ids.count(skill.id), skills_after_first)
        self.assertEqual(
            len(set(self.Agent.tool_ids.ids) & tool_ids), tools_after_first)
        self.assertEqual(skills_after_first, 1)
        self.assertEqual(tools_after_first, len(tool_ids))
