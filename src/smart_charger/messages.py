import random
import logging
from typing import Callable, Any

from smart_charger.chargers import BaseCharger
from smart_charger.config import ChargerConfiguration
from smart_charger.planner import VehicleStatus
from smart_charger.session import SessionManager
from paho.mqtt import client as mqtt_client

logger = logging.getLogger(__file__)


class MessageListener:
    def __init__(
        self,
        config: ChargerConfiguration,
        chargers: list[BaseCharger],
        vehicles: list[VehicleStatus],
    ):
        self.config = config
        self.chargers = chargers
        self.vehicles = vehicles

        # Generate a Client ID
        self.client_id = f"smartcharger-listener-{random.randint(0, 1000)}"
        self.client = None  # MQTT client

        # listeners
        self._on_connected_charger_listeners: list[Callable[[BaseCharger], None]] = []
        self._on_connected_vehicle_listeners: list[Callable[[VehicleStatus], None]] = []
        self._on_target_reached_listeners: list[Callable[[VehicleStatus], None]] = []
        self._on_soc_changed_listeners: list[Callable[[VehicleStatus], None]] = []
        self._on_power_consumption_changed: list[Callable[[float], None]] = []
        self._on_power_production_changed: list[Callable[[float], None]] = []

    def add_on_connected_charger_listener(
        self, callback: Callable[[BaseCharger], None]
    ) -> None:
        self._on_connected_charger_listeners.append(callback)

    def add_on_connected_vehicle_listener(
        self, callback: Callable[[VehicleStatus], None]
    ) -> None:
        self._on_connected_vehicle_listeners.append(callback)

    def add_on_target_reached_listeners(
        self, callback: Callable[[VehicleStatus], None]
    ) -> None:
        self._on_target_reached_listeners.append(callback)

    def add_on_soc_changed_listeners(
        self, callback: Callable[[VehicleStatus], None]
    ) -> None:
        self._on_soc_changed_listeners.append(callback)

    def add_on_power_consumption_updated(
        self, callback: Callable[[float], None]
    ) -> None:
        self._on_power_consumption_changed.append(callback)

    def add_on_power_production_changed(
        self, callback: Callable[[float], None]
    ) -> None:
        self._on_power_production_changed.append(callback)

    def connect_mqtt(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info("Connected to MQTT Broker!")
            else:
                logger.error("Failed to connect, return code %d\n", rc)

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION1, self.client_id
        )

        # client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.connect(self.config.mqtt_broker, self.config.mqtt_port)
        return client

    def subscribe(self, client: mqtt_client.Client):
        def on_message(client, userdata, msg):
            logger.info(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
            for charger_config in self.config.chargers:
                charger_status = SessionManager.get_charger_status_by_id(
                    self.chargers, charger_config.id
                )
                if msg.topic == charger_config.status_topic:
                    value = charger_status.get_connected_from_status(
                        msg.payload.decode()
                    )
                    logger.info(f"Charger value {value}")
                    if charger_status.connected != value:
                        charger_status.connected = value
                        logger.info(
                            f"Updated {charger_config.name} connected to {charger_status.connected}"
                        )
                        self._trigger_listeners(
                            self._on_connected_charger_listeners, charger_status
                        )

            for vehicle in self.config.vehicles:
                vehicle_status = SessionManager.get_vehicle_status_by_id(
                    vehicle.id, self.vehicles
                )
                if msg.topic == vehicle.connected_topic:
                    value = _decode_bool(msg)
                    if vehicle_status.connected != value:
                        vehicle_status.connected = value
                        logger.info(
                            f"Updated {vehicle.name} connected to {vehicle_status.connected}"
                        )
                        self._trigger_listeners(
                            self._on_connected_vehicle_listeners, vehicle_status
                        )

                elif msg.topic == vehicle.soc_topic:
                    try:
                        vehicle_status.soc = int(msg.payload.decode())
                        logger.debug(
                            f"Updated {vehicle.name} SOC to {vehicle_status.soc}"
                        )
                        self._trigger_listeners(
                            self._on_soc_changed_listeners, vehicle_status
                        )
                        if vehicle_status.soc >= vehicle.target_soc:
                            self._trigger_listeners(
                                self._on_target_reached_listeners, vehicle_status
                            )

                    except ValueError:
                        logger.error(
                            f"Invalid SOC payload for {vehicle.name}: {msg.payload}"
                        )

            if msg.topic == self.config.power_consumption_topic:
                try:
                    power = float(msg.payload.decode())
                    self._trigger_listeners(self._on_power_consumption_changed, power)
                except ValueError:
                    logger.error(f"Invalid power payload: {msg.payload}")

            if msg.topic == self.config.power_production_topic:
                try:
                    power = float(msg.payload.decode())
                    logger.info(f"Received production: {power} watts")
                    self._trigger_listeners(self._on_power_production_changed, power)
                except ValueError:
                    logger.error(f"Invalid power payload: {msg.payload}")

        def _decode_bool(msg) -> bool:
            return msg.payload.decode().lower() in ["true", "1", "yes"]

        for charger in self.config.chargers:
            if charger.connected_topic:
                client.subscribe(charger.connected_topic)
                client.subscribe(charger.status_topic)

        for vehicle in self.config.vehicles:
            if vehicle.connected_topic:
                client.subscribe(vehicle.connected_topic)
            if vehicle.soc_topic:
                client.subscribe(vehicle.soc_topic)

        client.subscribe(self.config.power_consumption_topic)
        client.subscribe(self.config.power_production_topic)
        client.on_message = on_message

    @staticmethod
    def _trigger_listeners(listeners: list[Callable[[Any], None]], value: Any):
        for listener in listeners:
            listener(value)

    def start(self):
        self.client = self.connect_mqtt()
        self.subscribe(self.client)
        self.client.loop_start()

    def cleanup(self):
        # cleanup mqtt client
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            pass


class MessageSender:
    def __init__(self, config: ChargerConfiguration):
        self.config = config
        # Generate a Client ID
        self.client_id = f"smartcharger-sender-{random.randint(0, 1000)}"
        self.client = None  # MQTT client

    def connect_mqtt(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info("Connected to MQTT Broker!")
            else:
                logger.error("Failed to connect, return code %d\n", rc)

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION1, self.client_id
        )

        # client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.connect(self.config.mqtt_broker, self.config.mqtt_port)
        return client

    def start(self):
        self.client = self.connect_mqtt()
        self.client.loop_start()

    def publish(self, topic, data):
        self.client.publish(topic, data)

    def cleanup(self):
        # cleanup mqtt client
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            pass
