# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2023 Vertel AB (<robin.calvin@vertel.se>)
#    All Rights Reserved
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
#
# https://www.odoo.com/documentation/16.0/reference/module.html
#
{
    'name': 'Knowledge Powerbox Option',
    'version': '0.0',
    'summary': 'Knowledge Powerbox Option',
    'category': 'Knowledge',
    'description': """
    Knowledge Powerbox Option
    """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/knowledge_powerbox_option',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-knowledge',
    # Any module necessary for this one to work correctly
    
    'depends': ['document_knowledge', 'document_page', 'web_editor'],
    'data': [
        'views/document_article_views.xml',
        'data/behaviors_templates.xml',
        'data/ir_actions_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'knowledge_powerbox_option/static/src/components/**/*.js',
            'knowledge_powerbox_option/static/src/components/**/*.xml',

            'knowledge_powerbox_option/static/src/scss/knowledge_blocks.scss',
            'knowledge_powerbox_option/static/src/js/knowledge_plugin.js',
        ],
        'web_editor.assets_wysiwyg': [
            'knowledge_powerbox_option/static/src/js/wysiwyg/*.js',
            'knowledge_powerbox_option/static/src/js/wysiwyg.js',
            'knowledge_powerbox_option/static/src/xml/knowledge_editor.xml',
        ],
        'web.assets_common': [
            'knowledge_powerbox_option/static/src/js/tools/knowledge_tools.js',
        ],
    },
    'application': True,
    'installable': True,
}
