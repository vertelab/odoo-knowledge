from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    joplin_api_url = fields.Char(
        string='Joplin API Connection',
        compute='_compute_joplin_api_url',
        readonly=True,
    )
    joplin_instruction_html = fields.Html(
        string='Instructions',
        compute='_compute_joplin_instruction_html',
        readonly=True,
        sanitize=False,
    )

    @api.depends_context('uid')
    def _compute_joplin_api_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for user in self:
            user.joplin_api_url = f"{base_url}/joplin"

    @api.depends_context('uid')
    def _compute_joplin_instruction_html(self):
        for user in self:
            user.joplin_instruction_html = f'''
<div class="alert alert-info" role="alert">
    <h4>Connect Joplin to Odoo</h4>

    <h5>Step 1: Connect via desktop (Joplin Desktop)</h5>
    <ol>
        <li>Open Joplin &rarr; Tools &rarr; Settings &rarr; Synchronization</li>
        <li>Select sync target: <strong>"Joplin Server"</strong></li>
        <li>
            <strong>Joplin Server URL:</strong>
            <code style="display:block; margin:4px 0; padding:4px 8px; background:#f5f5f5; border-radius:3px;">{user.joplin_api_url}</code>
        </li>
        <li><strong>User ID:</strong> Your Odoo email address ({user.login})</li>
        <li><strong>Password:</strong> Your Odoo password</li>
        <li>Click "Check Synchronization Configuration" to verify</li>
    </ol>

    <h5>Step 2: Connect via mobile (Joplin Mobile)</h5>
    <ol>
        <li>Open Joplin &rarr; Settings &rarr; Synchronization</li>
        <li>Select sync target: <strong>"Joplin Server"</strong></li>
        <li>Enter the same URL, user ID, and password as above</li>
    </ol>
</div>'''
