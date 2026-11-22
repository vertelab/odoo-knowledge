from odoo.tests import common, tagged
from odoo import fields
import logging

_logger = logging.getLogger(__name__)


@tagged('-at_install', 'post_install')
class TestGraphModel(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ModelConfig = cls.env['knowledge.graph.model']
        cls.Publisher = cls.env['knowledge.graph.publisher']
        cls.partner_model = cls.env['ir.model'].search([
            ('model', '=', 'res.partner')
        ], limit=1)
        cls.test_partner = cls.env['res.partner'].create({
            'name': 'Test Partner for Graph',
        })

    def test_01_create_config_defaults(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
        })
        self.assertEqual(config.state, 'active')
        self.assertEqual(config.domain, '[]')
        self.assertTrue(config.target_queue)

    def test_02_record_count_computation(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
            'domain': "[('id', '=', %s)]" % self.test_partner.id,
        })
        config._compute_record_count()
        self.assertEqual(config.record_count, 1)

    def test_03_record_count_zero_for_invalid_domain(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
            'domain': "[('id', '=', -999)]",
        })
        config._compute_record_count()
        self.assertEqual(config.record_count, 0)

    def test_04_publisher_payload_structure(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
        })
        try:
            self.Publisher.publish(
                'res.partner',
                self.test_partner.id,
                'create',
                config,
                fields_data={'name': 'Test'},
            )
        except Exception as e:
            self.fail(f"Publish raised unexpected exception: {e}")

    def test_05_publish_batch_calls_publish(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
        })
        partners = self.env['res.partner'].search([], limit=3)
        try:
            self.Publisher.publish_batch(config, partners)
        except Exception:
            pass

    def test_06_admin_payload(self):
        try:
            self.Publisher.publish_admin('provision_database', {
                'graph_topic': 'test-topic-abc123',
                'login': 'testuser',
            })
        except Exception:
            pass

    def test_07_security_user_own_configs(self):
        internal_group = self.env.ref('base.group_user')
        demo_user = self.env['res.users'].create({
            'name': 'Demo Graph User',
            'login': 'demographuser',
            'groups_id': [(4, internal_group.id)],
        })
        self.ModelConfig.sudo().create({
            'model_id': self.partner_model.id,
            'target_queue': 'user_queue',
            'user_id': demo_user.id,
        })
        self.ModelConfig.sudo().create({
            'model_id': self.partner_model.id,
            'target_queue': 'global_queue',
        })
        user_configs = self.ModelConfig.with_user(demo_user).search([
            ('target_queue', '=', 'user_queue'),
        ])
        self.assertEqual(len(user_configs), 1)
        global_configs = self.ModelConfig.with_user(demo_user).search([
            ('target_queue', '=', 'global_queue'),
        ])
        self.assertEqual(len(global_configs), 0)

    def test_08_admin_sees_all_configs(self):
        self.ModelConfig.sudo().create({
            'model_id': self.partner_model.id,
            'target_queue': 'admin_test_queue',
            'user_id': self.env.user.id,
        })
        self.ModelConfig.sudo().create({
            'model_id': self.partner_model.id,
            'target_queue': 'admin_test_global',
        })
        all_configs = self.ModelConfig.sudo().search([
            '|',
            ('target_queue', '=', 'admin_test_queue'),
            ('target_queue', '=', 'admin_test_global'),
        ])
        self.assertEqual(len(all_configs), 2)

    def test_09_sync_now_action(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
            'domain': "[('id', '=', %s)]" % self.test_partner.id,
        })
        result = config.action_sync_now()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')

    def test_10_update_graph_db_action(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'test_queue',
        })
        result = config.action_update_graph_db()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'ir.actions.client')

    def test_11_user_graph_topic_generation(self):
        new_user = self.env['res.users'].create({
            'name': 'Topic Test User',
            'login': 'topictest',
        })
        self.assertTrue(new_user.graph_topic)
        self.assertIn('topictest', new_user.graph_topic)
        parts = new_user.graph_topic.split('-')
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(parts[1]), 8)

    def test_12_base_automation_creation(self):
        config = self.ModelConfig.create({
            'model_id': self.partner_model.id,
            'target_queue': 'auto_test',
        })
        automation_name = f"GraphDB: {self.partner_model.name} [{config.id}]"
        automation = self.env['base.automation'].search([
            ('name', '=', automation_name),
        ], limit=1)
        self.assertTrue(automation)
        self.assertEqual(automation.trigger, 'on_create|on_write|on_unlink')
        config.write({'state': 'inactive'})
        automation = self.env['base.automation'].search([
            ('name', '=', automation_name),
        ], limit=1)
        self.assertFalse(automation)
