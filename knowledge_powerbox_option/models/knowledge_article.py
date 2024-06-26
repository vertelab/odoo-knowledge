# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast
import json

from collections import defaultdict
from datetime import datetime, timedelta
from markupsafe import Markup
from werkzeug.urls import url_join

from odoo import api, Command, fields, models, _
from odoo.addons.web.controllers.utils import clean_action
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.osv import expression
from odoo.tools import get_lang


class Article(models.Model):
    _inherit = "document.page"

    def render_embedded_view(self, act_window_id_or_xml_id, view_type, name, context=None):
        """
        Returns the HTML tag that will be recognized by the editor as an embedded view.
        :param int | str act_window_id_or_xml_id: id or xml id of the action
        :param str view_type: type of the view ('kanban', 'list', ...)
        :param str name: display name
        :param dict context: context of the view

        :return: rendered template for embedded views
        """
        self.ensure_one()
        action_data = self._extract_act_window_data(act_window_id_or_xml_id, name)
        print("action_data", action_data)
        return self.env['ir.qweb']._render(
            'knowledge_powerbox_option.knowledge_embedded_view', {
                'behavior_props': json.dumps({
                    'act_window': action_data,
                    'context': context or {},
                    'view_type': view_type,
                }),
            },
            minimal_qcontext=True,
            raise_if_not_found=False
        )

    def _extract_act_window_data(self, act_window_id_or_xml_id, name):
        """
        Returns a dictionary containing a copy of the attributes of the action
        window identified by the given id or xml id.
        :param int | str act_window_id_or_xml_id: id or xml id of the action
        :param str name: display name
        :return dict:
        """
        self.ensure_one()
        act_window = self.env.ref(act_window_id_or_xml_id) if isinstance(act_window_id_or_xml_id, str) else \
            self.env['ir.actions.act_window'].browse(act_window_id_or_xml_id)
        if act_window._name != 'ir.actions.act_window':
            raise ValidationError(_('Error: The given action is not an act_window. This action can not be used to '
                                    'create an embedded view or a view link'))

        action = act_window.sudo().read()[0]
        action_data = clean_action(action, self.env)
        # from this point on, the act_window is considered apart from the original record
        del action_data['id']
        del action_data['xml_id']
        action_data['display_name'] = name or action_data['display_name']
        action_data['name'] = name or action_data['name']
        return action_data


