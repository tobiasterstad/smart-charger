import unittest
from unittest.mock import MagicMock, patch

from smart_charger.config import ChargerConfiguration, ChargerType, VehicleConfig
from smart_charger.messages import MessageListener, MessageSender
from smart_charger.planner import VehicleStatus


class TestMessageListener(unittest.TestCase):
    def setUp(self):
        self.config = ChargerConfiguration.load_defaults()
        self.chargers = [
            MagicMock(id="charger1"),
            MagicMock(id="charger2"),
        ]
        self.vehicles = [
            VehicleStatus(id="leaf", soc=50, connected=False),
            VehicleStatus(id="rav4", soc=30, connected=False),
        ]

    def test_listener_initialization(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        self.assertEqual(listener.config, self.config)
        self.assertEqual(listener.chargers, self.chargers)
        self.assertEqual(listener.vehicles, self.vehicles)

    def test_add_connected_charger_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_connected_charger_listener(callback)
        self.assertIn(callback, listener._on_connected_charger_listeners)

    def test_add_connected_vehicle_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_connected_vehicle_listener(callback)
        self.assertIn(callback, listener._on_connected_vehicle_listeners)

    def test_add_target_reached_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_target_reached_listeners(callback)
        self.assertIn(callback, listener._on_target_reached_listeners)

    def test_add_soc_changed_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_soc_changed_listeners(callback)
        self.assertIn(callback, listener._on_soc_changed_listeners)

    def test_add_power_consumption_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_power_consumption_updated(callback)
        self.assertIn(callback, listener._on_power_consumption_changed)

    def test_add_power_production_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_power_production_changed(callback)
        self.assertIn(callback, listener._on_power_production_changed)

    def test_trigger_listeners(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback1 = MagicMock()
        callback2 = MagicMock()
        listener._on_connected_charger_listeners.append(callback1)
        listener._on_connected_charger_listeners.append(callback2)

        listener._trigger_listeners(
            listener._on_connected_charger_listeners, "test_value"
        )

        callback1.assert_called_once_with("test_value")
        callback2.assert_called_once_with("test_value")

    @patch("smart_charger.messages.mqtt_client.Client")
    def test_connect_mqtt_creates_client(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        listener = MessageListener(self.config, self.chargers, self.vehicles)
        listener.client_id = "test-client"
        client = listener.connect_mqtt()

        mock_client_class.assert_called_once()
        mock_client.connect.assert_called_once_with(
            self.config.mqtt_broker, self.config.mqtt_port
        )


class TestMessageSender(unittest.TestCase):
    def setUp(self):
        self.config = ChargerConfiguration.load_defaults()

    def test_sender_initialization(self):
        sender = MessageSender(self.config)
        self.assertEqual(sender.config, self.config)

    @patch("smart_charger.messages.mqtt_client.Client")
    def test_connect_mqtt_creates_client(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        sender = MessageSender(self.config)
        sender.client_id = "test-sender"
        client = sender.connect_mqtt()

        mock_client_class.assert_called_once()
        mock_client.connect.assert_called_once_with(
            self.config.mqtt_broker, self.config.mqtt_port
        )

    @patch("smart_charger.messages.mqtt_client.Client")
    def test_publish_calls_client_publish(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        sender = MessageSender(self.config)
        sender.client = mock_client
        sender.publish("test/topic", "test_payload")

        mock_client.publish.assert_called_once_with("test/topic", "test_payload")


class TestPowerMessages(unittest.TestCase):
    def setUp(self):
        self.config = ChargerConfiguration.load_defaults()
        self.vehicles = [
            VehicleStatus(id="leaf", soc=50, connected=False),
        ]
        self.chargers = [MagicMock(id="charger1")]

    def test_power_production_triggers_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_power_production_changed(callback)

        # Simulate triggering the listener
        listener._trigger_listeners(listener._on_power_production_changed, 5000.0)

        callback.assert_called_once_with(5000.0)

    def test_power_consumption_triggers_listener(self):
        listener = MessageListener(self.config, self.chargers, self.vehicles)
        callback = MagicMock()
        listener.add_on_power_consumption_updated(callback)

        # Simulate triggering the listener
        listener._trigger_listeners(listener._on_power_consumption_changed, 1500.0)

        callback.assert_called_once_with(1500.0)


if __name__ == "__main__":
    unittest.main()
