"""Regression tests for the Android sync-visibility defects.

These exercise the ORM directly (TransactionCase, not HttpCase): under
PreforkServer an HttpCase has no httpd to talk to, so an HTTP test would
error before it proved anything.

What is asserted here, and why each one is a real defect that shipped:

* every ``*_FIELDS`` map names fields that exist — ``_FOLDER_FIELDS``
  mapped ``deleted_time`` on a model that had no such field, so
  serialising ANY folder raised KeyError and the client was told it had
  no notebooks while the notes were plainly searchable;
* a folder/tag survives a deleted_time round trip;
* the delta pages without duplicates and converges to empty;
* the delta's item set equals a single-shot enumeration;
* a note whose parent folder is unknown still resolves to a folder
  (a shell), never to "no notebook".
"""
import uuid

from odoo.tests import TransactionCase, tagged

from odoo.addons.knowledge_joplin.models import joplin_sync


def _jid():
    """A fresh 32-hex joplin id, unique per test run."""
    return uuid.uuid4().hex


@tagged('post_install', '-at_install')
class TestFieldMaps(TransactionCase):
    """Every mapped field must exist on the target model."""

    MAPS = (
        ('_NOTE_FIELDS', 'joplin.note'),
        ('_FOLDER_FIELDS', 'joplin.folder'),
        ('_TAG_FIELDS', 'joplin.tag'),
        ('_RESOURCE_FIELDS', 'joplin.resource'),
    )

    def test_every_mapped_field_exists(self):
        for attr, model in self.MAPS:
            field_map = getattr(joplin_sync, attr)
            have = set(self.env[model]._fields)
            missing = sorted({okey for _jkey, okey in field_map
                              if okey not in have})
            self.assertEqual(
                missing, [],
                "%s maps fields that %s does not have: %s"
                % (attr, model, missing),
            )

    def test_deleted_time_is_carried_on_every_item_type(self):
        # Joplin's protocol puts deleted_time on notes, folders and tags
        # alike. A model missing it cannot report a deletion.
        for model in ('joplin.note', 'joplin.folder', 'joplin.tag'):
            self.assertIn('deleted_time', self.env[model]._fields, model)


@tagged('post_install', '-at_install')
class TestFolderSerialisation(TransactionCase):
    """The defect that hid the notebooks."""

    def test_folder_serialises(self):
        folder = self.env['joplin.folder'].create({
            'name': 'Notebook',
            'joplin_id': _jid(),
        })
        text = joplin_sync._folder_to_item(folder)
        self.assertIn('Notebook', text)
        self.assertIn('type_: 2', text)

    def test_folder_deleted_time_round_trip(self):
        folder = self.env['joplin.folder'].create({
            'name': 'Doomed',
            'joplin_id': _jid(),
        })
        stamp = '2026-01-02 03:04:05'
        joplin_sync._apply_fields(
            folder,
            {'props': {'deleted_time': stamp}},
            joplin_sync._FOLDER_FIELDS,
        )
        # _apply_fields only builds vals; apply them to prove the field is
        # writable and readable, not merely present in _fields.
        folder.write(joplin_sync._apply_fields(
            folder,
            {'props': {'deleted_time': stamp}},
            joplin_sync._FOLDER_FIELDS,
        ))
        self.assertTrue(folder.deleted_time)
        self.assertIn('deleted_time: ', joplin_sync._folder_to_item(folder))

    def test_tag_soft_delete_mirrors_active(self):
        tag = self.env['joplin.tag'].create({
            'name': 'sometag',
            'joplin_id': _jid(),
        })
        tag.action_trash()
        self.assertFalse(tag.active)
        self.assertTrue(tag.deleted_time)
        tag.action_restore()
        self.assertTrue(tag.active)
        self.assertFalse(tag.deleted_time)


@tagged('post_install', '-at_install')
class TestDeltaPaging(TransactionCase):
    """The delta must page cleanly and converge."""

    def _make_items(self, count=12):
        created = []
        for i in range(count):
            created.append(self.env['joplin.note'].create({
                'title': 'delta note %d' % i,
                'body': 'body',
                'joplin_id': _jid(),
            }))
        return created

    def test_delta_pages_without_duplicates_and_converges(self):
        self._make_items(12)

        seen, cursor, pages = [], None, 0
        while pages < 200:
            items, cursor, has_more = joplin_sync.delta_items(
                self.env, cursor=cursor, limit=5)
            pages += 1
            seen.extend(item['item_name'] for item in items)
            if not has_more:
                break

        self.assertEqual(
            len(seen), len(set(seen)),
            "delta returned the same item on more than one page",
        )

        # Converged: asking again from the final cursor yields nothing.
        items, same_cursor, has_more = joplin_sync.delta_items(
            self.env, cursor=cursor, limit=5)
        self.assertEqual(items, [])
        self.assertFalse(has_more)
        self.assertEqual(same_cursor, cursor)

    def test_delta_item_set_equals_single_shot(self):
        self._make_items(8)

        seen, cursor, pages = [], None, 0
        while pages < 200:
            items, cursor, has_more = joplin_sync.delta_items(
                self.env, cursor=cursor, limit=3)
            pages += 1
            seen.extend(item['item_name'] for item in items)
            if not has_more:
                break

        everything, _cursor, _more = joplin_sync.delta_items(
            self.env, limit=100000)
        self.assertEqual(
            {item['item_name'] for item in everything},
            set(seen),
            "paged delta and single-shot delta disagree",
        )

    def test_delta_does_not_enumerate_raw_items(self):
        # joplin.item is protocol debris (locks, .sync state). Enumerating
        # it made a fresh client discover junk and miss the real notes.
        self.env['joplin.item'].create({
            'path': '/debris-%s.md' % _jid(),
            'content': 'garbage',
            'updated_time': '2026-01-01 00:00:00',
        })
        items, _cursor, _more = joplin_sync.delta_items(self.env, limit=100000)
        names = {item['item_name'] for item in items}
        self.assertFalse(
            any(name.startswith('debris-') for name in names),
            "raw joplin.item rows must not appear in the delta",
        )


@tagged('post_install', '-at_install')
class TestNotebookAgreement(TransactionCase):
    """Client notebooks and Odoo folders must not disagree."""

    def test_note_with_unknown_parent_gets_a_folder_shell(self):
        parent_jid = _jid()
        index = {
            'id': _jid(),
            'parent_id': parent_jid,
            'title': 'child of an unseen notebook',
            'body': '',
            'type_': joplin_sync.TYPE_NOTE,
        }
        text = joplin_sync.serialize_item(
            'child of an unseen notebook', None,
            [(key, index[key]) for key in
             ('id', 'parent_id', 'title', 'body', 'type_')],
        )
        joplin_sync.ingest(
            self.env, '/%s.md' % index['id'], text)

        note = self.env['joplin.note'].search(
            [('joplin_id', '=', index['id'])], limit=1)
        self.assertTrue(note, "note was not ingested")
        self.assertTrue(
            note.folder_id,
            "a note whose parent folder was unknown must still get a "
            "folder shell, otherwise the client shows no notebook at all",
        )
        self.assertEqual(note.folder_id.joplin_id, parent_jid)

    def test_folder_is_serialisable_after_trash_and_restore(self):
        folder = self.env['joplin.folder'].create({
            'name': 'Round trip',
            'joplin_id': _jid(),
        })
        before = joplin_sync._folder_to_item(folder)
        folder.action_trash()
        trashed = joplin_sync._folder_to_item(folder)
        folder.action_restore()
        after = joplin_sync._folder_to_item(folder)

        self.assertIn('Round trip', before)
        self.assertIn('Round trip', trashed)
        self.assertIn('Round trip', after)
        # The trash is visible on the wire, which is how the client learns
        # about it at all.
        self.assertNotEqual(before, trashed)


@tagged('post_install', '-at_install')
class TestFieldMapSymmetry(TransactionCase):
    """The map is the single source of truth for serve AND ingest.

    Nothing asserted that before, which is how ``_FOLDER_FIELDS`` came to
    map a ``deleted_time`` that did not exist.
    """

    MAPS = (
        ('_NOTE_FIELDS', 'joplin.note'),
        ('_FOLDER_FIELDS', 'joplin.folder'),
        ('_TAG_FIELDS', 'joplin.tag'),
        ('_RESOURCE_FIELDS', 'joplin.resource'),
    )

    # Handled explicitly by the serialisers because they are not item
    # properties: the title is the item header, the body is the payload.
    SPECIAL = {'joplin_id', 'title', 'body', 'name'}

    def _map(self, attr, model):
        return getattr(joplin_sync, attr), self.env[model]._fields

    def test_every_map_target_exists(self):
        for attr, model in self.MAPS:
            field_map, fields = self._map(attr, model)
            missing = sorted({okey for _jkey, okey in field_map
                              if okey not in fields})
            self.assertEqual(
                missing, [],
                "%s maps targets that %s does not have: %s"
                % (attr, model, missing),
            )

    def test_no_duplicate_joplin_keys(self):
        for attr, model in self.MAPS:
            field_map, _fields = self._map(attr, model)
            keys = [jkey for jkey, _okey in field_map]
            self.assertEqual(
                sorted(keys), sorted(set(keys)),
                "%s maps the same joplin key twice" % attr,
            )

    def test_timestamp_fields_are_on_every_item_type(self):
        # created_time/updated_time come from Joplin's common item base.
        for model in ('joplin.note', 'joplin.folder',
                      'joplin.tag', 'joplin.resource'):
            fields = self.env[model]._fields
            for name in ('created_time', 'updated_time'):
                self.assertIn(name, fields, '%s lacks %s' % (model, name))

    def test_soft_delete_is_modelled_where_the_map_claims_it(self):
        # deleted_time is only meaningful where the map carries it; a model
        # that lacks the column must not be mapped as if it had one.
        for attr, model in self.MAPS:
            field_map = getattr(joplin_sync, attr)
            keys = {jkey for jkey, _okey in field_map}
            self.assertEqual(
                'deleted_time' in keys, 'deleted_time' in self.env[model]._fields,
                '%s and %s disagree about deleted_time' % (attr, model),
            )

    def test_every_mapped_odoo_field_is_stored(self):
        # A map target that is not stored cannot round-trip: the ingest
        # writes a value the database discards, and the next serve reports
        # the original.
        unstored = []
        for attr, model in self.MAPS:
            field_map, fields = self._map(attr, model)
            for _jkey, okey in field_map:
                field = fields[okey]
                if field.type in ('one2many', 'many2many'):
                    continue
                if not field.store:
                    unstored.append('%s -> %s.%s' % (attr, model, okey))
        self.assertEqual(unstored, [], 'map targets that do not persist')

    def test_deleted_time_is_mapped_not_merely_present(self):
        # The tag model gained a deleted_time column in this change; the
        # field existing is not enough, the map has to carry it or the
        # value never reaches the client.
        for attr in ('_NOTE_FIELDS', '_FOLDER_FIELDS', '_TAG_FIELDS'):
            field_map = getattr(joplin_sync, attr)
            keys = {jkey for jkey, _okey in field_map}
            self.assertIn(
                'deleted_time', keys,
                '%s does not carry deleted_time, so a deletion in that '
                'item type can never be reported' % attr,
            )


@tagged('post_install', '-at_install')
class TestServeIngestFixedPoint(TransactionCase):
    """serve -> ingest -> serve must be a fixed point, per item type.

    The same ``*_FIELDS`` map drives both directions, so any asymmetry
    shows up here as a property that changes on the second round trip.
    """

    def _round_trip(self, model, record, path):
        """Serve a record, ingest the text, and return the re-served text."""
        served, _mime = joplin_sync.content_for(self.env, path)
        self.assertTrue(served, 'nothing served for %s' % path)
        joplin_sync.ingest(self.env, path, served)
        again, _mime = joplin_sync.content_for(self.env, path)
        return served, again

    def test_note_fixed_point(self):
        folder = self.env['joplin.folder'].create({
            'name': 'Fixed point',
            'joplin_id': _jid(),
        })
        note = self.env['joplin.note'].create({
            'title': 'fixed point note',
            'body': 'line one\nline two\n\nline four',
            'folder_id': folder.id,
            'joplin_id': _jid(),
            'source_url': 'https://example.invalid/x',
            'markup_language': 1,
            'is_todo': True,
            'todo_due': '2026-03-04 05:06:07',
            'todo_completed': '2026-03-05 06:07:08',
        })
        before = self.env['joplin.note'].browse(note.id).read(
            ['title', 'body', 'folder_id', 'source_url',
             'markup_language', 'is_todo', 'todo_due',
             'todo_completed'])[0]

        served, again = self._round_trip(
            'joplin.note', note, '/%s.md' % note.joplin_id)

        self.assertEqual(served, again, 'note serve/ingest is not stable')

        after = self.env['joplin.note'].browse(note.id).read(
            ['title', 'body', 'folder_id', 'source_url',
             'markup_language', 'is_todo', 'todo_due',
             'todo_completed'])[0]
        self.assertEqual(before, after, 'the round trip changed the record')

    def test_folder_fixed_point(self):
        folder = self.env['joplin.folder'].create({
            'name': 'Folder fixed point',
            'joplin_id': _jid(),
            'icon': '1',
        })
        served, again = self._round_trip(
            'joplin.folder', folder, '/%s.md' % folder.joplin_id)
        self.assertEqual(served, again)
        self.assertIn('Folder fixed point', again)
        self.assertIn('type_: 2', again)

    def test_tag_fixed_point(self):
        tag = self.env['joplin.tag'].create({
            'name': 'tag-fixed-point',
            'joplin_id': _jid(),
        })
        served, again = self._round_trip(
            'joplin.tag', tag, '/%s.md' % tag.joplin_id)
        self.assertEqual(served, again)
        self.assertIn('tag-fixed-point', again)
        self.assertIn('type_: 5', again)

    def test_resource_fixed_point(self):
        note = self.env['joplin.note'].create({
            'title': 'owner',
            'body': '',
            'joplin_id': _jid(),
        })
        resource = self.env['joplin.resource'].create({
            'filename': 'a.txt',
            'mime': 'text/plain',
            'file_extension': 'txt',
            'note_id': note.id,
            'joplin_id': _jid(),
            'datas': 'aGVsbG8=',
        })
        served, again = self._round_trip(
            'joplin.resource', resource, '/%s.md' % resource.joplin_id)
        self.assertEqual(served, again)
        self.assertIn('a.txt', again)
        self.assertIn('type_: 4', again)


@tagged('post_install', '-at_install')
class TestPropertyRoundTrip(TransactionCase):
    """Specific properties must survive serve -> ingest."""

    def test_note_properties_survive(self):
        parent = self.env['joplin.folder'].create({
            'name': 'Parent', 'joplin_id': _jid(),
        })
        note = self.env['joplin.note'].create({
            'title': 'Round trip title',
            'body': 'first\nsecond\n\nfourth',
            'folder_id': parent.id,
            'joplin_id': _jid(),
            'created_time': '2026-01-01 10:00:00',
            'updated_time': '2026-01-02 11:00:00',
        })
        text, _mime = joplin_sync.content_for(
            self.env, '/%s.md' % note.joplin_id)
        joplin_sync.ingest(self.env, '/%s.md' % note.joplin_id, text)

        again = self.env['joplin.note'].browse(note.id)
        self.assertEqual(again.title, 'Round trip title')
        self.assertEqual(again.body, 'first\nsecond\n\nfourth')
        self.assertEqual(again.folder_id, parent)
        # Client timestamps, not the server clock (D6).
        self.assertEqual(
            again.created_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2026-01-01 10:00:00')
        self.assertEqual(
            again.updated_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2026-01-02 11:00:00')

    def test_subfolder_parent_survives(self):
        root = self.env['joplin.folder'].create({
            'name': 'Root', 'joplin_id': _jid(),
        })
        child = self.env['joplin.folder'].create({
            'name': 'Child', 'joplin_id': _jid(),
            'parent_id': root.id,
        })
        text, _mime = joplin_sync.content_for(
            self.env, '/%s.md' % child.joplin_id)
        joplin_sync.ingest(self.env, '/%s.md' % child.joplin_id, text)

        again = self.env['joplin.folder'].browse(child.id)
        self.assertEqual(again.name, 'Child')
        self.assertEqual(again.parent_id, root)


@tagged('post_install', '-at_install')
class TestWriteTimestampRules(TransactionCase):
    """D6: an explicit updated_time wins, an absent one advances.

    Trusting the client's timestamp must not freeze the column: a normal
    edit in the Odoo UI sends no updated_time and has to look changed to
    the next delta.
    """

    OLD = '2020-01-01 00:00:00'

    def _advances(self, model, create_vals, edit_vals):
        record = self.env[model].create(dict(
            create_vals, joplin_id=_jid(), updated_time=self.OLD))
        self.assertEqual(
            record.updated_time.strftime('%Y-%m-%d %H:%M:%S'), self.OLD)
        record.write(edit_vals)
        record.invalidate_recordset()
        self.assertGreater(
            record.updated_time.strftime('%Y-%m-%d %H:%M:%S'), self.OLD,
            '%s.write() did not advance updated_time for a UI edit'
            % model)

    def _keeps(self, model, create_vals, edit_vals):
        record = self.env[model].create(dict(
            create_vals, joplin_id=_jid(), updated_time=self.OLD))
        record.write(dict(edit_vals, updated_time='2026-05-05 05:05:05'))
        record.invalidate_recordset()
        self.assertEqual(
            record.updated_time.strftime('%Y-%m-%d %H:%M:%S'),
            '2026-05-05 05:05:05',
            '%s.write() clobbered an explicitly supplied updated_time'
            % model)

    def test_ui_edit_advances_note(self):
        self._advances('joplin.note', {'title': 'a', 'body': ''},
                       {'title': 'b'})

    def test_ui_edit_advances_folder(self):
        self._advances('joplin.folder', {'name': 'a'}, {'name': 'b'})

    def test_ui_edit_advances_tag(self):
        self._advances('joplin.tag', {'name': 'a'}, {'name': 'b'})

    def test_client_timestamp_wins_note(self):
        self._keeps('joplin.note', {'title': 'a', 'body': ''}, {'title': 'b'})

    def test_client_timestamp_wins_folder(self):
        self._keeps('joplin.folder', {'name': 'a'}, {'name': 'b'})

    def test_client_timestamp_wins_tag(self):
        self._keeps('joplin.tag', {'name': 'a'}, {'name': 'b'})


@tagged('post_install', '-at_install')
class TestNotebookTreeAgreement(TransactionCase):
    """The reported bug: the client reports notes but shows no notebooks.

    Every note's notebook must be in the same delta that reports the note,
    and every item type must be fetchable without a server error.
    """

    def _tree(self):
        root = self.env['joplin.folder'].create({
            'name': 'Root', 'joplin_id': _jid()})
        sub = self.env['joplin.folder'].create({
            'name': 'Sub', 'joplin_id': _jid(), 'parent_id': root.id})
        notes = [
            self.env['joplin.note'].create({
                'title': 'in root %d' % i, 'body': 'body', 'joplin_id': _jid(),
                'folder_id': root.id})
            for i in range(2)
        ] + [
            self.env['joplin.note'].create({
                'title': 'in sub %d' % i, 'body': 'body', 'joplin_id': _jid(),
                'folder_id': sub.id})
            for i in range(2)
        ]
        tag = self.env['joplin.tag'].create({
            'name': 'notebook-tag', 'joplin_id': _jid()})
        notes[0].write({'tag_ids': [(4, tag.id)]})
        resource = self.env['joplin.resource'].create({
            'filename': 'r.txt', 'mime': 'text/plain', 'joplin_id': _jid(),
            'note_id': notes[0].id, 'datas': 'aGVsbG8='})
        return root, sub, notes, tag, resource

    def _all_delta_names(self):
        names, cursor, has_more = set(), None, True
        guard = 0
        while has_more and guard < 50:
            items, cursor, has_more = joplin_sync.delta_items(
                self.env, cursor=cursor, limit=10)
            for item in items:
                names.add(item['item_name'])
            guard += 1
        return names

    def test_every_note_notebook_is_in_the_delta(self):
        root, sub, notes, tag, resource = self._tree()
        reported = self._all_delta_names()

        for note in notes:
            self.assertIn(
                '%s.md' % note.joplin_id, reported,
                'note %r was not reported by the delta' % note.title)
            self.assertTrue(note.folder_id, 'note lost its notebook')
            self.assertIn(
                '%s.md' % note.folder_id.joplin_id, reported,
                'notebook %r of note %r was not in the delta — this is the '
                'bug where the client lists notes but no notebooks'
                % (note.folder_id.name, note.title))

    def test_every_item_type_has_content(self):
        root, sub, notes, tag, resource = self._tree()
        paths = ['/%s.md' % root.joplin_id, '/%s.md' % sub.joplin_id,
                 '/%s.md' % notes[0].joplin_id,
                 '/%s.md' % tag.joplin_id,
                 '/%s.md' % resource.joplin_id]
        for path in paths:
            content, mime = joplin_sync.content_for(self.env, path)
            self.assertTrue(content, 'no content served for %s' % path)
            self.assertTrue(mime, 'no mime type for %s' % path)
            self.assertIsNotNone(joplin_sync.stat_for(self.env, path),
                                 'no stat for %s' % path)

    def test_every_delta_item_is_fetchable(self):
        # The generalised form of the note-tag 404. delta_items() advertises
        # item names; if any advertised name cannot be resolved by content_for
        # / stat_for, the client sees "found a new item" and then a 404 forever.
        # Note-tags are the case that shipped broken, because they are a
        # relation rather than a row and _record_kind_by_id() cannot see them.
        root, sub, notes, tag, resource = self._tree()
        for name in self._all_delta_names():
            path = '/%s' % name
            content, mime = joplin_sync.content_for(self.env, path)
            self.assertIsNotNone(
                content,
                'delta advertises %r but content_for returns None' % name)
            self.assertTrue(mime, 'no mime type for %r' % name)
            self.assertIsNotNone(
                joplin_sync.stat_for(self.env, path),
                'delta advertises %r but stat_for returns None' % name)

    def test_note_tag_item_round_trips(self):
        # A type-6 item must parse back into the same (note, tag) pair that
        # _ingest_notetag() wrote, or a client re-uploading what it downloaded
        # would corrupt the relation.
        root, sub, notes, tag, resource = self._tree()
        ntid = joplin_sync.notetag_id(notes[0].joplin_id, tag.joplin_id)

        self.assertIn('%s.md' % ntid, self._all_delta_names(),
                      'the note/tag relation is not advertised')

        content, _mime = joplin_sync.content_for(
            self.env, '/%s.md' % ntid)
        self.assertIsNotNone(content, 'note-tag content is not served')

        parsed = joplin_sync.unserialize_item(content)
        self.assertEqual(parsed['type_'], joplin_sync.TYPE_NOTE_TAG)
        self.assertEqual(parsed['props']['note_id'], notes[0].joplin_id)
        self.assertEqual(parsed['props']['tag_id'], tag.joplin_id)

    def test_searchable_note_is_also_in_the_delta(self):
        # The concrete symptom: the Android app's search finds the note,
        # sync does not show it.
        root, sub, notes, tag, resource = self._tree()
        needle = 'needle-in-a-notebook'
        notes[2].write({'title': needle, 'body': 'body'})

        found = self.env['joplin.note'].search([('title', '=', needle)])
        self.assertEqual(len(found), 1, 'fixture note is not searchable')

        reported = self._all_delta_names()
        self.assertIn(
            '%s.md' % found.joplin_id, reported,
            'a note that the search path finds is invisible to the delta')


@tagged('post_install', '-at_install')
class TestPerUserBoundary(TransactionCase):
    """Sync must not leak one user's notes to another."""

    def setUp(self):
        super().setUp()
        Users = self.env['res.users'].with_context(
            no_reset_password=True, tracking_disable=True)
        self.user_a = Users.create({
            'name': 'Sync A', 'login': 'sync_a_%s' % _jid()[:8],
            'email': 'a_%s@example.invalid' % _jid()[:8],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.user_b = Users.create({
            'name': 'Sync B', 'login': 'sync_b_%s' % _jid()[:8],
            'email': 'b_%s@example.invalid' % _jid()[:8],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.note_b = self.env['joplin.note'].with_user(self.user_b).create({
            'title': 'private to B', 'body': 'secret', 'joplin_id': _jid(),
        })

    def test_delta_as_a_excludes_b(self):
        self.env['joplin.note'].with_user(self.user_a).create({
            'title': 'visible to A', 'body': 'x', 'joplin_id': _jid()})

        items, _cursor, _more = joplin_sync.delta_items(
            self.env(user=self.user_a), limit=400)
        names = {item['item_name'] for item in items}
        self.assertNotIn('%s.md' % self.note_b.joplin_id, names,
                         "user A's delta reported user B's note")

    def test_direct_item_request_as_a_denied(self):
        path = '/%s.md' % self.note_b.joplin_id
        content, _mime = joplin_sync.content_for(
            self.env(user=self.user_a), path)
        self.assertFalse(content,
                         "user A fetched user B's note by identifier")
        self.assertIsNone(joplin_sync.stat_for(
            self.env(user=self.user_a), path))

    def test_shared_note_reaches_the_follower(self):
        # Following is the documented sharing mechanism; a note a user may
        # read through following must be reported by that user's delta.
        self.note_b.message_subscribe(partner_ids=self.user_a.partner_id.ids)
        items, _cursor, _more = joplin_sync.delta_items(
            self.env(user=self.user_a), limit=400)
        names = {item['item_name'] for item in items}
        self.assertIn('%s.md' % self.note_b.joplin_id, names,
                      'a followed note is missing from the follower delta')



@tagged('post_install', '-at_install')
class TestDeltaRequestParameters(TransactionCase):
    """The route must honour ``limit`` and ``cursor``.

    The paging tests above call ``delta_items()`` directly, so they were
    blind to the controller dropping the request parameters. A client
    asking ``?limit=3&cursor=...`` got page 1 and then an empty page 2,
    which is indistinguishable from "the delta is complete" and hid every
    item after the first page. That is the reported symptom.
    """

    def _helper(self):
        from odoo.addons.knowledge_joplin.controllers.joplin_api import (
            _parse_delta_params,
        )
        return _parse_delta_params

    def test_limit_is_forwarded(self):
        cursor, limit = self._helper()({'limit': '3'})
        self.assertIsNone(cursor)
        self.assertEqual(limit, 3)

    def test_cursor_is_forwarded(self):
        cursor, limit = self._helper()({'cursor': '123|a.md', 'limit': '5'})
        self.assertEqual(cursor, '123|a.md')
        self.assertEqual(limit, 5)

    def test_junk_limit_falls_back_to_default(self):
        for junk in ('', 'abc', '0', '-1'):
            _cursor, limit = self._helper()({'limit': junk})
            self.assertIsNone(limit, 'limit %r should be ignored' % junk)

    def test_missing_params_are_none(self):
        cursor, limit = self._helper()({})
        self.assertIsNone(cursor)
        self.assertIsNone(limit)

    def test_post_body_cursor_is_read(self):
        cursor, limit = self._helper()(
            {}, data=b'{"cursor": "42|b.md", "limit": 2}', is_post=True)
        self.assertEqual(cursor, '42|b.md')
        self.assertEqual(limit, 2)

    def test_malformed_post_body_does_not_raise(self):
        cursor, limit = self._helper()({}, data=b'not json', is_post=True)
        self.assertIsNone(cursor)
        self.assertIsNone(limit)

    def test_limit_actually_truncates_the_delta(self):
        """A forwarded limit must shorten the page, not be ignored."""
        for i in range(6):
            self.env['joplin.note'].create({
                'title': 'param note %d' % i,
                'body': 'body',
                'joplin_id': _jid(),
            })
        items, _cursor, has_more = joplin_sync.delta_items(self.env, limit=3)
        self.assertEqual(len(items), 3)
        self.assertTrue(has_more, 'a truncated page must report has_more')


@tagged('post_install', '-at_install')
class TestTimestampsNeverEmpty(TransactionCase):
    """No item may ever be served with an empty or unparsable timestamp.

    Joplin's ``BaseItem.ts`` turns an empty timestamp string into ``0``. An
    item whose ``user_updated_time`` is always 0 can never satisfy
    ``remote.jop_updated_time === local.updated_time``, so the client re-syncs
    it on every poll — the observed 404/conflict storm.
    """

    def test_note_without_user_timestamps_is_served_filled(self):
        note = self.env['joplin.note'].create({
            'title': 'no user stamps', 'body': 'b', 'joplin_id': _jid(),
        })
        self.assertFalse(note.user_updated_time, 'precondition: column is NULL')
        props = joplin_sync.unserialize_item(
            joplin_sync._note_to_item(note))['props']
        for key in ('user_created_time', 'user_updated_time'):
            self.assertTrue(
                props.get(key),
                '%s served empty for a note with NULL %s' % (key, key))
            self.assertNotEqual(props[key], '0', '%s served as 0' % key)

    def test_all_four_models_serve_parsable_user_timestamps(self):
        records = [
            self.env['joplin.note'].create(
                {'title': 't', 'body': 'b', 'joplin_id': _jid()}),
            self.env['joplin.folder'].create(
                {'name': 't', 'joplin_id': _jid()}),
            self.env['joplin.tag'].create(
                {'name': 't', 'joplin_id': _jid()}),
        ]
        for record in records:
            serializer = {
                'joplin.note': joplin_sync._note_to_item,
                'joplin.folder': joplin_sync._folder_to_item,
                'joplin.tag': joplin_sync._tag_to_item,
            }[record._name]
            props = joplin_sync.unserialize_item(serializer(record))['props']
            for key in ('user_created_time', 'user_updated_time'):
                self.assertTrue(
                    props.get(key),
                    '%s served empty %s' % (record._name, key))

    def test_notetag_item_carries_timestamps(self):
        """Type-6 items had no timestamp props at all (21 of 82 delta items)."""
        note = self.env['joplin.note'].create({
            'title': 'n', 'body': 'b', 'joplin_id': _jid(),
            'updated_time': '2024-03-03 03:03:03',
            'created_time': '2024-01-01 01:01:01',
        })
        tag = self.env['joplin.tag'].create({
            'name': 't', 'joplin_id': _jid(),
            'updated_time': '2024-04-04 04:04:04',
            'created_time': '2024-02-02 02:02:02',
        })
        props = joplin_sync.unserialize_item(
            joplin_sync._notetag_to_item(note, tag))['props']
        for key in ('created_time', 'updated_time',
                    'user_created_time', 'user_updated_time'):
            self.assertTrue(props.get(key), 'notetag serves no %s' % key)
        self.assertEqual(props['updated_time'], '2024-04-04T04:04:04.000Z',
                         'notetag must carry the later endpoint timestamp')
        self.assertEqual(props['created_time'], '2024-01-01T01:01:01.000Z')


@tagged('post_install', '-at_install')
class TestNotetagDoesNotEditNote(TransactionCase):
    """Re-sending a note/tag relation must not look like an edit.

    The relation ingest wrote ``{'tag_ids': [(4, id)]}``, which bumped the
    note's ``updated_time`` to now (days in the future relative to the
    client's sync_time) and minted a revision. Both are conflict triggers on
    the client side, and together they produced the conflict storm.
    """

    def setUp(self):
        super().setUp()
        self.Old = '2021-06-06 06:06:06'
        self.note = self.env['joplin.note'].create({
            'title': 'stable', 'body': 'unchanged', 'joplin_id': _jid(),
            'updated_time': self.Old, 'created_time': self.Old,
            'user_updated_time': self.Old, 'user_created_time': self.Old,
        })
        self.tag = self.env['joplin.tag'].create({
            'name': 'tag', 'joplin_id': _jid(),
            'updated_time': self.Old, 'created_time': self.Old,
        })

    def _relation_item(self):
        return {
            'id': self.note.joplin_id,
            'title': '',
            'body': '',
            'props': {
                'note_id': self.note.joplin_id,
                'tag_id': self.tag.joplin_id,
                'type_': '6',
            },
        }

    def test_relation_does_not_move_updated_time(self):
        joplin_sync._ingest_notetag(self.env, 'x', self._relation_item())
        self.note.invalidate_recordset()
        self.assertEqual(
            self.note.updated_time.strftime('%Y-%m-%d %H:%M:%S'), self.Old,
            'ingesting a note/tag relation moved the note updated_time')

    def test_relation_does_not_mint_a_revision(self):
        before = self.env['joplin.revision'].search_count(
            [('note_id', '=', self.note.id)])
        for _i in range(3):
            joplin_sync._ingest_notetag(self.env, 'x', self._relation_item())
        after = self.env['joplin.revision'].search_count(
            [('note_id', '=', self.note.id)])
        self.assertEqual(
            after, before,
            'a note/tag relation minted %d revisions' % (after - before))

    def test_relation_still_assigns_the_tag(self):
        joplin_sync._ingest_notetag(self.env, 'x', self._relation_item())
        self.note.invalidate_recordset()
        self.assertIn(self.tag, self.note.tag_ids,
                      'the tag was dropped along with the timestamp bump')

    def test_identical_put_mints_no_revision(self):
        self.note.write({'title': 'stable', 'body': 'unchanged'})
        count = self.env['joplin.revision'].search_count(
            [('note_id', '=', self.note.id)])
        self.note.write({'title': 'stable', 'body': 'unchanged'})
        self.assertEqual(
            self.env['joplin.revision'].search_count(
                [('note_id', '=', self.note.id)]), count,
            'an unchanged PUT recorded a document revision')

    def test_real_edit_still_mints_a_revision(self):
        self.note.write({'title': 'stable', 'body': 'changed now'})
        self.assertTrue(
            self.env['joplin.revision'].search_count(
                [('note_id', '=', self.note.id)]),
            'a genuine body edit must still record a revision')


@tagged('post_install', '-at_install')
class TestIngestTimestampAgreement(TransactionCase):
    """Ingest must never leave updated_time ahead of user_updated_time.

    ``sync.ts`` reads ``remoteContent.updated_time > local.sync_time`` as
    "both sides changed" and writes a conflict copy. The server must not
    manufacture that gap.
    """

    def _item(self, props):
        return {
            'id': props.get('id', _jid()),
            'title': 't',
            'body': 'b',
            'props': props,
        }

    def test_missing_user_times_are_filled_from_server_times(self):
        jid = _jid()
        joplin_sync._ingest_note(self.env, jid, self._item({
            'id': jid,
            'created_time': '2023-03-03T03:03:03.000Z',
            'updated_time': '2023-03-03T03:03:03.000Z',
        }))
        note = self.env['joplin.note'].search([('joplin_id', '=', jid)])
        self.assertTrue(note.user_updated_time,
                        'ingest left user_updated_time NULL')
        self.assertEqual(note.user_updated_time, note.updated_time,
                         'ingest created a gap without the client asking')
        self.assertEqual(note.user_created_time, note.created_time)

    def test_client_user_times_are_preserved(self):
        jid = _jid()
        joplin_sync._ingest_note(self.env, jid, self._item({
            'id': jid,
            'created_time': '2023-03-03T03:03:03.000Z',
            'updated_time': '2023-03-03T03:03:03.000Z',
            'user_created_time': '2023-01-01T01:01:01.000Z',
            'user_updated_time': '2023-02-02T02:02:02.000Z',
        }))
        note = self.env['joplin.note'].search([('joplin_id', '=', jid)])
        self.assertEqual(note.user_updated_time.strftime('%Y-%m-%d %H:%M:%S'),
                         '2023-02-02 02:02:02',
                         'the client-supplied user_updated_time was clobbered')

    def test_note_without_any_timestamp_gets_one(self):
        jid = _jid()
        joplin_sync._ingest_note(self.env, jid, self._item({'id': jid}))
        note = self.env['joplin.note'].search([('joplin_id', '=', jid)])
        self.assertTrue(note.updated_time, 'ingest stored no updated_time')
        self.assertEqual(note.updated_time, note.user_updated_time,
                         'an invented timestamp must serve both sides')
