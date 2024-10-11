from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)

class DocumentESGCategory(models.Model):
    _name = 'document.esg.category'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Creates ESRS datapoints'

    name = fields.Char()
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one(comodel_name='document.esg.category', string='Parent Category', index=True)
    csrd_ids = fields.One2many(comodel_name="document.csrd", inverse_name="category_id")
    
    impact_materiality_description = fields.Text(string="Impact Materiality Description")
    financial_materiality_description = fields.Text(string="Financial Materiality Description")

    impact_materiality = fields.Selection([
            ('1','1'), 
            ('2','2'),
            ('3','3'),
            ('4','4'),
            ('5','5'),
            ('6','6'),
            ('7','7'),
            ('8','8'),
            ('9','9'),
            ('10','10'),
            ], 
            string="Impact Materiality",
            default=None,
            group_operator="max"
            )

    financial_materiality = fields.Selection([
            ('1','1'), 
            ('2','2'),
            ('3','3'),
            ('4','4'),
            ('5','5'),
            ('6','6'),
            ('7','7'),
            ('8','8'),
            ('9','9'),
            ('10','10'),
            ], 
            string="Financial Materiality",
            default=None,
            group_operator="max"
            )


    impact_materiality_value = fields.Integer(compute="compute_materiality_value", store=True)
    financial_materiality_value = fields.Integer(compute="compute_materiality_value", store=True)

    @api.depends("impact_materiality", "financial_materiality")
    def compute_materiality_value(self):

        for rec in self:

            rec.impact_materiality_value = int(rec.impact_materiality)
            rec.financial_materiality_value = int(rec.financial_materiality)
            



    def set_materiality_downward(self):

        children = self.search([("parent_id", "child_of", self.id)])

        for child in children:
            
            if child.id != self.id:

                _logger.error(f"{child.name=}"*50)

                child.impact_materiality = child.parent_id.impact_materiality
                child.financial_materiality = child.parent_id.financial_materiality   


    def set_materiality_upward(self):

        parents = self.search([("id", "parent_of", self.id)])

        for parent in parents:

            _logger.error(f"{parent.name=}"*50)

            parent.parent_id.impact_materiality = parent.impact_materiality
            parent.parent_id.financial_materiality = parent.financial_materiality