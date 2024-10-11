from odoo import models, fields, api

class DocumentCSRD(models.Model):
    _name = 'document.page.csrd'
    _description = 'Glue model between document.page and document.csrd'

    document_csrd_id = fields.Many2one(comodel_name="document.csrd")
    document_page_id = fields.Many2one(comodel_name="document.page")
