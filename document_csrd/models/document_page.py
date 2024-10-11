from odoo import models, fields, api

class DocumentCSRD(models.Model):
    _inherit = 'document.page'
    _description = 'Addeds a One2many filed connected to the glue model document.page.csrd'

    document_csrd_ids = fields.One2many(comodel_name="document.page.csrd", inverse_name="document_page_id")

    
