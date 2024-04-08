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
    'name': 'Knowledge Forum Website',
    'version': '16.0.0.0',
    'summary': 'Knowledge Forum Website',
    'category': 'Knowledge',
    'description': """ """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/',
    'license': 'AGPL-3',
    'depends': ['website_forum', 'document_knowledge', 'document_page'],
    'data': [
        'security/document_knowledge_security.xml',
        'views/website_forum.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
}
