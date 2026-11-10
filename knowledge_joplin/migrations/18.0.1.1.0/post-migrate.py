# -*- coding: utf-8 -*-
"""Back-fill deleted_time for folders and tags that were trashed before the
field existed.

Until 18.0.1.1.0 only joplin.note carried deleted_time; joplin.folder and
joplin.tag were archived with active=False and no tombstone timestamp. The
sync protocol reports a deletion by sending a non-zero deleted_time, so
without this a notebook trashed before the upgrade stays invisible to the
client forever.

Guarded so it is a no-op on re-run: it only touches rows that are inactive
AND have no deleted_time.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Fresh install — nothing to back-fill, the column starts empty and
        # every row it applies to is created afterwards by correct code.
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    for model_name in ('joplin.folder', 'joplin.tag'):
        if model_name not in env:
            continue
        # with_context(active_test=False) is essential: the rows we are
        # looking for are exactly the archived ones.
        records = (
            env[model_name]
            .with_context(active_test=False)
            .search([('active', '=', False), ('deleted_time', '=', False)])
        )
        if not records:
            _logger.info(
                "knowledge_joplin: %s — nothing to back-fill", model_name
            )
            continue
        for rec in records:
            # write_date is the best available approximation of when the row
            # was trashed. A trashed-then-restored row could carry a stale
            # value; harmless, because any non-zero value only means
            # "deleted", and a restore clears it.
            rec.with_context(active_test=False).write(
                {'deleted_time': rec.write_date or fields_now()}
            )
        _logger.info(
            "knowledge_joplin: %s — back-filled deleted_time on %s row(s)",
            model_name,
            len(records),
        )


def fields_now():
    """Fallback only: write_date is always set on a persisted row."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)
