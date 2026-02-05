import asyncio
import logging
from argparse import ArgumentParser

from smart_charger.lib.ctek.config_util import ConfigUtil
from smart_charger.lib.ctek.ctek_util import CTEK
from mqtt_discovery.discovery import (
    UnitOfMeasurement,
    DeviceClass,
    SensorStateClass,
    DeviceDiscovery,
    DeviceBase,
    Origin,
    DeviceSensor,
    HaDiscovery,
)
from paho.mqtt import client as mqtt_client

logger = logging.getLogger("ctek-client")


class CtekMeterService:
    def __init__(self, interval: int):
        config_util = ConfigUtil()
        self.ctek_client = CTEK(config_util)
        self.interval = interval

        self.client = None
        self.client_id = "ctek-meter"
        self.broker = "10.100.0.10"
        self.port = 1883
        self.charger_energy_topic = "terstad/smartcharger/chargers/ctek/energy"
        self.charger_power_topic = "terstad/smartcharger/chargers/ctek/power"

        self.energy_kwh = 0
        self.power_kwh = 0

    def connect_mqtt(self):
        def on_connect(_client, _userdata, _flags, rc):
            if rc == 0:
                logger.info("Connected to MQTT Broker!")
            else:
                logger.error("Failed to connect, return code %d\n", rc)

        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION1, self.client_id
        )

        # client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.connect(self.broker, self.port)
        return client

    async def send_meter_task(self, interval_seconds: int):
        try:
            while True:
                self.ctek_client.login_if_needed()
                meter = self.ctek_client.get_meter()

                session = self.ctek_client.get_current_session()
                if session:
                    logger.info(
                        f"Watt hours consumed in session: {session.watt_hours_consumed}"
                    )
                    logger.info(f"Power: {session.momentary_power}")

                energy_kwh = (meter + session.watt_hours_consumed) / 1000
                # Make sure the meter is increasing when switching from a session
                if energy_kwh > self.energy_kwh:
                    self.energy_kwh = energy_kwh

                self.power_kwh = float(session.momentary_power) / 1000

                self.client.publish(self.charger_energy_topic, self.energy_kwh)
                self.client.publish(self.charger_power_topic, self.power_kwh)

                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("send status loop cancelled")
            raise

    async def _run_async_tasks(self):
        session_task = asyncio.create_task(
            self.send_meter_task(interval_seconds=self.interval)
        )

        try:
            await asyncio.gather(session_task)
        except asyncio.CancelledError:
            logger.info("Async tasks cancelled")
            session_task.cancel()
            await asyncio.gather(session_task, return_exceptions=True)
            raise
        except Exception:
            session_task.cancel()
            await asyncio.gather(session_task, return_exceptions=True)
            raise

    def run_async(self):
        """Start MQTT in background and run the asyncio monitor loop (blocking call)."""
        logger.info("Running ctek meter service")

        discovery = DeviceDiscovery(
            device=DeviceBase(ids="ctek1", name="CTEK charger"),
            origin=Origin(name="Terstad"),
            components={
                "ctek1_energy": DeviceSensor(
                    unique_id="ctek1_energy",
                    name="CTEK Energy",
                    device_class=DeviceClass.Energy,
                    unit_of_measurement=UnitOfMeasurement.KWH,
                    state_topic=self.charger_energy_topic,
                    state_class=SensorStateClass.TotalIncreasing,
                ),
                "ctek1_power": DeviceSensor(
                    unique_id="ctek1_power",
                    name="CTEK Power",
                    device_class=DeviceClass.Power,
                    unit_of_measurement=UnitOfMeasurement.KILO_WATT,
                    state_topic=self.charger_power_topic,
                    state_class=SensorStateClass.Total,
                ),
            },
        )
        ha_discovery = HaDiscovery()
        ha_discovery.discover(discovery)

        self.client = self.connect_mqtt()

        try:
            asyncio.run(self._run_async_tasks())
        finally:
            pass


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
    )
    argument_parser = ArgumentParser()
    argument_parser.add_argument(
        "--start", action="store_true", help="Start SmartCharger in the background"
    )
    argument_parser.add_argument(
        "--interval",
        default=900,
        type=int,
        help="Interval to check meter, defaults to 900",
    )
    args = argument_parser.parse_args()

    if args.start:
        charger = CtekMeterService(args.interval)
        charger.run_async()


if __name__ == "__main__":
    main()
