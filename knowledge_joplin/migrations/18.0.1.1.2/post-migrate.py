# -*- coding: utf-8 -*-
"""Close the timestamp gaps that made the Joplin client mint conflicts.

Two defects are repaired here, both measured on a live installation before
the fix:

1. ``user_created_time`` / ``user_updated_time`` were NULL on rows created
   outside the sync (12 of 32 notes, 3 of 6 folders, 18 of 18 tags). The
   server served those as an empty string, and the Joplin client parses an
   empty timestamp as ``0`` (BaseItem.ts, ``unserialize_format``), so the item
   could never converge: ``remote.jop_updated_time === local.updated_time`` is
   unreachable when the remote side is always 0. Back-fill from the
   server-side timestamps, which is the value the serializer now falls back to.

2. ``updated_time`` was days ahead of ``user_updated_time`` (13 notes, 5
   resources, 1 folder — up to 76 days). Joplin's conflict branch is
   ``if (remoteContent.updated_time > local.sync_time)`` and it then writes a
   conflict copy. A server timestamp in the future is therefore a conflict
   generator, not a cosmetic wart. ``_ingest_notetag()`` was the source: it
   wrote ``{'tag_ids': ...}`` on every re-sent relation and the note's
   ``write()`` treated that as an edit. That is fixed in code; this migration
   collapses the damage already recorded, pulling ``updated_time`` back to the
   client's own ``user_updated_time`` where the server invented the later one.

Guarded so it is a no-op on re-run: each step only touches rows that still
have the defect.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODELS = ('joplin.note', 'joplin.folder', 'joplin.tag', 'joplin.resource')


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    filled = 0
    for model_name in MODELS:
        # Step 1: never serve an empty timestamp. Mirror the serializer's
        # fallback into the column so the API and the database agree.
        cr.execute(
            """
            UPDATE %(table)s
               SET user_created_time = created_time
             WHERE user_created_time IS NULL
               AND created_time IS NOT NULL
            """ % {'table': env[model_name]._table}
        )
        filled += cr.rowcount
        cr.execute(
            """
            UPDATE %(table)s
               SET user_updated_time = updated_time
             WHERE user_updated_time IS NULL
               AND updated_time IS NOT NULL
            """ % {'table': env[model_name]._table}
        )
        filled += cr.rowcount

    # Step 2: undo the invented future timestamps. Only rows where the server
    # moved updated_time PAST the client's own value are touched; a genuine
    # client edit keeps updated_time == user_updated_time and is left alone.
    rewound = 0
    for model_name in MODELS:
        cr.execute(
            """
            UPDATE %(table)s
               SET updated_time = user_updated_time
             WHERE user_updated_time IS NOT NULL
               AND updated_time > user_updated_time + interval '2 seconds'
            """ % {'table': env[model_name]._table}
        )
        rewound += cr.rowcount

    # Revisions minted by a note/tag relation are not document versions. They
    # carry an empty title AND body diff (no text changed) — drop exactly the
    # ones that recorded nothing.
    cr.execute(
        """
        DELETE FROM joplin_revision
         WHERE COALESCE(title_diff, '') = ''
           AND COALESCE(body_diff, '') = ''
        """
    )
    stale_revisions = cr.rowcount

    _logger.info(
        "[knowledge_joplin] 18.0.1.1.2: back-filled %s user_* timestamps, "
        "rewound %s invented updated_time values, removed %s empty revisions",
        filled, rewound, stale_revisions,
    )
