import json
import secrets
from datetime import datetime, timezone, timedelta

from odoo.tests import common, tagged
from odoo.exceptions import AccessError, ValidationError
from odoo import fields


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
