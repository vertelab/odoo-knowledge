from odoo import models, fields, api
import logging
import json

try:
    import pika
except ImportError:
    pika = None

_logger = logging.getLogger(__name__)


class GraphPublisher(models.AbstractModel):
    _name = 'knowledge.graph.publisher'
    _description = 'RabbitMQ Graph Database Publisher'

    def _get_connection_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'host': ICP.get_param('knowledge_graphdb.rabbitmq_host', 'localhost'),
            'port': int(ICP.get_param('knowledge_graphdb.rabbitmq_port', '5672')),
            'login': ICP.get_param('knowledge_graphdb.rabbitmq_user', 'guest'),
            'password': ICP.get_param('knowledge_graphdb.rabbitmq_password', 'guest'),
            'exchange': ICP.get_param('knowledge_graphdb.rabbitmq_exchange', 'odoo_events_topic'),
            'exchange_type': ICP.get_param('knowledge_graphdb.rabbitmq_exchange_type', 'topic'),
            'virtual_host': ICP.get_param('knowledge_graphdb.rabbitmq_vhost', '/'),
        }

    def _get_connection(self):
        """Create and return a pika connection."""
        if pika is None:
            _logger.error('pika library is not installed. Install with: pip install pika')
            return None
        params = self._get_connection_params()
        try:
            credentials = pika.PlainCredentials(params['login'], params['password'])
            parameters = pika.ConnectionParameters(
                host=params['host'],
                port=params['port'],
                virtual_host=params['virtual_host'],
                credentials=credentials,
            )
            return pika.BlockingConnection(parameters)
        except Exception as e:
            _logger.error('Failed to connect to RabbitMQ: %s', e)
            return None

    def publish(self, model_name, record_id, operation, config, fields_data=None):
        """Publish a single record change to RabbitMQ.

        :param model_name: technical model name (e.g. 'res.partner')
        :param record_id: ID of the changed record
        :param operation: 'create', 'write', 'unlink', or 'sync'
        :param config: knowledge.graph.model record (browsed)
        :param fields_data: dict of field values (optional, computed if not provided)
        """
        self.ensure_one()
        Model = self.env.get(model_name)
        if not Model:
            return
        if fields_data is None and operation != 'unlink':
            record = Model.sudo().browse(record_id)
            if record.exists():
                if config.key_field_ids:
                    field_names = config.key_field_ids.mapped('name')
                    fields_data = record.read(field_names)[0] if field_names else None
                else:
                    fields_data = record.read()[0]
                if fields_data and 'id' in fields_data:
                    del fields_data['id']
        payload = {
            'tenant_id': self.env.cr.dbname,
            'model': model_name,
            'operation': operation,
            'record_id': record_id,
            'target_queue': config.target_queue,
            'graph_topic': config.user_id.graph_topic if config.user_id else None,
            'fields': fields_data or {},
        }
        routing_key = f"odoo.{model_name}.{operation}"
        self._send(routing_key, payload)

    def publish_batch(self, config, records):
        """Publish all records in a batch."""
        Model = records._name
        for record in records:
            self.publish(Model, record.id, 'sync', config)

    def publish_admin(self, action, payload):
        """Send an administrative message to RabbitMQ.

        :param action: admin action type (e.g. 'provision_database', 'refresh', 'delete_database')
        :param payload: dict of action-specific data
        """
        message = {
            'tenant_id': self.env.cr.dbname,
            'action': action,
            'timestamp': fields.Datetime.now().isoformat(),
            **payload,
        }
        routing_key = 'odoo.admin'
        self._send(routing_key, message)

    def _send(self, routing_key, message):
        """Low-level method to serialize and send a JSON message via pika."""
        if pika is None:
            _logger.error('pika library not available, cannot send message')
            return
        conn = self._get_connection()
        if not conn:
            return
        try:
            channel = conn.channel()
            params = self._get_connection_params()
            channel.exchange_declare(
                exchange=params['exchange'],
                exchange_type=params['exchange_type'],
                durable=True,
            )
            body = json.dumps(message, default=str)
            channel.basic_publish(
                exchange=params['exchange'],
                routing_key=routing_key,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type='application/json',
                ),
            )
            _logger.info(
                'Published to %s/%s [%s]: %s',
                params['exchange'], routing_key, message.get('operation', message.get('action', 'admin')),
                message.get('model', ''),
            )
        except Exception as e:
            _logger.error('Failed to publish message: %s', e)
        finally:
            try:
                conn.close()
            except Exception:
                pass
