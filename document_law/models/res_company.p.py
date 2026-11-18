import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class Company(models.Model):
    _inherit = 'res.company'
    _description = 'Adds a RSS URL field to the res.company model'

    law_rss_url = fields.Char(string="RSS_URL", default="https://data.riksdagen.se/dokumentlista/?doktyp=sfs&dokstat=g%C3%A4llande sfs&del=global&utformat=rss&sort=datum&sortorder=desc")
