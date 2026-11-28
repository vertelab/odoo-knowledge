import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LawImportWizard(models.TransientModel):
    _name = "document.law.import.wizard"
    _description = "Import laws from Riksdagen by SFS designation"

    mode = fields.Selection(
        selection=[
            ("designation", "By SFS designation"),
            ("incremental", "Incremental refresh (what is new or amended)"),
            ("backfill", "Full backfill (whole catalogue)"),
        ],
        string="Mode",
        default="designation",
        required=True,
    )
    beteckningar = fields.Text(
        string="SFS designations",
        help="One per line, e.g. 2006:804. Only used in the designation mode.",
    )
    refresh = fields.Boolean(
        string="Overwrite existing",
        default=False,
        help="Also rewrite laws that are already imported.",
    )
    max_pages = fields.Integer(
        string="Max pages",
        default=5,
        help="100 laws per page. The whole catalogue is about 57 pages.",
    )
    result = fields.Text(string="Result", readonly=True)

    def action_run(self):
        self.ensure_one()
        law = self.env["document.law"]
        lines = []

        if self.mode == "designation":
            designations = [
                row.strip()
                for row in (self.beteckningar or "").splitlines()
                if row.strip()
            ]
            if not designations:
                raise UserError("Ange minst en SFS-beteckning, t.ex. 2006:804.")
            summary = law.import_law_by_designations(
                designations, refresh=self.refresh
            )
            lines.append(
                "Skapade: %(created)s, uppdaterade: %(updated)s, "
                "oförändrade: %(skipped)s" % summary
            )
            if summary["failed"]:
                lines.append("Misslyckades: " + ", ".join(summary["failed"]))

        elif self.mode == "incremental":
            before = law.search_count([])
            law._create_law_record_cron()
            after = law.search_count([])
            lines.append("Nya lagar: %s" % (after - before))
            lines.append("Totalt i databasen: %s" % after)

        else:  # backfill
            result = law._backfill_law_records(
                max_pages=self.max_pages, create=True
            )
            lines.append(
                "Lagar i katalogen (denna körning): %(found)s\n"
                "Saknades: %(missing)s\n"
                "Skapade: %(created)s\n"
                "Sidor lästa: %(pages)s" % result
            )

        self.result = "\n".join(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
