import asyncio
import datetime
import logging
from argparse import ArgumentParser
from typing import Optional

from smart_charger import secret
from smart_charger.chargers import (
    BaseCharger,
    CtekCharger,
    ZaptecCharger,
    ZaptecSettings,
)
from smart_charger.config import ChargerConfiguration, ChargerType
from smart_charger.messages import MessageListener, MessageSender
from smart_charger.planner import VehicleStatus, ChargingStep, SimpleHourPlanner
from smart_charger.session import SessionManager, ChargingSession
from smart_charger.zaptec import OperatingMode

logger = logging.getLogger(__name__)


class SmartCharger:
    def __init__(self):
        self.config = ChargerConfiguration.load_defaults()
        self.vehicles: list[VehicleStatus] = []
        self.chargers: list[BaseCharger] = []

        for vehicle in self.config.vehicles:
            logger.info("Configure vehicle: %s", vehicle)
            self.vehicles.append(VehicleStatus(id=vehicle.id, soc=0, connected=False))

        for charger_config in self.config.chargers:
            logger.info("Configure charger: %s", charger_config)

            if charger_config.type == ChargerType.CTEK:
                charger = CtekCharger(id=charger_config.id)
            elif charger_config.type == ChargerType.ZAPTEC:
                settings = ZaptecSettings(
                    username=secret.username,
                    password=secret.password,
                    installation_id=secret.installation_id,
                    charger_id=secret.charger_id,
                    base_url="https://api.zaptec.local",  # optional
                )
                charger = ZaptecCharger(id=charger_config.id, settings=settings)
            else:
                raise ValueError(f"Unknown charger type: {charger_config.type}")

            self.chargers.append(charger)

        self.power_consumption: float = 0.0
        self.power_production: float = 0.0
        self.session_manager = SessionManager()
        self.planner = SimpleHourPlanner(self.config)

        # tibber_config = TibberConfig(api_key=secret.tibber_api_key)
        # tibber_prices = TibberPrices(tibber_config)
        # test_planner = PriceAwarePlanner(self.config, tibber_prices=tibber_prices)
        # test_planner.plan_charging()

        # register session listeners
        self.session_manager.add_on_session_start_listener(self._on_session_start)
        self.session_manager.add_on_session_stop_listener(self._on_session_stop)

        self.message_listener = MessageListener(
            self.config, self.chargers, self.vehicles
        )
        self.message_listener.add_on_connected_charger_listener(
            self.session_manager.connected_charger
        )
        self.message_listener.add_on_connected_vehicle_listener(
            self.session_manager.connected_vehicle
        )
        self.message_listener.add_on_target_reached_listeners(self._on_target_reached)
        self.message_listener.add_on_soc_changed_listeners(self._on_soc_changed)
        self.message_listener.add_on_power_consumption_updated(
            self._on_updated_power_consumption
        )
        self.message_listener.add_on_power_production_changed(
            self._on_power_production_changed
        )

        self.message_sender = MessageSender(self.config)

    def _on_session_start(self, session: ChargingSession):
        """Handle new or updated sessions.

        - Log the session start
        - Ensure a plan exists (use Planner)
        - If both vehicle and charger are connected, start charging via charger.impl
        """
        logger.info(
            f"Session started/updated: {session.id} (vehicle={session.vehicle.id} charger={session.charger.id})"
        )

        status = session.charger.get_status()
        if status == OperatingMode.Connected_Charging:
            logger.info(
                "New session, but charger already is charging. Stop charging for the new session"
            )
            session.charger.stop_charging()

        # assign a plan if missing and vehicle is known
        if not session.plan and session.vehicle:
            session.target_soc = self.config.get_vehicle_config_by_id(
                session.vehicle.id
            ).target_soc
            session.plan = self.planner.plan_charging(session.vehicle)
            logger.info(f"Assigned plan to session {session.id}: {session.plan}")

    def _on_session_stop(self, session: ChargingSession):
        logger.info(f"Session stopped: {session.id}")
        self.message_sender.publish(
            f"{self.config.smart_charger_topic_prefix}/sessions/{session.id}", None
        )
        vehicle = SessionManager.get_vehicle_status_by_id(
            session.vehicle.id, self.vehicles
        )
        if vehicle:
            vehicle.connected = False
        charger = session.charger
        if charger:
            charger.connected = False
            charger.charging = False

        self.session_manager.archive_sessions()

    @staticmethod
    def _on_charge_start(session: ChargingSession, new_charging_step: ChargingStep):
        logger.info("Starting charging")
        status = session.charger.get_status()
        if status in [
            OperatingMode.Connected_Requesting,
            OperatingMode.Connected_Finished,
        ]:
            session.charger.start_charging()
        session.charger.set_current(new_charging_step.current)

    @staticmethod
    def _on_charge_stop(session: ChargingSession):
        logger.info("Stopped charging")
        status = session.charger.get_status()
        if status == OperatingMode.Connected_Charging:
            session.charger.stop_charging()

    @staticmethod
    def _on_changed_charging_step(
        session: ChargingSession,
        previous_charging_step: ChargingStep,
        charging_step: ChargingStep,
    ):
        logger.info(f"Changed charging step {charging_step.id}")
        if previous_charging_step.current != charging_step.current:
            session.charger.set_current(charging_step.current)

    def _on_target_reached(self, vehicle: VehicleStatus):
        session = self.session_manager.get_session_by_vehicle(vehicle_id=vehicle.id)
        logger.info(f"Target soc {session.target_soc} reached for {vehicle.id}")
        status = session.charger.get_status()
        if status == OperatingMode.Connected_Charging:
            session.charger.stop_charging()

    @staticmethod
    def _on_soc_changed(vehicle: VehicleStatus):
        logger.info(f"Vehicle {vehicle.id} changes SOC: {vehicle.soc}")

    def _on_updated_power_consumption(self, power):
        logger.debug(f"Received power consumption: {power} watts")
        self.power_consumption = power

    def _on_power_production_changed(self, power: float):
        logger.debug(f"Received power production: {power} watts")
        self.power_production = power

    async def charger_loop(self, check_interval_seconds: int = 10):
        """Async loop that controls the chargers."""
        logger.info("Starting async charger loop")
        try:
            while True:
                # Check charging sessions
                for session in self.session_manager.current_sessions:
                    charger = session.charger
                    plan = session.plan
                    charging_step = plan.get_charging_step() if plan else None
                    if charging_step and not charger.charging:
                        logger.info(
                            f"Starting charging, current {charging_step.current}"
                        )
                        charger.charging = True
                        plan.active_step = charging_step
                        self._on_charge_start(session, charging_step)
                    elif charging_step and charging_step.id != plan.active_step.id:
                        logger.info(
                            f"Changing charging step, current {charging_step.current}"
                        )
                        previous_charging_step = plan.active_step
                        plan.active_step = charging_step
                        self._on_changed_charging_step(
                            session, previous_charging_step, charging_step
                        )
                    elif not charging_step and charger and charger.charging:
                        logger.info("Stop charging")
                        charger.charging = False
                        plan.active_step = None
                        self._on_charge_stop(session)

                await asyncio.sleep(check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("charger loop cancelled")
            raise

    async def send_status_loop(self, check_interval_seconds: int = 10):
        logger.info("Starting async send status loop")
        try:
            while True:
                tariff = self.get_tariff()
                power_consumption_high = (
                    self.power_consumption > self.config.high_load_threshold
                )
                logger.debug(
                    f"Tariff enabled {tariff}, Power consumption high: {power_consumption_high}"
                )
                self.message_sender.publish(self.config.tariff.topic, tariff)
                self.message_sender.publish(
                    self.config.high_load_topic, power_consumption_high
                )

                for session in self.session_manager.current_sessions:
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/sessions/{session.id}",
                        session.model_dump_json(),
                    )

                for charger in self.chargers:
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/chargers/{charger.id.lower()}/connected",
                        charger.connected,
                    )
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/chargers/{charger.id.lower()}/charging",
                        charger.charging,
                    )

                for vehicle in self.vehicles:
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/vehicles/{vehicle.id.lower()}/connected",
                        vehicle.connected,
                    )
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/vehicles/{vehicle.id.lower()}/soc",
                        vehicle.soc,
                    )

                await asyncio.sleep(check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("send status loop cancelled")
            raise

    @staticmethod
    def get_tariff():
        timestamp = datetime.datetime.now()
        if timestamp.month in [1, 2, 3, 11, 12] and 7 <= timestamp.hour < 21:
            return True
        return False

    async def _run_async_tasks(self):
        session_task = asyncio.create_task(
            self.send_status_loop(check_interval_seconds=10)
        )
        charger_task = asyncio.create_task(self.charger_loop(check_interval_seconds=10))

        try:
            await asyncio.gather(session_task, charger_task)
        except asyncio.CancelledError:
            logger.info("Async tasks cancelled")
            session_task.cancel()
            charger_task.cancel()
            await asyncio.gather(session_task, charger_task, return_exceptions=True)
            raise
        except Exception:
            session_task.cancel()
            charger_task.cancel()
            await asyncio.gather(session_task, charger_task, return_exceptions=True)
            raise

    def run_async(self):
        """Start MQTT in background and run the asyncio monitor loop (blocking call)."""
        logger.info("Running SmartCharger")

        # Start the message listener
        self.message_listener.start()
        self.message_sender.start()

        try:
            asyncio.run(self._run_async_tasks())
        finally:
            self.message_listener.cleanup()
            self.message_sender.cleanup()

    def get_charger(self, charger_id) -> Optional[BaseCharger]:
        for charger in self.chargers:
            if charger.id == charger_id:
                return charger
        return None

    def get_vehicle(self, vehicle_id) -> Optional[VehicleStatus]:
        for vehicle in self.vehicles:
            if vehicle.id == vehicle_id:
                return vehicle
        return None


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
    )

    argument_parser = ArgumentParser()
    argument_parser.add_argument(
        "--start", action="store_true", help="Start SmartCharger in the background"
    )
    args = argument_parser.parse_args()
    if args.start:
        charger = SmartCharger()
        charger.run_async()


if __name__ == "__main__":
    main()
