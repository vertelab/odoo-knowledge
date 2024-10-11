from odoo import models, fields, api

class DocumentCSRD(models.Model):
    _name = 'document.csrd'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Creates ESRS datapoints'

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

    survey_id = fields.Many2one(comodel_name='survey.survey')

    active = fields.Boolean(default=True)

    document_page_manual_ids = fields.One2many(comodel_name="document.page.csrd", inverse_name="document_csrd_id")

    currency_id = fields.Many2one('res.currency', string="Currency",
                                 related='company_id.currency_id')

    stage = fields.Selection(selection=[
       ('draft', 'Draft'),
       ('done', 'Done'),
   ], string='Status', required=True, copy=False,
   tracking=True, default='draft')

    implementation_narrative = fields.Text(string="Implementation Text")
    implementation_monetary = fields.Monetary(string="Monetary Value")
    implementation_decimal = fields.Float(string="Decimal Value")
    implementation_integer = fields.Integer(string="Integer Value")
    implementation_percent = fields.Float(string="Percentage")  
    implementation_date = fields.Date(string="Date")

    category_id = fields.Many2one(comodel_name="document.esg.category", string="ESG Category", compute="_compute_category_id", store=True)

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
    csrd_name = fields.Char(string="CSRD Name", translate=True)
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

    @api.depends("csrd_sheet_name")
    def _compute_category_id(self):

        for rec in self:

            category_id = self.env["document.esg.category"].search([("name", '=', rec.csrd_sheet_name)])

            if category_id:

                rec.category_id = category_id
