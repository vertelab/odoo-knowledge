import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class KnowledgePageController(http.Controller):

    @http.route(['/knowledge/page/<int:manual_id_id>'], type='http', auth="public", website=True)
    def manual_page(self, manual_id_id, **kw):
        _logger.info(f"Accessing manual page for ID: {manual_id_id}")
        try:
            manual_id = request.env['document.page'].sudo().browse(manual_id_id)
            if not manual_id.exists():
                _logger.warning(f"Equipment with ID {manual_id} not found")
                return request.render("document_publish.page_not_found")
            
            _logger.debug(f"Manual found: {manual_id.name}")
                        
            return request.render("document_publish.manual_page", {
                'name': manual_id.name,
                'content': manual_id.content,
                'draft_name': manual_id.draft_name,
                'draft_summary': manual_id.draft_summary,
                'content_uid': manual_id.content_uid.name,
                'content_date': manual_id.content_date,
            })
        except Exception as e:
            _logger.error(f"Error occurred while rendering knowledge page: {str(e)}")
            return request.render("document_publish.page_not_found")