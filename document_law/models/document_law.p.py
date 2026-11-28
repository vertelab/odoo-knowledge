import requests
import rss_parser
import xmltodict
import logging
import re
import time

_logger = logging.getLogger(__name__)

# Riksdagen open data. The RSS feed only ever carries the 20 most recently
# published SFS documents, so a daily cron that reads the feed and nothing else
# will never pick up a law that was published on a day the cron did not run.
# The documentlist API is paged (sz/p) and can therefore be walked in full.
RIKSDAGEN_API = "https://data.riksdagen.se/dokumentlista/"
RIKSDAGEN_DOC = "https://data.riksdagen.se/dokument/"


def _sfs_to_doc_id(beteckning):
    """'2006:804' -> 'sfs-2006-804'. Riksdagen keeps the number unpadded."""
    year, _, number = (beteckning or "").strip().partition(":")
    if not year.isdigit() or not number.isdigit():
        return False
    return f"sfs-{year}-{number}"


def _doc_id_to_sfs(doc_id):
    """'sfs-2006-804' -> '2006:804'."""
    match = re.match(r"^sfs-(\d{4})-(\d+)$", doc_id or "")
    if not match:
        return False
    return f"{match.group(1)}:{match.group(2)}"

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class DocumentLaw(models.Model):
    _name = 'document.law'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Gets the latest laws and changes from a RSS URL'
    _rec_name = "rss_titel"

    creation_date = fields.Date(
        string="Date",
        index=True,
        readonly=True,
        default=fields.Date.today()
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="If set, page is accessible only from this company",
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
 
    active = fields.Boolean(default=True)
    stage = fields.Selection(selection=[
       ('cancel', 'Cancelled'),
       ('draft', 'Draft'),
       ('in_progress', 'In Progress'),
       ('done', 'Done'),
   ], string='Status', required=True, copy=False,
   tracking=True, default='draft')

    rss_hangar_id = fields.Char(string="Hangar ID")
    rss_dok_id = fields.Char(string="Law Document ID")
    rss_rm = fields.Char(string="Reform Year")
    rss_beteckning = fields.Char(string="Designation")
    rss_typ = fields.Char(string="Type")
    rss_subtyp = fields.Char(string="Subtype")
    rss_tempbeteckning = fields.Char(string="Temporary Designation")
    rss_organ = fields.Char(string="Departement")
    rss_nummer = fields.Integer(string="Number")
    rss_slutnummer = fields.Integer(string="End Number")
    rss_datum = fields.Date(string="Date")
    rss_publicerad = fields.Datetime(string="Published")
    rss_systemdatum = fields.Datetime(string="System Date")
    rss_titel = fields.Char(string="Title")
    rss_subtitel = fields.Char(string="Subtitle")
    rss_status = fields.Char(string="Status")
    rss_text = fields.Text(string="Text")
    rss_html = fields.Html(string="HTML", readonly=True)
    rss_dokumentnamn = fields.Char(string="Document Name")
    rss_avdelningar = fields.Char(string="Departments")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _law_values_from_xml(self, xml_text):
        """Turn one Riksdagen document XML into a dict of document.law values.

        Returns False when the payload is not a law document. Every key the
        model actually has is set, so a missing element in the payload simply
        leaves the field unset instead of raising.
        """
        try:
            payload = xmltodict.parse(xml_text)
            source = payload["dokumentstatus"]["dokument"]
        except Exception as error:  # noqa: BLE001 - third-party payloads vary
            _logger.warning("document_law: could not parse document XML: %s", error)
            return False

        if not isinstance(source, dict) or not source.get("dok_id"):
            return False

        values = {}
        for key, raw in source.items():
            field_name = f"rss_{key}"
            if field_name not in self._fields:
                continue
            field_type = self._fields[field_name].type
            if raw is None or raw == "":
                continue
            try:
                if field_type in ("integer", "float"):
                    values[field_name] = int(raw)
                elif field_type == "date":
                    values[field_name] = fields.Date.to_date(raw)
                elif field_type == "datetime":
                    values[field_name] = fields.Datetime.to_datetime(raw)
                elif field_name == "rss_avdelningar":
                    # {"avdelning": "X"} or {"avdelning": ["X", "Y"]}
                    depts = raw.get("avdelning") if isinstance(raw, dict) else raw
                    if isinstance(depts, list):
                        values[field_name] = ", ".join(str(d) for d in depts)
                    else:
                        values[field_name] = str(depts) if depts else False
                else:
                    values[field_name] = str(raw)
            except (ValueError, TypeError) as error:
                _logger.warning(
                    "document_law: bad value for %s (%r): %s", field_name, raw, error
                )
        return values

    def _fetch_law_xml(self, doc_id, timeout=30):
        """Fetch the XML for one sfs-<year>-<number> document id."""
        try:
            response = requests.get(f"{RIKSDAGEN_DOC}{doc_id}.xml", timeout=timeout)
            if response.status_code != 200 or not response.text.strip():
                _logger.warning(
                    "document_law: no XML for %s (HTTP %s)", doc_id, response.status_code
                )
                return False
            return response.text
        except requests.RequestException as error:
            _logger.warning("document_law: fetch failed for %s: %s", doc_id, error)
            return False

    @api.model
    def _law_context(self, company):
        """Collect the company + optional run markers from the context."""
        return {
            "company": company,
            "force": bool(self.env.context.get("law_force_refresh")),
            "report": self.env.context.get("law_import_report") is not None,
            "max_new": self.env.context.get("law_max_new"),
            "sleep": float(self.env.context.get("law_sleep", 0.2)),
        }

    @api.model
    def _upsert_law(self, doc_id, values, company, force=False):
        """Create or update the record for one law document.

        Returns "created", "updated", "skipped" or False when the payload
        could not be parsed. The update path is what keeps a law current
        after it has been imported: Riksdagen republishes the whole document
        whenever an amending act touches it, and the new subtitel
        ("t.o.m. SFS ...") plus the new text is the signal that it changed.
        """
        if not values or not values.get("rss_dok_id"):
            return False

        existing = self.search(
            [("company_id", "=", company.id), ("rss_dok_id", "=", doc_id)],
            limit=1,
        )
        if existing:
            if force or existing.rss_subtitel != values.get("rss_subtitel"):
                existing.write(values)
                return "updated"
            return "skipped"

        values = dict(values, company_id=company.id)
        self.create(values)
        return "created"

    def _import_report_guard(self):
        """Cap the number of newly created records in a discovery run."""
        max_new = self.env.context.get("law_max_new")
        if not max_new:
            return True
        created = self.env.context.get("law_import_created", 0)
        return created < int(max_new)

    # ------------------------------------------------------------------
    # Import entry points
    # ------------------------------------------------------------------

    def import_law_by_designation(self, beteckning, refresh=False):
        """Import or refresh one law by SFS designation, e.g. "2006:804".

        Meant for laws you actually care about. Discovery (the daily cron)
        can only ever see what Riksdagen published recently; this is how a
        branch-specific act (alkohollagen, livsmedelslagen, LSO, ...) is
        brought in on demand.
        """
        doc_id = _sfs_to_doc_id(beteckning)
        if not doc_id:
            raise UserError(
                f"Ogiltig SFS-beteckning: {beteckning!r}. Väntat format: ÅÅÅÅ:NNN."
            )
        xml_text = self._fetch_law_xml(doc_id)
        values = self._law_values_from_xml(xml_text) if xml_text else False
        if not values:
            raise UserError(
                f"Kunde inte hämta {beteckning} ({doc_id}) från Riksdagen."
            )
        result = self._upsert_law(
            doc_id, values, self.env.company, force=refresh
        )
        _logger.info("document_law: %s -> %s", beteckning, result)
        return result

    @api.model
    def import_law_by_designations(self, beteckningar, refresh=False):
        """Batch variant of import_law_by_designation. Returns a summary dict."""
        summary = {"created": 0, "updated": 0, "skipped": 0, "failed": []}
        for beteckning in beteckningar:
            doc_id = _sfs_to_doc_id(beteckning)
            if not doc_id:
                summary["failed"].append(beteckning)
                continue
            xml_text = self._fetch_law_xml(doc_id)
            values = self._law_values_from_xml(xml_text) if xml_text else False
            if not values:
                summary["failed"].append(beteckning)
                continue
            result = self._upsert_law(
                doc_id, values, self.env.company, force=refresh
            )
            if result in summary:
                summary[result] += 1
            else:
                summary["failed"].append(beteckning)
            time.sleep(self.env.context.get("law_sleep", 0.2))
        return summary

    def _create_law_record_cron(self):
        """Daily incremental refresh.

        Walks the Riksdagen documentlist newest-first and stops as soon as a
        whole page is already known, so a normal day costs 1-2 requests. Any
        known law whose subtitel changed is updated in place (see
        _upsert_law), which is how amendments reach already imported acts.
        """
        max_pages = int(self.env.context.get("law_max_pages", 50))
        companies = self.env["res.company"].search([("law_rss_url", "!=", False)])

        for company in companies:
            page = 1
            new_this_page = 0
            seen_docs = set()
            stop = False

            while page <= max_pages and not stop:
                params = {
                    "doktyp": "sfs",
                    "dokstat": "gällande sfs",
                    "utformat": "json",
                    "sz": 100,
                    "p": page,
                    "sort": "datum",
                    "sortorder": "desc",
                }
                try:
                    response = requests.get(
                        RIKSDAGEN_API, params=params, timeout=30
                    )
                    payload = response.json()
                except (requests.RequestException, ValueError) as error:
                    _logger.warning(
                        "document_law: page %s failed for %s: %s",
                        page, company.display_name, error,
                    )
                    break

                container = payload.get("dokumentlista") or {}
                docs = container.get("dokument") or []
                if isinstance(docs, dict):
                    docs = [docs]
                if not docs:
                    break

                for doc in docs:
                    doc_id = doc.get("dok_id")
                    if not doc_id or doc_id in seen_docs:
                        continue
                    seen_docs.add(doc_id)

                    known = self.search_count(
                        [("company_id", "=", company.id), ("rss_dok_id", "=", doc_id)]
                    )
                    if known:
                        new_this_page += 0
                    else:
                        new_this_page += 1

                    # Only fetch XML for unknown, or for known-but-newly-
                    # published (subtitle is the version marker).
                    needs_fetch = not known
                    if not needs_fetch:
                        record = self.search(
                            [("company_id", "=", company.id),
                             ("rss_dok_id", "=", doc_id)], limit=1)
                        if record and doc.get("titel") and record.rss_titel != doc.get("titel"):
                            needs_fetch = True
                    if not needs_fetch:
                        continue

                    xml_text = self._fetch_law_xml(doc_id)
                    values = self._law_values_from_xml(xml_text) if xml_text else False
                    self._upsert_law(doc_id, values, company)
                    time.sleep(self.env.context.get("law_sleep", 0.2))

                # A full page with nothing unknown means we have caught up
                # with what the feed would have shown us and beyond.
                if new_this_page == 0:
                    stop = True

                page += 1

            _logger.info(
                "document_law: incremental refresh done for %s (%s pages)",
                company.display_name, page - 1,
            )

    def action_import_law(self):
        """Refresh the selected laws from Riksdagen."""
        for record in self:
            if not record.rss_beteckning:
                continue
            record.import_law_by_designation(record.rss_beteckning, refresh=True)
        return True


    def _backfill_law_records(self, max_pages=60, create=True):
        """One-shot backfill of the whole "gällande sfs" catalogue.

        The RSS window this module was built around holds 20 documents. The
        catalogue holds ~5 700. Running this once brings in everything that
        existed before, after which the daily cron keeps it current. Keep
        create=False to only report what is missing.
        """
        company = self.env.company
        found = missing = created = 0
        skipped = []
        page = 1

        while page <= max_pages:
            params = {
                "doktyp": "sfs",
                "dokstat": "gällande sfs",
                "utformat": "json",
                "sz": 100,
                "p": page,
                "sort": "datum",
                "sortorder": "desc",
            }
            try:
                payload = requests.get(RIKSDAGEN_API, params=params, timeout=30).json()
            except (requests.RequestException, ValueError) as error:
                _logger.warning("document_law backfill page %s: %s", page, error)
                break

            docs = (payload.get("dokumentlista") or {}).get("dokument") or []
            if isinstance(docs, dict):
                docs = [docs]
            if not docs:
                break

            for doc in docs:
                doc_id = doc.get("dok_id")
                if not doc_id:
                    continue
                found += 1
                if self.search_count(
                    [("company_id", "=", company.id), ("rss_dok_id", "=", doc_id)]
                ):
                    continue
                missing += 1
                if not create:
                    skipped.append(_doc_id_to_sfs(doc_id) or doc_id)
                    continue
                xml_text = self._fetch_law_xml(doc_id)
                values = self._law_values_from_xml(xml_text) if xml_text else False
                if values and self._upsert_law(doc_id, values, company) == "created":
                    created += 1
                time.sleep(self.env.context.get("law_sleep", 0.2))

            page += 1

        result = {
            "found": found,
            "missing": missing,
            "created": created,
            "pages": page - 1,
        }
        _logger.info("document_law: backfill %s", result)
        return result

    def set_stage_to_in_progres(self):

        companies = self.env['res.company'].search([])

        for company in companies:

            if self.env.user.company_id.id == company.id:

                self.stage = "in_progress"


    def set_stage_to_cancel(self):

        companies = self.env['res.company'].search([])

        for company in companies:

            if self.env.user.company_id.id == company.id:

                self.stage = "cancel"


    def set_stage_to_draft(self):

        companies = self.env['res.company'].search([])

        for company in companies:

            if self.env.user.company_id.id == company.id:

                self.stage = "draft"
    
    def set_stage_to_done(self):

        companies = self.env['res.company'].search([])

        for company in companies:

            if self.env.user.company_id.id == company.id:

                self.stage = "done"

