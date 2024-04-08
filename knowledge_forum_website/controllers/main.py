# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json
import lxml
import requests
import logging
import werkzeug.exceptions
import werkzeug.urls
import werkzeug.wrappers

from datetime import datetime

from odoo import http, tools, _
from odoo.exceptions import AccessError
from odoo.addons.http_routing.models.ir_http import slug
from odoo.addons.website.models.ir_http import sitemap_qs2dom
from odoo.addons.website_profile.controllers.main import WebsiteProfile
from odoo.addons.portal.controllers.portal import _build_url_w_params
from odoo.addons.website_forum.controllers.main import WebsiteForum

from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class WebsiteForumExtended(WebsiteForum):

    @http.route(['/forum/<model("forum.forum"):forum>',
                 '/forum/<model("forum.forum"):forum>/page/<int:page>',
                 '''/forum/<model("forum.forum"):forum>/tag/<model("forum.tag"):tag>/questions''',
                 '''/forum/<model("forum.forum"):forum>/tag/<model("forum.tag"):tag>/questions/page/<int:page>''',
                 ], type='http', auth="public", website=True, sitemap=WebsiteForum.sitemap_forum)
    def questions(self, forum, tag=None, page=1, filters='all', my=None, sorting=None, search='', **post):
        Post = request.env['forum.post']

        if sorting:
            # check that sorting is valid
            # retro-compatibily for V8 and google links
            try:
                sorting = werkzeug.urls.url_unquote_plus(sorting)
                Post._generate_order_by(sorting, None)
            except (UserError, ValueError):
                sorting = False

        if not sorting:
            sorting = forum.default_order

        options = {
            'displayDescription': False,
            'displayDetail': False,
            'displayExtraDetail': False,
            'displayExtraLink': False,
            'displayImage': False,
            'allowFuzzy': not post.get('noFuzzy'),
            'forum': str(forum.id) if forum else None,
            'tag': str(tag.id) if tag else None,
            'filters': filters,
            'my': my,
        }
        question_count, details, fuzzy_search_term = request.website._search_with_fuzzy("forum_posts_only", search,
                                                                                        limit=page * self._post_per_page,
                                                                                        order=sorting, options=options)
        question_ids = details[0].get('results', Post)
        question_ids = question_ids[(page - 1) * self._post_per_page:page * self._post_per_page]

        if tag:
            url = "/forum/%s/tag/%s/questions" % (slug(forum), slug(tag))
        else:
            url = "/forum/%s" % slug(forum)

        url_args = {
            'sorting': sorting
        }
        if search:
            url_args['search'] = search
        if filters:
            url_args['filters'] = filters
        if my:
            url_args['my'] = my
        pager = tools.lazy(lambda: request.website.pager(url=url, total=question_count, page=page,
                                                         step=self._post_per_page, scope=self._post_per_page,
                                                         url_args=url_args))

        values = self._prepare_user_values(forum=forum, searches=post, header={'ask_hide': not forum.active})
        knowledge_ids = False
        if search:
            knowledge_ids = self._forum_knowledge_search(search, options)

        values.update({
            'main_object': tag or forum,
            'edit_in_backend': True,
            'question_ids': question_ids,
            'question_count': question_count,
            'search_count': question_count,
            'pager': pager,
            'tag': tag,
            'filters': filters,
            'my': my,
            'sorting': sorting,
            'search': fuzzy_search_term or search,
            'original_search': fuzzy_search_term and search,
            'knowledge_ids': knowledge_ids
        })
        return request.render("website_forum.forum_index", values)

    def _forum_knowledge_search(self, search, options):
        knowledge_ids = request.env['document.page'].search([('name', 'ilike', search)], order="id asc")
        return knowledge_ids

    @http.route(['/knowledge/<model("document.page"):document>',
                 '/forum/<model("document.page"):document>/page/<int:page>',
                 ], type='http', auth="public", website=True, sitemap=WebsiteForum.sitemap_forum)
    def knowledge(self, document=None, page=1, filters='all', search='', **post):
        values = {
            'document': document
        }

        return request.render("knowledge_forum_website.knowledge_post", values)
