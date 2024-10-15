import requests
import rss_parser
import xmltodict
import logging

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class DocumentLaw(models.Model):
    _name = 'document.law'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Gets the latest laws and changes from a RSS URL'

    name = fields.Char(string="Name", compute='_compute_name')
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

    def _create_law_record_cron(self):

        companies = self.env['res.company'].search([])

        for company in companies:
            
            if company.law_rss_url:

                url = company.law_rss_url
                response = requests.get(url)

                rss = rss_parser.RSSParser.parse(response.text)

                document_ids = self.search([('company_id','=',company.id),('rss_dok_id', '!=', False)])
                
                document_rss_dok_ids = [document.rss_dok_id for document in document_ids]

                links_to_xml = []
                xml_dicts = []
                record_dict = {'company_id': company.id}

                for item in rss.channel.items:

                    links_to_xml.append(item.guid.split("=",1)[0])

                for link in links_to_xml:

                    get_xml = requests.get(link)

                    xml_dicts.append(xmltodict.parse(get_xml.text))

                for xml_dict in xml_dicts:

                    xml_dict_values = xml_dict["dokumentstatus"]["dokument"]

                    xml_dict_key_values = map(lambda key: f"rss_{key}",xml_dict_values.keys())    

                    for rss_key, key in zip(xml_dict_key_values, xml_dict_values.keys()):
                        
                        if rss_key == "rss_nummer" or rss_key == "rss_slutnummer":
                            record_dict[rss_key] = int(xml_dict_values.get(key))

                        elif rss_key == "rss_datum":
                            record_dict[rss_key] = fields.Date.to_date(xml_dict_values.get(key))

                        elif rss_key == "rss_publicerad" or rss_key == "rss_systemdatum":
                            record_dict[rss_key] = fields.Datetime.to_datetime(xml_dict_values.get(key))
                            
                        elif rss_key == "rss_avdelningar":
                            record_dict[rss_key] = "".join(xml_dict_values.get(key).get("avdelning"))

                        else:
                            record_dict[rss_key] = xml_dict_values.get(key)

                    if record_dict.get("rss_dok_id") not in document_rss_dok_ids:

                        self.create(record_dict)

            else:

                raise UserError(f"The RSS URL is empty on company {company.display_name}")
    

    @api.depends("rss_titel")
    def _compute_name(self):

        for rec in self:

            if rec.rss_titel:
                rec.name = rec.rss_titel


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

