# knowledge_joplin — sync contract

Odoo's server side of the Joplin sync protocol (E2EE-off, `/joplin/api`).
The Android/desktop client treats Odoo as a Joplin sync target.

This file documents what the client may rely on. It exists because that
contract was previously implicit and partly wrong — the client reported new
notes that then did not appear in their notebook, and a search in the client
found notes the notebook list never showed.

## One delta, one order

`GET /:<path>:/delta` and the legacy `GET /joplin/api/delta` are the same
enumeration: `models/joplin_sync.py:delta_items(env, cursor=None, limit=None)`.

- Every item type the protocol carries is included: note, folder, tag,
  resource and note-tag relations. `joplin.item` is **not** — it is the
  debris table for content the sync does not understand, and it stays
  reachable by raw path (`content_for`/`ingest`), just not reported.
- Order is `(updated_time, item_name)` ascending, compared in epoch
  milliseconds. The cursor is that pair as an opaque `'<epoch_ms>|<item_name>'`
  string.
- `has_more` is real and the cursor only advances past items actually
  returned, so paging to exhaustion reports each changed item exactly once
  and a further call reports nothing.
- An id is not used for ordering: an Odoo row id is unique only per table
  and cannot order a delta that spans five models. `item_name` is the
  protocol's own global item identity.
- A cursor that cannot be decoded (junk, or a legacy numeric timestamp from
  the old implementation) falls back to a full delta. It never silently
  skips items.

### Request parameters

`limit` and `cursor` are read from the query string (GET) or a JSON body
(POST) by `controllers/joplin_api.py:_parse_delta_params()`. A junk or
non-positive `limit` falls back to the default page size rather than
raising — a client must never get a 500 for a badly formed page size.

This used to be broken: the route forwarded neither parameter, so every
call ran unpaged from the start and page 2 came back empty with
`has_more: false` — which reads exactly like "the delta is complete" and
made every item past page 1 invisible. The paging tests did not catch it
because they call `delta_items()` directly; `TestDeltaRequestParameters`
now covers the parsing and pins a shortened page to a real `has_more`.

Note the delta is scoped to the token's user: a walk returns that user's
items only, which is why a non-admin walk is shorter than the table count.

## Soft delete on every item type

Joplin carries `deleted_time` on folders and tags as well as notes.
`joplin.folder` and `joplin.tag` have the field, mirror it into `active`, and
expose `action_trash()` / `action_restore()`. Servers and clients therefore
agree on what is trashed, and a trashed folder still serialises instead of
raising.

`joplin.resource` genuinely has no `deleted_time`; the field map omits it and
a test (`test_soft_delete_is_modelled_where_the_map_claims_it`) keeps map and
model in agreement in both directions.

### `deleted_time` back-fill

Rows trashed before the field existed have `active = False` and no timestamp.
`migrations/18.0.1.1.0/post-migrate.py` sets `deleted_time = write_date` for
exactly those rows (`active = False AND deleted_time IS NULL`), in both
`joplin_folder` and `joplin_tag`. The migration is a guarded no-op on a fresh
install and on a re-run, so it is safe to apply repeatedly.

An operator seeing an old trashed folder with a `deleted_time` equal to its
`write_date` is looking at that back-fill, not at a real delete event.

## Client timestamps are trusted

`joplin.note`, `joplin.folder`, `joplin.tag` and `joplin.resource` all set
`updated_time` only when the writer did not supply one.

- Ingest passes the timestamp from the Joplin item, so a sync does not make
  every record look newly modified (which would re-yield it forever).
- A normal edit through the Odoo UI supplies no `updated_time`, so it still
  advances — that is what makes the edit visible to the next delta.

Both halves are pinned by `TestWriteTimestampRules`.

## Folder shells

Ingesting a note whose folder has not arrived yet creates the folder shell
rather than dropping the note or the parent link (`_resolve_folder`). The
notebook list therefore cannot be empty while the notes in it exist, and
`_ingest_notetag` creates shells for either end of the relation instead of
silently discarding the tag.

## Running the tests

```bash
# 0 failed, 0 error(s) of 143 tests on a clean database
sudo checkmodule -d <db> -m knowledge_joplin -t > /tmp/kj.log 2>&1
```

`checkmodule -t` writes the result to `/var/log/odoo/odoo-server.log`
(`odoo.tests.result`), not to the redirected stdout — grep the log for the
count. The sync tests are `TransactionCase`/ORM by design; driving them over
HTTP fails under `PreforkServer`.

## Rolling back

This change is additive, so a revert is cheap:

```bash
git -C /usr/share/odoo-knowledge revert <sha>
# restore `version` in __manifest__.py to the previous value
sudo checkmodule -d <db> -m knowledge_joplin
sudo systemctl restart odoo
```

What reverts cleanly: the rewritten `delta_items()`, the guarded
`write()` on note/folder/tag/resource, the new folder/tag helpers, and the
controller delegation.

What stays, harmlessly: the added `deleted_time` and `active` columns. They
are nullable/defaulted and unread by reverted code. The back-fill migration
is a guarded no-op on re-run and does not need to be undone — it only filled
in a timestamp that was already implied by `active = False`.

The one asymmetry worth knowing: after a rollback the legacy
`/joplin/api/delta` emits the old numeric timestamp cursor again. A client
still holding a new `'<epoch_ms>|<item_name>'` cursor cannot decode it and
gets a **full** delta rather than skipping items — a larger response, never
a lost note. The reverse direction is covered by the same rule: undecodable
cursors fall back to full delta.

## Upgrading into this version — check the view tree first

Installing this module on a database whose other modules have drifted can
fail for reasons that have nothing to do with Joplin. The proven case
(2026-11-10, `luke18a`): every `--update` aborted with a NULL `parent_id` in
`ir_model_inherit`, which looked like an inheritance bug here but was really
a stale view owned by `saltstack`.

If an upgrade dies and the traceback is nowhere to be found, note that
`checkmodule` deliberately splits the child's stderr away from its own log,
and `logfile` in `/etc/odoo/odoo.conf` overrides stdout — so redirecting to a
file yields an **empty** file. Run the update directly to see the error:

```bash
cd /usr/share/odoo-<repo>
sudo -u odoo odoo --config /etc/odoo/odoo.conf -d <db> \
  --update <module> --stop-after-init \
  --logfile=/dev/stdout --log-level=warn 2>&1 | tail -40
```

A `ParseError` naming a field that exists in no module you have is usually a
**stale sibling view**: views sharing a parent form are validated together, so
one module's dead field blocks an unrelated module's upgrade. Find it and
upgrade the *owner* first:

```sql
SELECT id, name FROM ir_ui_view WHERE arch_db::text LIKE '%<field>%';
SELECT name, latest_version FROM ir_module_module WHERE name = '<owner>';
```

Compare the latter against `version` in that module's `__manifest__.py`;
disk ≫ database means the view was never refreshed. Fix order is
owner → blocked module:

```bash
sudo -u odoo odoo --config /etc/odoo/odoo.conf -d <db> \
  --update <owner>,<blocked>,knowledge_joplin --stop-after-init \
  --logfile=/dev/stdout --log-level=warn
```
