import asyncio
import random
import logging
from typing import Callable, Any

from smart_charger.chargers import BaseCharger
from smart_charger.config import ChargerConfiguration
from smart_charger.planner import VehicleStatus
from smart_charger.session import SessionManager
from paho.mqtt import client as mqtt_client

logger = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5
RECONNECT_DELAY_MAX_SECONDS = 300


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
        self._on_energy_accumulated_hourly_changed: list[Callable[[float], None]] = []

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

    def add_on_power_accumulated_hourly_changed(
        self, callback: Callable[[float], None]
    ) -> None:
        self._on_energy_accumulated_hourly_changed.append(callback)

    def connect_mqtt(self):
        self._reconnect_delay = RECONNECT_DELAY_SECONDS

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info("Connected to MQTT Broker!")
                self._reconnect_delay = RECONNECT_DELAY_SECONDS
            else:
                logger.error("Failed to connect, return code %d\n", rc)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning(
                    f"Unexpected disconnection from MQTT, return code {rc}. Reconnecting..."
                )
                self._schedule_reconnect()

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION1, self.client_id
        )

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(self.config.mqtt_broker, self.config.mqtt_port)
        return client

    def _schedule_reconnect(self):
        logger.info(f"Scheduling MQTT reconnection in {self._reconnect_delay} seconds")
        asyncio.get_event_loop().call_later(self._reconnect_delay, self._do_reconnect)
        self._reconnect_delay = min(
            self._reconnect_delay * 2, RECONNECT_DELAY_MAX_SECONDS
        )

    def _do_reconnect(self):
        try:
            logger.info("Attempting MQTT reconnection...")
            self.client = self.connect_mqtt()
            self.subscribe(self.client)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to reconnect: {e}")
            self._schedule_reconnect()

    def _handle_float_message(
        self,
        msg: mqtt_client.MQTTMessage,
        listener_list: list[Callable[[float], None]],
    ) -> None:
        try:
            value = float(msg.payload.decode())
            self._trigger_listeners(listener_list, value)
        except ValueError:
            logger.error(f"Invalid float payload: {msg.payload}")

    def subscribe(self, client: mqtt_client.Client):
        def on_message(client, userdata, msg):
            logger.info(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
            for charger_config in self.config.chargers:
                charger_status = SessionManager.get_charger_status_by_id(
                    self.chargers, charger_config.id
                )
                if msg.topic == charger_config.status_topic:
                    s = charger_status.map_status(msg.payload.decode())
                    charger_status.status = s
                    logger.info(
                        f"Updated {charger_config.name} status to {charger_status}"
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
                        vehicle_soc_reached = (
                            (vehicle_status.soc >= vehicle.target_soc)
                            if vehicle.target_soc
                            else False
                        )
                        self._trigger_listeners(
                            self._on_soc_changed_listeners, vehicle_status
                        )
                        if vehicle_soc_reached:
                            self._trigger_listeners(
                                self._on_target_reached_listeners, vehicle_status
                            )

                    except ValueError:
                        logger.error(
                            f"Invalid SOC payload for {vehicle.name}: {msg.payload}"
                        )

            if msg.topic == self.config.power_consumption_topic:
                self._handle_float_message(msg, self._on_power_consumption_changed)

            if msg.topic == self.config.power_production_topic:
                self._handle_float_message(msg, self._on_power_production_changed)

            if msg.topic == self.config.power_accumulated_hourly_topic:
                self._handle_float_message(
                    msg, self._on_energy_accumulated_hourly_changed
                )

        def _decode_bool(msg) -> bool:
            return msg.payload.decode().lower() in ["true", "1", "yes"]

        for charger in self.config.chargers:
            if charger.status_topic:
                client.subscribe(charger.status_topic)

        for vehicle in self.config.vehicles:
            if vehicle.connected_topic:
                client.subscribe(vehicle.connected_topic)
            if vehicle.soc_topic:
                client.subscribe(vehicle.soc_topic)

        client.subscribe(self.config.power_consumption_topic)
        client.subscribe(self.config.power_production_topic)
        client.subscribe(self.config.power_accumulated_hourly_topic)
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
        self._reconnect_delay = RECONNECT_DELAY_SECONDS

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info("Connected to MQTT Broker!")
                self._reconnect_delay = RECONNECT_DELAY_SECONDS
            else:
                logger.error("Failed to connect, return code %d\n", rc)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning(
                    f"Unexpected disconnection from MQTT, return code {rc}. Reconnecting..."
                )
                self._schedule_reconnect()

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION1, self.client_id
        )

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(self.config.mqtt_broker, self.config.mqtt_port)
        return client

    def _schedule_reconnect(self):
        logger.info(f"Scheduling MQTT reconnection in {self._reconnect_delay} seconds")
        asyncio.get_event_loop().call_later(self._reconnect_delay, self._do_reconnect)
        self._reconnect_delay = min(
            self._reconnect_delay * 2, RECONNECT_DELAY_MAX_SECONDS
        )

    def _do_reconnect(self):
        try:
            logger.info("Attempting MQTT reconnection...")
            self.client = self.connect_mqtt()
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to reconnect: {e}")
            self._schedule_reconnect()

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
