import werkzeug

from odoo import http, tools, _
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.osv import expression


class KnowledgeDocumentController(http.Controller):

    @http.route('/document/article/<int:article_id>', type='http', auth='user')
    def redirect_to_document(self, article_id):
        """ This route will redirect internal users to the backend view of the
        article and the share users to the frontend view instead."""
        article = request.env['document.page'].search([('id', '=', article_id)])
        if request.env.user.has_group('base.group_user'):
            if not article:
                return werkzeug.exceptions.Forbidden()
            return self._redirect_to_backend_view(article)
        # return self._redirect_to_portal_view(article)
        return

    def _redirect_to_backend_view(self, article):
        return request.redirect("/web#id=%s&model=document.page&action=%s&menu_id=%s" % (
            article.id if article else '',
            request.env.ref("knowledge_powerbox_option.document_knowledge_article_action_form").id,
            request.env.ref('document_knowledge.menu_document_root').id
        ))
