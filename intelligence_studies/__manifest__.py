# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2025  Vertel AB  info@vertel.se
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
# https://www.odoo.com/documentation/18.0/reference/module.html
#

{
    'name': "Knowledge: Intelligence Studies",
    'version': '1.0',
    'author': "Vertel AB",
    'category': 'Tools',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/intelligence_studies',
    'images': ['static/description/banner.png'], # 560x280
    'license': 'AGPL-3',

    'description': """
        Intelligence Studies offers a structured and automated approach to collecting, 
        analyzing, and reporting critical information that supports strategic decision-making. 
        
        By leveraging specialized AI agents, it continuously monitors external macro trends 
        through PESTLE analysis, examines market dynamics and competitive forces using Porter’s 
        Five Forces, and evaluates internal strengths, weaknesses, opportunities, and 
        threats via SWOT analysis. 
        
        This comprehensive process delivers regular, data-driven 
        insights that reduce manual effort while providing a dynamic and up-to-date overview 
        of both the external environment and the organization’s internal strategic position. 
        
        The result is a powerful tool for proactive planning and informed decision-making 
        based on relevant and timely intelligence.
        """,
    'depends': ['ai_agent','project_task_swot','document_page'],
    'data': [
        'data/quest_module_opportunities.xml', 
        'data/quest_module_ekonomiska_trender.xml', 
        'data/quest_module_invarldsbevakning_swot_analys.xml', 
        'data/quest_module_juridiska_trender.xml', 
        'data/quest_module_konkurrenskraftsuppdrag.xml', 
        'data/quest_module_miljomassiga_trender.xml', 
        'data/quest_module_narvarldsbevakning.xml', 
        'data/quest_module_nulagesbeskrivning_swot_analys.xml', 
        'data/quest_module_ny_aktorkraftsuppdrag.xml', 
        'data/quest_module_omvarldsbevakning_av_aktuella trender.xml',
        'data/quest_module_politiska_trender.xml', 
        'data/quest_module_sociala_trender.xml', 
        'data/quest_module_strenghts.xml', 
        'data/quest_module_tekniska_teknologiska_trender.xml', 
        'data/quest_module_threats.xml', 
        'data/quest_module_weakness.xml'
        ],
    'installable': True,
    'application': False,
}
