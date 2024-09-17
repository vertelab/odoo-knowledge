from odoo import models, fields, api

class DocumentCSRD(models.Model):
    _name = 'document.csrd'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'scaffold_test.scaffold_test'

    name = fields.Char(compute='_compute_name')
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="If set, page is accessible only from this company",
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )

    creation_date = fields.Date(
        string="Date",
        index=True,
        readonly=True,
        default=fields.Date.today()
    )

    active = fields.Boolean(default=True)

    csrd_sheet_name = fields.Selection(
        string="CSRD Category", 
        selection=[
            ('ESRS 2','ESRS 2'),
            ('ESRS 2 MDR','ESRS 2 MDR'),
            ('ESRS E1','ESRS E1'),
            ('ESRS E2','ESRS E2'),
            ('ESRS E3','ESRS E3'),
            ('ESRS E4','ESRS E4'),
            ('ESRS E5','ESRS E5'),
            ('ESRS S1','ESRS S1'),
            ('ESRS S2','ESRS S2'),
            ('ESRS S3','ESRS S3'),
            ('ESRS S4','ESRS S4'),
            ('ESRS G1','ESRS G1')
            ], 
        default=None )

    csrd_id = fields.Char(string="CSRD ID")
    csrd_esrs = fields.Char(string="CSRD ESRS")
    csrd_dr = fields.Char(string="CSRD DR")
    csrd_paragraph = fields.Char(string="CSRD Paragraph")
    csrd_related_ar = fields.Char(string="CSRD Related_AR")
    csrd_name = fields.Char(string="CSRD Name")
    csrd_data_type = fields.Char(string="CSRD Data Type")
    csrd_conditional_or_alternative_dp = fields.Char(string="CSRD Conditional or Alternative DP")
    csrd_may_v = fields.Char(string="CSRD May V")
    csrd_appendix_b = fields.Char(string="CSRD Appendix B")
    csrd_appendix_c_less_then_750 = fields.Char(string="CSRD Appendix C < 750")
    csrd_appendix_c_more_then_750 = fields.Char(string="CSRD Appendix C > 750")

    @api.depends("csrd_name")
    def _compute_name(self):

        for rec in self:

            if rec.csrd_name:
                rec.name = rec.csrd_name
