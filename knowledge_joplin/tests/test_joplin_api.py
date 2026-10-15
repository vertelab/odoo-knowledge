import json
import secrets
from datetime import datetime, timezone, timedelta

from lxml import etree

from odoo.tests import common, tagged
from odoo.exceptions import AccessError, ValidationError
from odoo import fields
from odoo.tools.safe_eval import safe_eval


@tagged('-at_install', 'post_install')
class TestJoplinModels(common.TransactionCase):
    """Test core model operations: create, read, update, delete."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.User1 = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
        except ValueError:
            cls.User1 = cls.env['res.users'].create({
                'name': 'Test User 1',
                'login': 'test_joplin1@test.com',
                'groups_id': [
                    (4, cls.env.ref('base.group_user').id),
                    (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
                ],
            })
        try:
            cls.User2 = cls.env.ref('knowledge_joplin.demo_user_joplin_2')
        except ValueError:
            cls.User2 = cls.env['res.users'].create({
                'name': 'Test User 2',
                'login': 'test_joplin2@test.com',
                'groups_id': [
                    (4, cls.env.ref('base.group_user').id),
                    (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
                ],
            })

        cls.Folder = cls.env['joplin.folder']
        cls.Note = cls.env['joplin.note']
        cls.Tag = cls.env['joplin.tag']
        cls.Resource = cls.env['joplin.resource']
        cls.Revision = cls.env['joplin.revision']
        cls.Event = cls.env['joplin.event']

    def _create_folder(self, name='Test Folder', user=None):
        return self.Folder.with_user(user or self.User1).create({
            'name': name,
            'joplin_id': secrets.token_hex(16),
            'user_id': (user or self.User1).id,
        })

    def _create_note(self, title='Test Note', body='Test body', folder=None, user=None, **kwargs):
        vals = {
            'title': title,
            'body': body,
            'joplin_id': secrets.token_hex(16),
            'user_id': (user or self.User1).id,
        }
        if folder:
            vals['folder_id'] = folder.id
        vals.update(kwargs)
        return self.Note.with_user(user or self.User1).create(vals)

    def _create_tag(self, name='Test Tag', user=None):
        return self.Tag.with_user(user or self.User1).create({
            'name': name,
            'joplin_id': secrets.token_hex(16),
            'user_id': (user or self.User1).id,
        })

    # ---- FOLDER TESTS ----

    def test_create_folder(self):
        folder = self._create_folder('My Notebook')
        self.assertTrue(folder.joplin_id)
        self.assertEqual(len(folder.joplin_id), 32)
        self.assertEqual(folder.name, 'My Notebook')
        self.assertEqual(folder.user_id, self.User1)
        self.assertTrue(folder.created_time)
        self.assertTrue(folder.updated_time)

    def test_folder_tree(self):
        parent = self._create_folder('Parent')
        child = self._create_folder('Child')
        child.parent_id = parent.id
        self.assertEqual(child.parent_id, parent)
        self.assertIn(child, parent.child_ids)

    def test_folder_note_count(self):
        folder = self._create_folder('Count Test')
        self.assertEqual(folder.note_count, 0)
        note = self._create_note(folder=folder)
        self.assertEqual(folder.note_count, 1)

    def test_folder_event_on_create(self):
        folder = self._create_folder()
        events = self.Event.search([('item_id', '=', folder.joplin_id)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events.event_type, 1)

    def test_folder_event_on_delete(self):
        folder = self._create_folder()
        jid = folder.joplin_id
        folder.sudo().unlink()
        events = self.Event.search([('item_id', '=', jid)])
        delete_events = events.filtered(lambda e: e.event_type == 3)
        self.assertTrue(len(delete_events) >= 1)

    # ---- NOTE TESTS ----

    def test_create_note(self):
        folder = self._create_folder()
        note = self._create_note('Hello World', 'This is **markdown**', folder)
        self.assertEqual(note.title, 'Hello World')
        self.assertEqual(note.body, 'This is **markdown**')
        self.assertEqual(note.folder_id, folder)
        self.assertEqual(note.user_id, self.User1)
        self.assertTrue(note.joplin_id)
        self.assertEqual(len(note.joplin_id), 32)
        self.assertTrue(note.created_time)
        self.assertTrue(note.updated_time)

    def test_note_markdown_to_html(self):
        note = self._create_note(
            'Markdown Test',
            '# Title\n\nThis is **bold** and `code`.\n\n- Item 1\n- Item 2\n\n| Col1 | Col2 |\n|------|------|\n| A    | B    |',
        )
        html = note.body_html
        self.assertTrue(html)
        self.assertIn('<h1 ', html)
        self.assertIn('<strong>', html)
        self.assertIn('<code>', html)
        self.assertIn('<li>', html)
        self.assertIn('<table>', html)

    def test_note_markdown_empty_body(self):
        note = self._create_note('Empty body', '')
        self.assertEqual(note.body_html, '')

    def test_note_event_on_create(self):
        note = self._create_note()
        events = self.Event.search([('item_id', '=', note.joplin_id), ('event_type', '=', 1)])
        self.assertEqual(len(events), 1)

    def test_note_event_on_update(self):
        note = self._create_note('Original')
        note.sudo().write({'title': 'Updated'})
        events = self.Event.search([('item_id', '=', note.joplin_id), ('event_type', '=', 2)])
        self.assertEqual(len(events), 1)

    def test_note_event_on_delete(self):
        note = self._create_note()
        jid = note.joplin_id
        note.sudo().unlink()
        events = self.Event.search([('item_id', '=', jid), ('event_type', '=', 3)])
        self.assertTrue(len(events) >= 1)

    # ---- TRASH & RESTORE ----

    def test_note_trash_and_restore(self):
        note = self._create_note('To Trash')
        self.assertTrue(note.active)

        note.action_trash()
        self.assertFalse(note.active)
        self.assertTrue(note.deleted_time)

        note.action_restore()
        self.assertTrue(note.active)
        self.assertFalse(note.deleted_time)

    # ---- TAG TESTS ----

    def test_create_tag(self):
        tag = self._create_tag('urgent')
        self.assertTrue(tag.joplin_id)
        self.assertEqual(tag.name, 'urgent')
        self.assertEqual(tag.user_id, self.User1)

    def test_assign_tag_to_note(self):
        tag = self._create_tag('bug')
        note = self._create_note('Bug Report')
        note.sudo().write({'tag_ids': [(4, tag.id)]})
        self.assertIn(tag, note.tag_ids)
        self.assertIn(note, tag.note_ids)

    def test_remove_tag_from_note(self):
        tag = self._create_tag('feature')
        note = self._create_note('Feature Request')
        note.sudo().write({'tag_ids': [(4, tag.id)]})
        note.sudo().write({'tag_ids': [(3, tag.id)]})
        self.assertNotIn(tag, note.tag_ids)

    def test_tag_note_count(self):
        tag = self._create_tag('count-test')
        note1 = self._create_note('Note 1')
        note2 = self._create_note('Note 2')
        note1.sudo().write({'tag_ids': [(4, tag.id)]})
        note2.sudo().write({'tag_ids': [(4, tag.id)]})
        self.assertEqual(tag.note_count, 2)

    # ---- RESOURCE TESTS ----

    def test_create_resource(self):
        import base64
        note = self._create_note('Resource Note')
        res = self.Resource.with_user(self.User1).create({
            'joplin_id': secrets.token_hex(16),
            'name': 'test.txt',
            'mime': 'text/plain',
            'filename': 'test.txt',
            'datas': base64.b64encode(b'Hello World').decode('utf-8'),
            'note_id': note.id,
            'user_id': self.User1.id,
        })
        self.assertTrue(res.joplin_id)
        self.assertEqual(res.file_size, 11)
        self.assertEqual(res.file_extension, 'txt')

    def test_resource_belongs_to_note(self):
        import base64
        note = self._create_note('Note With File')
        res = self.Resource.with_user(self.User1).create({
            'joplin_id': secrets.token_hex(16),
            'name': 'data.bin',
            'mime': 'application/octet-stream',
            'datas': base64.b64encode(b'\x00\x01\x02').decode('utf-8'),
            'note_id': note.id,
            'user_id': self.User1.id,
        })
        self.assertIn(res, note.resource_ids)
        self.assertEqual(res.note_id, note)

    # ---- REVISION TESTS ----

    def test_revision_created_on_write(self):
        note = self._create_note('Original Title', 'Original body')
        initial_count = len(note.revision_ids)
        note.sudo().write({'title': 'Updated Title', 'body': 'Updated body'})
        self.assertEqual(len(note.revision_ids), initial_count + 1)
        rev = note.revision_ids[-1]
        self.assertTrue(rev.title_diff or rev.body_diff)

    def test_revision_fields(self):
        note = self._create_note('Rev Test', 'Body v1')
        note.sudo().write({'title': 'Rev Test Updated', 'body': 'Body v2'})
        rev = note.revision_ids[-1]
        self.assertEqual(rev.note_id, note)
        self.assertEqual(rev.item_id, note.joplin_id)
        self.assertEqual(rev.item_type, 1)

    def test_initial_revision_created_on_create(self):
        note = self._create_note('Initial Title', 'Initial body')
        self.assertEqual(len(note.revision_ids), 1)
        rev = note.revision_ids[0]
        self.assertEqual(rev.note_id, note)

    def test_initial_revision_records_created_content(self):
        note = self._create_note('Initial Title', 'Initial body')
        rev = note.revision_ids[0]
        self.assertTrue(rev.title_diff)
        self.assertTrue(rev.body_diff)
        # The initial revision records the content as an addition: the patch
        # inserts the created text into an empty original.
        self.assertIn('Initial Title', rev.title_diff)
        self.assertIn('Initial body', rev.body_diff)

    def test_initial_revision_shape_matches_write_revision(self):
        note = self._create_note('Shape Title', 'Shape body')
        initial = note.revision_ids[0]
        note.sudo().write({'title': 'Shape Title 2', 'body': 'Shape body 2'})
        edit_rev = note.revision_ids.filtered(lambda r: r != initial)[0]
        for rev in (initial, edit_rev):
            self.assertEqual(rev.note_id, note)
            self.assertEqual(rev.item_id, note.joplin_id)
            self.assertEqual(rev.item_type, 1)
            self.assertTrue(rev.joplin_id)
            self.assertTrue(rev.item_updated_time)

    def test_initial_revision_title_only(self):
        note = self._create_note('Title Only', '')
        self.assertEqual(len(note.revision_ids), 1)
        rev = note.revision_ids[0]
        self.assertTrue(rev.title_diff)
        self.assertIn('Title Only', rev.title_diff)

    def test_initial_revision_joplin_id_uniqueness(self):
        notes = self.Note.browse([
            self._create_note('Unique %d' % i, 'Body %d' % i).id
            for i in range(5)
        ])
        for note in notes:
            self.assertEqual(len(note.revision_ids), 1)
        revision_ids = notes.mapped('revision_ids.joplin_id')
        self.assertEqual(len(revision_ids), len(set(revision_ids)))

    def test_edit_after_create_yields_two_revisions(self):
        note = self._create_note('Original Title', 'Original body')
        initial = note.revision_ids[0]
        initial_diffs = (initial.title_diff, initial.body_diff)
        note.sudo().write({'title': 'Edited Title', 'body': 'Edited body'})
        self.assertEqual(len(note.revision_ids), 2)
        # The initial revision is preserved, not altered or duplicated.
        self.assertEqual(note.revision_ids[0].title_diff, initial_diffs[0])
        self.assertEqual(note.revision_ids[0].body_diff, initial_diffs[1])

    def test_write_without_tracked_fields_adds_no_revision(self):
        note = self._create_note('No Track', 'Body')
        initial_count = len(note.revision_ids)
        note.sudo().write({'author': 'Someone'})
        self.assertEqual(len(note.revision_ids), initial_count)

    # ---- UNIQUENESS TESTS ----

    def test_joplin_id_uniqueness(self):
        jid = secrets.token_hex(16)
        self._create_note('First', joplin_id=jid)
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self._create_note('Second', joplin_id=jid)

    def test_note_tag_relation_uniqueness(self):
        tag = self._create_tag('unique')
        note = self._create_note('Unique relation')
        self.env['joplin.note.tag'].create({
            'note_id': note.id,
            'tag_id': tag.id,
        })
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self.env['joplin.note.tag'].create({
                    'note_id': note.id,
                    'tag_id': tag.id,
                })

    # ---- TODO TESTS ----

    def test_note_todo(self):
        due = datetime.utcnow() + timedelta(days=7)
        note = self._create_note('Todo Note', is_todo=True, todo_due=due)
        self.assertTrue(note.is_todo)
        self.assertEqual(note.todo_due, due)
        self.assertFalse(note.todo_completed)

        completed = datetime.utcnow()
        note.sudo().write({'todo_completed': completed})
        self.assertEqual(note.todo_completed, completed)

    # ---- MARKUP LANGUAGE ----

    def test_markup_language_html(self):
        note = self._create_note('HTML Note', '<p>Hello</p>', markup_language=0)
        self.assertIn('<p>Hello</p>', note.body_html)


@tagged('-at_install', 'post_install')
class TestJoplinSecurity(common.TransactionCase):
    """Test record rules and access control."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.User1 = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
        except ValueError:
            cls.User1 = cls.env['res.users'].create({
                'name': 'Secure User 1',
                'login': 'secure_joplin1@test.com',
                'groups_id': [
                    (4, cls.env.ref('base.group_user').id),
                    (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
                ],
            })
        try:
            cls.User2 = cls.env.ref('knowledge_joplin.demo_user_joplin_2')
        except ValueError:
            cls.User2 = cls.env['res.users'].create({
                'name': 'Secure User 2',
                'login': 'secure_joplin2@test.com',
                'groups_id': [
                    (4, cls.env.ref('base.group_user').id),
                    (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
                ],
            })
        cls.Note = cls.env['joplin.note']

    def _create_note_for(self, user, title='Secret Note'):
        return self.Note.with_user(user).create({
            'title': title,
            'body': 'Secret content',
            'joplin_id': secrets.token_hex(16),
            'user_id': user.id,
        })

    def test_user_can_read_own_note(self):
        note = self._create_note_for(self.User1)
        notes = self.Note.with_user(self.User1).search([('id', '=', note.id)])
        self.assertTrue(notes)

    def test_user_cannot_read_others_note(self):
        note = self._create_note_for(self.User1)
        notes = self.Note.with_user(self.User2).search([('id', '=', note.id)])
        self.assertFalse(notes)

    def test_follower_can_read_note(self):
        note = self._create_note_for(self.User1)
        note.with_user(self.User1).message_subscribe(partner_ids=[self.User2.partner_id.id])
        notes = self.Note.with_user(self.User2).search([('id', '=', note.id)])
        self.assertTrue(notes)

    def test_user_can_update_own_note(self):
        note = self._create_note_for(self.User1)
        note.with_user(self.User1).write({'title': 'Updated'})
        self.assertEqual(note.with_user(self.User1).title, 'Updated')

    def test_user_cannot_update_others_note(self):
        note = self._create_note_for(self.User1)
        with self.assertRaises(AccessError):
            note.with_user(self.User2).write({'title': 'Hacked'})

    def test_user_can_create_note(self):
        note = self.Note.with_user(self.User1).create({
            'title': 'New Note',
            'body': 'Body',
            'joplin_id': secrets.token_hex(16),
            'user_id': self.User1.id,
        })
        self.assertTrue(note)
        self.assertEqual(note.user_id, self.User1)


@tagged('-at_install', 'post_install')
class TestJoplinNoteAccessFilters(common.TransactionCase):
    """Test the note list filters and the action ceiling.

    The record rules are covered by TestJoplinSecurity. These tests cover the
    filter and action domains in views/joplin_note_views.xml, which the record
    rules do not: a filter domain can contradict the rule without the rule's
    tests noticing.

    The domains are read from the search view arch and the action record, then
    evaluated against a fixture of owned / followed / unrelated notes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Follow TestJoplinSecurity's fixture style: prefer the demo users but
        # fall back to created users when demo data is not loaded.
        try:
            cls.User1 = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
        except ValueError:
            cls.User1 = cls._make_user('Filter Test User 1', 'filter_joplin1@test.com')
        try:
            cls.User2 = cls.env.ref('knowledge_joplin.demo_user_joplin_2')
        except ValueError:
            cls.User2 = cls._make_user('Filter Test User 2', 'filter_joplin2@test.com')
        cls.User3 = cls._make_user('Filter Test User 3', 'filter_joplin3@test.com')
        cls.Note = cls.env['joplin.note']

        # Fixture: one note of each relationship to User1.
        cls.own_note = cls._make_note(cls.User1, 'Owned by User1')
        # Owned by User2, followed by User1: the "shared with me" case.
        cls.followed_note = cls._make_note(cls.User2, 'Owned by User2, followed by User1')
        cls.followed_note.message_subscribe(partner_ids=[cls.User1.partner_id.id])
        # Owned by User2, followed by User3 only: not User1's business.
        cls.other_followed_note = cls._make_note(cls.User2, 'Owned by User2, followed by User3')
        cls.other_followed_note.message_subscribe(partner_ids=[cls.User3.partner_id.id])
        # Owned by User2, followed by nobody: fully unrelated to User1.
        cls.unrelated_note = cls._make_note(cls.User2, 'Owned by User2, no followers')

    @classmethod
    def _make_user(cls, name, login):
        return cls.env['res.users'].create({
            'name': name,
            'login': login,
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
            ],
        })

    @classmethod
    def _make_note(cls, user, title):
        return cls.Note.with_user(user).create({
            'title': title,
            'body': title,
            'joplin_id': secrets.token_hex(16),
            'user_id': user.id,
        })

    def _filter_domain(self, name):
        """Return the raw domain string of a search filter, from the arch."""
        view = self.env.ref('knowledge_joplin.view_joplin_note_search')
        arch = etree.fromstring(view.arch.encode())
        nodes = arch.xpath('//filter[@name=$name]', name=name)
        self.assertEqual(len(nodes), 1, f'filter {name!r} not found in search view')
        return nodes[0].get('domain')

    def _action_domain(self):
        """Return the raw domain string of the notes action."""
        action = self.env.ref('knowledge_joplin.action_joplin_note')
        return action.domain

    def _rule_domain(self, xmlid):
        """Return the raw domain string of a record rule."""
        rule = self.env.ref(xmlid)
        return rule.domain_force

    def _resolve(self, domain_str, user):
        """Evaluate a domain string with the web client's context.

        Search filters and action domains are evaluated with ``uid`` and
        ``user`` in scope; ``user.partner_id.id`` is the follower partner.
        """
        return safe_eval(domain_str, {'uid': user.id, 'user': user})

    def _admitted(self, domain_str, user):
        """Return the fixture notes a domain admits for ``user``."""
        domain = self._resolve(domain_str, user)
        return self.Note.with_user(user).search(domain)

    # ---- My Notes ----

    def test_my_notes_domain_is_owned_only(self):
        domain = self._resolve(self._filter_domain('my_notes'), self.User1)
        self.assertEqual(domain, [('user_id', '=', self.User1.id)])

    def test_my_notes_admits_own_and_excludes_followed(self):
        admitted = self._admitted(self._filter_domain('my_notes'), self.User1)
        self.assertIn(self.own_note, admitted)
        self.assertNotIn(self.followed_note, admitted)

    def test_my_notes_widened_to_union_would_include_followed(self):
        # Guards test_my_notes_admits_own_and_excludes_followed: if the filter
        # were widened to the union (the action ceiling), the followed note
        # would be admitted and the exclusion above would fail.
        union = self._action_domain()
        admitted = self._admitted(union, self.User1)
        self.assertIn(self.followed_note, admitted)

    # ---- Shared with Me ----

    def test_shared_with_me_domain_requires_current_follower(self):
        # The follower clause must identify the current user, not merely
        # "has any follower". Odoo 18's view validator rejects
        # ``user.partner_id.id`` in a search-filter domain (``user`` is not an
        # ignored expression name there), so the follower clause traverses the
        # follower partner's users and compares with ``uid`` — the same idiom
        # Odoo core uses for "My Meetings"
        # (calendar: ``[('partner_ids.user_ids', 'in', [uid])]``).
        domain = self._resolve(self._filter_domain('shared_with_me'), self.User1)
        self.assertEqual(domain, [
            ('message_follower_ids.partner_id.user_ids', 'in', [self.User1.id]),
            ('user_id', '!=', self.User1.id),
        ])

    def test_shared_with_me_admits_followed_not_owned(self):
        admitted = self._admitted(self._filter_domain('shared_with_me'), self.User1)
        self.assertIn(self.followed_note, admitted)
        self.assertNotIn(self.own_note, admitted)

    def test_shared_with_me_excludes_note_followed_by_someone_else(self):
        # The old broken domain ('message_follower_ids.partner_id', '!=', False)
        # admitted this note because it has a follower, just not the current
        # user. The corrected domain must not.
        admitted = self._admitted(self._filter_domain('shared_with_me'), self.User1)
        self.assertNotIn(self.other_followed_note, admitted)

    def test_shared_with_me_excludes_unrelated_note(self):
        admitted = self._admitted(self._filter_domain('shared_with_me'), self.User1)
        self.assertNotIn(self.unrelated_note, admitted)

    def test_filters_do_not_overlap(self):
        my_notes = self._admitted(self._filter_domain('my_notes'), self.User1)
        shared = self._admitted(self._filter_domain('shared_with_me'), self.User1)
        self.assertFalse(set(my_notes.ids) & set(shared.ids))

    # ---- Action ceiling ----

    def test_action_domain_is_owned_or_followed(self):
        domain = self._resolve(self._action_domain(), self.User1)
        self.assertEqual(domain, [
            '|',
            ('user_id', '=', self.User1.id),
            ('message_follower_ids.partner_id', '=', self.User1.partner_id.id),
        ])

    def test_action_admits_owned_and_followed_and_excludes_unrelated(self):
        admitted = self._admitted(self._action_domain(), self.User1)
        self.assertIn(self.own_note, admitted)
        self.assertIn(self.followed_note, admitted)
        self.assertNotIn(self.unrelated_note, admitted)
        self.assertNotIn(self.other_followed_note, admitted)

    def test_action_ceiling_matches_record_rule(self):
        # The ceiling duplicates the record rule's domain (design D5). If the
        # rule changes and the ceiling does not (or vice versa), this fails.
        ceiling = self._resolve(self._action_domain(), self.User1)
        rule = self._resolve(self._rule_domain('knowledge_joplin.rule_joplin_note_own'), self.User1)
        self.assertEqual(ceiling, rule)
        self.assertEqual(
            set(self._admitted(self._action_domain(), self.User1).ids),
            set(self._admitted(self._rule_domain('knowledge_joplin.rule_joplin_note_own'), self.User1).ids),
        )

    # ---- Kanban ----

    def test_kanban_card_fields_are_declared(self):
        # Every field the card template reads must be declared on the kanban
        # (the <field> elements before <templates>), or the card has no data.
        view = self.env.ref('knowledge_joplin.view_joplin_note_kanban')
        arch = etree.fromstring(view.arch.encode())
        card = arch.xpath('//t[@t-name="card"]')
        self.assertEqual(len(card), 1, 'kanban card template not found')
        declared = {
            node.get('name')
            for node in arch.xpath('//kanban/field')
        }
        used = {
            node.get('name')
            for node in card[0].xpath('.//field')
        }
        missing = used - declared
        self.assertFalse(missing, f'card uses undeclared fields: {sorted(missing)}')

    def test_kanban_renders_for_followed_note(self):
        # A follower must be able to read every field the card depends on for a
        # note they do not own. ``read`` raises AccessError if the template
        # referenced a field the follower cannot read.
        view = self.env.ref('knowledge_joplin.view_joplin_note_kanban')
        arch = etree.fromstring(view.arch.encode())
        card = arch.xpath('//t[@t-name="card"]')[0]
        field_names = sorted({node.get('name') for node in card.xpath('.//field')})
        self.assertTrue(field_names)
        data = self.followed_note.with_user(self.User1).read(field_names)[0]
        self.assertEqual(data['id'], self.followed_note.id)
        self.assertEqual(data['title'], self.followed_note.title)
        self.assertEqual(data['user_id'][0], self.User2.id)


@tagged('-at_install', 'post_install')
class TestJoplinNoteSearchPanel(common.TransactionCase):
    """Test the notes search panel in views/joplin_note_views.xml.

    There is no browser in this environment, so rendering cannot be asserted
    (design D6). These tests read the search view arch and assert the panel's
    presence, its three sections and each section's attributes; the
    behavioural tests then assert that selecting a section narrows the result
    set within the action ceiling.
    """

    # The section fields, in the order design D1 fixes them.
    PANEL_FIELDS = ['folder_id', 'tag_ids', 'user_id']

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Follow TestJoplinNoteAccessFilters' fixture style: prefer the demo
        # users but fall back to created users when demo data is not loaded.
        try:
            cls.User1 = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
        except ValueError:
            cls.User1 = cls._make_user('Panel Test User 1', 'panel_joplin1@test.com')
        try:
            cls.User2 = cls.env.ref('knowledge_joplin.demo_user_joplin_2')
        except ValueError:
            cls.User2 = cls._make_user('Panel Test User 2', 'panel_joplin2@test.com')
        cls.User3 = cls._make_user('Panel Test User 3', 'panel_joplin3@test.com')
        cls.Note = cls.env['joplin.note']

        # Fixture: two notebooks and two tags, owned by User1.
        cls.folder_a = cls._make_folder(cls.User1, 'Panel Notebook A')
        cls.folder_b = cls._make_folder(cls.User1, 'Panel Notebook B')
        cls.tag_x = cls._make_tag(cls.User1, 'panel-tag-x')
        cls.tag_y = cls._make_tag(cls.User1, 'panel-tag-y')

        # note_a1: folder A, tag X. note_a2: folder A, tag Y.
        # note_b1: folder B, tag X.
        cls.note_a1 = cls._make_note(cls.User1, 'Panel A1', cls.folder_a, [cls.tag_x])
        cls.note_a2 = cls._make_note(cls.User1, 'Panel A2', cls.folder_a, [cls.tag_y])
        cls.note_b1 = cls._make_note(cls.User1, 'Panel B1', cls.folder_b, [cls.tag_x])

        # A note owned by User2 in folder A that User1 neither owns nor
        # follows: the panel must never surface it to User1 (task 4.7).
        cls.foreign_note = cls._make_note(cls.User2, 'Panel Foreign', cls.folder_a, [])

    @classmethod
    def _make_user(cls, name, login):
        return cls.env['res.users'].create({
            'name': name,
            'login': login,
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
            ],
        })

    @classmethod
    def _make_folder(cls, user, name):
        return cls.env['joplin.folder'].with_user(user).create({
            'name': name,
            'joplin_id': secrets.token_hex(16),
            'user_id': user.id,
        })

    @classmethod
    def _make_tag(cls, user, name):
        return cls.env['joplin.tag'].with_user(user).create({
            'name': name,
            'joplin_id': secrets.token_hex(16),
            'user_id': user.id,
        })

    @classmethod
    def _make_note(cls, user, title, folder, tags):
        vals = {
            'title': title,
            'body': title,
            'joplin_id': secrets.token_hex(16),
            'user_id': user.id,
            'folder_id': folder.id,
        }
        if tags:
            vals['tag_ids'] = [(6, 0, [tag.id for tag in tags])]
        return cls.Note.with_user(user).create(vals)

    # ---- Arch helpers ----

    def _searchpanel_states(self):
        """Return the searchpanel's ``field`` nodes, keyed by field name.

        Raises if the panel or a section is missing, so a removed section
        fails every arch test rather than only the count assertion.
        """
        view = self.env.ref('knowledge_joplin.view_joplin_note_search')
        arch = etree.fromstring(view.arch.encode())
        panels = arch.xpath('//searchpanel')
        self.assertEqual(len(panels), 1, 'search view has no <searchpanel>')
        states = {}
        for node in panels[0].xpath('./field'):
            states[node.get('name')] = node
        return states

    def _panel_field(self, name):
        states = self._searchpanel_states()
        self.assertIn(name, states, f'search panel section {name!r} is missing')
        return states[name]

    # ---- Behavioural helpers ----

    def _action_domain(self):
        """Return the resolved domain of the notes action (the ceiling)."""
        action = self.env.ref('knowledge_joplin.action_joplin_note')
        return safe_eval(action.domain, {'uid': self.User1.id, 'user': self.User1})

    def _filter_domain(self, name, user):
        """Return the resolved domain of a search filter from the arch."""
        view = self.env.ref('knowledge_joplin.view_joplin_note_search')
        arch = etree.fromstring(view.arch.encode())
        nodes = arch.xpath('//filter[@name=$name]', name=name)
        self.assertEqual(len(nodes), 1, f'filter {name!r} not found in search view')
        return safe_eval(nodes[0].get('domain'), {'uid': user.id, 'user': user})

    def _panel_domain(self, field, value):
        """Return the domain the panel adds when selecting ``value``.

        A many2many section (tag_ids) filters with ``in``; a many2one section
        (folder_id, user_id) filters with ``=`` — the same domains the web
        client sends for a search panel selection.
        """
        if field == 'tag_ids':
            return [('tag_ids', 'in', [value.id])]
        return [(field, '=', value.id)]

    def _panel_search(self, user, panel_domain, filter_name=None):
        """Search as ``user`` with the action ceiling, an optional default
        filter and the panel's domain combined — the list the panel produces.
        """
        action = self.env.ref('knowledge_joplin.action_joplin_note')
        ceiling = safe_eval(action.domain, {'uid': user.id, 'user': user})
        domain = ceiling + panel_domain
        if filter_name:
            domain = domain + self._filter_domain(filter_name, user)
        return self.Note.with_user(user).search(domain)

    # ---- 4.1 Panel and its three sections ----

    def test_searchpanel_has_three_sections(self):
        states = self._searchpanel_states()
        self.assertEqual(list(states), self.PANEL_FIELDS)

    def test_searchpanel_section_fields_exist_on_model(self):
        # Guards the arch against a section naming a field the model lacks:
        # the view would not load, but assert it here so the intent is explicit.
        for name in self.PANEL_FIELDS:
            self.assertIn(name, self.Note._fields)

    # ---- 4.2 Notebooks are hierarchical ----

    def test_notebooks_section_is_hierarchical(self):
        # Hierarchisation is on by default; only hierarchize="0" switches it
        # off. Assert the attribute is absent or truthy.
        node = self._panel_field('folder_id')
        self.assertNotEqual(node.get('hierarchize'), '0')

    def test_notebooks_section_is_unbounded(self):
        node = self._panel_field('folder_id')
        self.assertEqual(node.get('limit'), '0')

    # ---- 4.3 Tags are multi-select ----

    def test_tags_section_is_multi_select(self):
        node = self._panel_field('tag_ids')
        self.assertEqual(node.get('select'), 'multi')

    # ---- 4.4 Owner is bounded ----

    def test_owner_section_is_bounded(self):
        node = self._panel_field('user_id')
        self.assertNotEqual(node.get('limit'), '0')
        self.assertTrue(node.get('limit'))
        self.assertGreater(int(node.get('limit')), 0)

    # ---- 4.5 Every section has counters ----

    def test_every_section_has_counters(self):
        for name in self.PANEL_FIELDS:
            node = self._panel_field(name)
            self.assertEqual(
                node.get('enable_counters'), '1',
                f'section {name!r} does not enable counters',
            )

    # ---- 4.6 Selecting a notebook / tag filters the list ----

    def test_selecting_notebook_filters_the_list(self):
        admitted = self._panel_search(
            self.User1, self._panel_domain('folder_id', self.folder_a),
        )
        self.assertIn(self.note_a1, admitted)
        self.assertIn(self.note_a2, admitted)
        self.assertNotIn(self.note_b1, admitted)

    def test_selecting_tag_filters_the_list(self):
        admitted = self._panel_search(
            self.User1, self._panel_domain('tag_ids', self.tag_x),
        )
        self.assertIn(self.note_a1, admitted)
        self.assertIn(self.note_b1, admitted)
        self.assertNotIn(self.note_a2, admitted)

    def test_selecting_two_tags_narrows_further(self):
        # Two selections combine (AND), so the result is the intersection.
        domain = (
            self._panel_domain('tag_ids', self.tag_x)
            + self._panel_domain('tag_ids', self.tag_y)
        )
        admitted = self._panel_search(self.User1, domain)
        self.assertNotIn(self.note_a1, admitted)
        self.assertNotIn(self.note_a2, admitted)
        self.assertNotIn(self.note_b1, admitted)

    # ---- 4.7 The panel cannot surface an inaccessible note ----

    def test_panel_cannot_surface_a_note_the_user_may_not_see(self):
        # User1 selects User2 as owner. The ceiling admits only User1's own
        # notes and notes User1 follows; the foreign note is neither, so the
        # combined domain must return nothing.
        admitted = self._panel_search(
            self.User1, self._panel_domain('user_id', self.User2),
        )
        self.assertNotIn(self.foreign_note, admitted)
        self.assertFalse(admitted)

    def test_panel_ceiling_is_what_excludes_the_foreign_note(self):
        # Guards the test above. The record rule also excludes the foreign
        # note, so search as sudo to remove that layer: the action ceiling is
        # then the only thing standing between the panel and the note. If the
        # ceiling is removed from the action, the panel's combined domain no
        # longer excludes it and this fails.
        panel_domain = self._panel_domain('user_id', self.User2)
        without_ceiling = self.Note.sudo().search(panel_domain)
        self.assertIn(self.foreign_note, without_ceiling)
        with_ceiling = self.Note.sudo().search(self._action_domain() + panel_domain)
        self.assertNotIn(self.foreign_note, with_ceiling)

    # ---- 4.8 The panel combines with the default My Notes filter ----

    def test_notebook_with_my_notes_filter_returns_own_notes_only(self):
        # The action's context sets search_default_my_notes, so a notebook
        # selection is combined with ('user_id', '=', uid) — the documented
        # outcome (design D6 / Risks).
        admitted = self._panel_search(
            self.User1,
            self._panel_domain('folder_id', self.folder_a),
            filter_name='my_notes',
        )
        self.assertIn(self.note_a1, admitted)
        self.assertIn(self.note_a2, admitted)
        self.assertNotIn(self.note_b1, admitted)
        self.assertNotIn(self.foreign_note, admitted)

    def test_notebook_with_my_notes_excludes_followed_notes(self):
        # A note in folder A owned by User2 but followed by User1 is admitted
        # by the ceiling; the My Notes filter must still exclude it.
        self.foreign_note.message_subscribe(partner_ids=[self.User1.partner_id.id])
        admitted = self._panel_search(
            self.User1,
            self._panel_domain('folder_id', self.folder_a),
            filter_name='my_notes',
        )
        self.assertIn(self.note_a1, admitted)
        self.assertNotIn(self.foreign_note, admitted)

    # ---- 4.7b Owner section offers only visible owners ----

    def test_owner_section_offers_only_visible_owners(self):
        # The panel's Owner section lists users whose notes the ceiling admits.
        # For User1 that is User1 plus the owners of notes User1 follows — not
        # every user in the database (spec: Owner list respects access).
        own_notes = self.Note.with_user(self.User1).search(self._action_domain())
        visible_owners = own_notes.mapped('user_id')
        self.assertIn(self.User1, visible_owners)
        self.assertNotIn(self.User3, visible_owners)


@tagged('-at_install', 'post_install')
class TestJoplinApi(common.HttpCase):
    """Test REST API endpoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.User1 = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
        except ValueError:
            cls.User1 = cls.env['res.users'].create({
                'name': 'API User',
                'login': 'api_joplin@test.com',
                'groups_id': [
                    (4, cls.env.ref('base.group_user').id),
                    (4, cls.env.ref('knowledge_joplin.group_joplin_user_own').id),
                ],
            })
        cls.Token = cls.env['joplin.api.token'].sudo().create({
            'name': 'Test API Token',
            'user_id': cls.User1.id,
        })

    def setUp(self):
        super().setUp()
        self.folder = self.env['joplin.folder'].with_user(self.User1).create({
            'name': 'API Test Folder',
            'joplin_id': secrets.token_hex(16),
            'user_id': self.User1.id,
        })
        self.note = self.env['joplin.note'].with_user(self.User1).create({
            'title': 'API Test Note',
            'body': '# API Note\n\nContent',
            'joplin_id': secrets.token_hex(16),
            'folder_id': self.folder.id,
            'user_id': self.User1.id,
        })
        self.tag = self.env['joplin.tag'].with_user(self.User1).create({
            'name': 'api-test',
            'joplin_id': secrets.token_hex(16),
            'user_id': self.User1.id,
        })

    def _auth_url(self, path):
        sep = '&' if '?' in path else '?'
        return f'/joplin{path}{sep}token={self.Token.token}'

    def _get_json(self, path):
        resp = self.url_open(self._auth_url(path))
        return json.loads(resp.content)

    def test_ping(self):
        resp = self.url_open('/joplin/ping')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), 'JoplinClipperServer')

    def test_get_notes(self):
        data = self._get_json('/notes')
        self.assertIn('items', data)
        self.assertIn('has_more', data)

    def test_get_note(self):
        data = self._get_json(f'/notes/{self.note.joplin_id}')
        self.assertEqual(data.get('title'), 'API Test Note')
        self.assertEqual(data.get('id'), self.note.joplin_id)

    def test_get_note_tags(self):
        self.note.sudo().write({'tag_ids': [(4, self.tag.id)]})
        data = self._get_json(f'/notes/{self.note.joplin_id}/tags')
        self.assertIn('items', data)
        tag_ids = [t.get('id') for t in data['items']]
        self.assertIn(self.tag.joplin_id, tag_ids)

    def test_get_folders(self):
        data = self._get_json('/folders')
        self.assertIn('items', data)
        folder_ids = [f.get('id') for f in data['items']]
        self.assertIn(self.folder.joplin_id, folder_ids)

    def test_get_folder_notes(self):
        data = self._get_json(f'/folders/{self.folder.joplin_id}/notes')
        self.assertIn('items', data)
        note_ids = [n.get('id') for n in data['items']]
        self.assertIn(self.note.joplin_id, note_ids)

    def test_get_tags(self):
        data = self._get_json('/tags')
        self.assertIn('items', data)

    def test_search(self):
        data = self._get_json('/search?query=API+Test')
        self.assertIn('items', data)
        found = any('API Test' in n.get('title', '') for n in data['items'])
        self.assertTrue(found)

    def test_get_events(self):
        data = self._get_json('/events')
        self.assertIn('items', data)
        self.assertIn('has_more', data)
        self.assertIn('cursor', data)


@tagged('at_install', 'post_install')
class TestDemoData(common.TransactionCase):
    """Verify demo data integrity."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.demo_user = cls.env.ref('knowledge_joplin.demo_user_joplin_1')
            cls.has_demo = True
        except ValueError:
            cls.has_demo = False

    def test_demo_users_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        users = self.env['res.users'].search([
            ('login', 'in', ['alice@example.com', 'bob@example.com']),
        ])
        self.assertEqual(len(users), 2)

    def test_demo_folders_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        folders = self.env['joplin.folder'].search([
            ('joplin_id', 'like', 'a%'),
        ])
        self.assertGreaterEqual(len(folders), 8)

    def test_demo_tags_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        tags = self.env['joplin.tag'].search([
            ('joplin_id', 'like', 't%'),
        ])
        self.assertGreaterEqual(len(tags), 9)

    def test_demo_notes_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        notes = self.env['joplin.note'].with_context(active_test=False).search([
            ('joplin_id', 'like', 'n%'),
        ])
        self.assertGreaterEqual(len(notes), 12)

    def test_demo_trashed_note(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        note = self.env.ref('knowledge_joplin.demo_note_trashed')
        self.assertFalse(note.active)

    def test_demo_mermaid_note(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        note = self.env.ref('knowledge_joplin.demo_note_mermaid')
        self.assertIn('```mermaid', note.body)
        self.assertIn('graph TD', note.body)
        self.assertIn('sequenceDiagram', note.body)

    def test_demo_python_note(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        note = self.env.ref('knowledge_joplin.demo_note_python')
        self.assertIn('async def main', note.body)
        self.assertIn('TaskGroup', note.body)

    def test_demo_revisions_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        revisions = self.env['joplin.revision'].search([
            ('joplin_id', 'like', 'v%'),
        ])
        self.assertGreaterEqual(len(revisions), 5)

    def test_demo_resources_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        resources = self.env['joplin.resource'].search([
            ('joplin_id', 'like', 'r%'),
        ])
        self.assertGreaterEqual(len(resources), 3)

    def test_demo_api_tokens_exist(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        tokens = self.env['joplin.api.token'].search([
            ('name', 'like', '%API%'),
        ])
        self.assertGreaterEqual(len(tokens), 2)

    def test_demo_folder_hierarchy(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        projects = self.env.ref('knowledge_joplin.demo_folder_projects')
        self.assertTrue(projects.parent_id)
        self.assertEqual(projects.parent_id.name, 'Work')

    def test_demo_user2_notes_isolation(self):
        if not self.has_demo:
            self.skipTest('Demo data not loaded')
        bob_notes = self.env['joplin.note'].with_context(active_test=False).search([
            ('user_id', '=', self.env.ref('knowledge_joplin.demo_user_joplin_2').id),
        ])
        self.assertGreaterEqual(len(bob_notes), 2)
