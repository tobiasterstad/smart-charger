import asyncio
import logging
from argparse import ArgumentParser
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from smart_charger.secrets import Secrets
from smart_charger.chargers import (
    BaseCharger,
    ChargerStatus,
    CtekCharger,
    ZaptecCharger,
    ZaptecSettings,
    ChargerReason,
)
from smart_charger.config import ChargerConfiguration, ChargerType, PlannerType
from smart_charger.messages import MessageListener, MessageSender
from smart_charger.planner import (
    VehicleStatus,
    ChargingStep,
    SimpleHourPlanner,
    PriceAwarePlanner,
)
from smart_charger.price_providers import TibberPriceProvider
from smart_charger.solar_providers import SolarChargerController
from smart_charger.session import SessionManager, ChargingSession
from smart_charger.tariff import create_tariff_provider, TariffProvider
from smart_charger.tibber.tibber_util import TibberConfig
from smart_charger.vehicle import VehicleConnectionStatus
from smart_charger.zaptec import OperatingMode

from pyrate_limiter import Duration, Rate, Limiter

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    message: str
    details: dict = field(default_factory=dict)


class SmartCharger:
    def __init__(self, read_only: bool = False):
        self.config = ChargerConfiguration.load_defaults()
        secrets = Secrets()
        self.vehicles: list[VehicleStatus] = []
        self.chargers: list[BaseCharger] = []

        if read_only:
            logger.info("Running in READ-ONLY mode - no charger commands will be sent")

        for vehicle in self.config.vehicles:
            logger.info("Configure vehicle: %s", vehicle)
            self.vehicles.append(
                VehicleStatus(
                    id=vehicle.id,
                    soc=0,
                    connection_status=VehicleConnectionStatus.DISCONNECTED,
                )
            )

        for charger_config in self.config.chargers:
            logger.info("Configure charger: %s", charger_config)

            if charger_config.type == ChargerType.CTEK:
                charger = CtekCharger(id=charger_config.id, read_only=read_only)
            elif charger_config.type == ChargerType.ZAPTEC:
                settings = ZaptecSettings(
                    username=secrets.username,
                    password=secrets.password,
                    installation_id=secrets.installation_id,
                    charger_id=secrets.charger_id,
                    access_token=secrets.zaptec_access_token,
                    token_expires_at=secrets.zaptec_token_expires_at,
                    on_token_refreshed=secrets.save_zaptec_token,
                    base_url="https://api.zaptec.local",  # optional
                )
                charger = ZaptecCharger(
                    id=charger_config.id, settings=settings, read_only=read_only
                )
            else:
                raise ValueError(f"Unknown charger type: {charger_config.type}")

            self.chargers.append(charger)

        self.power_consumption: float = 0.0
        self.power_consumption_high: bool = False
        self.power_production: float = 0.0
        self.power_accumulated_hourly_consumption: float = 0.0
        self.power_accumulated_hourly_consumption_high: bool = False
        self.effect_tariff_stopped_hour: Optional[int] = None
        self._solar_limiter = Limiter(Rate(1, Duration.SECOND * 30))
        self.session_manager = SessionManager()

        if self.config.planner == PlannerType.SIMPLE:
            logger.info("Configure simple hour planner")
            self.planner = SimpleHourPlanner(self.config)
            self.solar_charger_controller = SolarChargerController(self.config)
        elif self.config.planner == PlannerType.TIBBER:
            logger.info("Configure Tibber hour planner")
            tibber_config = TibberConfig(api_key=secrets.tibber_api_key)
            tibber_price_provider = TibberPriceProvider(tibber_config)
            self.solar_charger_controller = SolarChargerController(
                self.config, price_provider=tibber_price_provider
            )
            self.planner = PriceAwarePlanner(
                self.config, price_provider=tibber_price_provider
            )

        self.tariff_provider: TariffProvider = create_tariff_provider(
            self.config.tariff
        )

        self.message_listener = MessageListener(
            self.config, self.chargers, self.vehicles
        )
        self.message_sender = MessageSender(self.config)

        self._register_event_listeners()

    def _register_event_listeners(self):
        """Register all event listeners."""
        # Session events
        self.session_manager.add_on_session_start_listener(self._on_session_start)
        self.session_manager.add_on_session_stop_listener(self._on_session_stop)

        # MQTT message events -> session management
        ml = self.message_listener
        ml.add_on_connected_charger_listener(self.session_manager.connected_charger)
        ml.add_on_connected_vehicle_listener(self.session_manager.connected_vehicle)
        ml.add_on_target_reached_listeners(self._on_target_reached)
        ml.add_on_soc_changed_listeners(self._on_soc_changed)

        # Power events (multiple handlers)
        for cb in (
            self._on_updated_power_consumption,
            self.solar_charger_controller.update_consumption,
        ):
            ml.add_on_power_consumption_updated(cb)
        for cb in (
            self._on_power_production_changed,
            self.solar_charger_controller.update_production,
        ):
            ml.add_on_power_production_changed(cb)

        ml.add_on_power_accumulated_hourly_changed(
            self._on_accumulated_hourly_consumption_changed
        )

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
            logger.info("%s", session.plan.format_for_log())

    def _on_session_stop(self, session: ChargingSession):
        logger.info(f"Session stopped: {session.id}")
        self.message_sender.publish(
            f"{self.config.smart_charger_topic_prefix}/sessions/{session.id}", None
        )
        vehicle = SessionManager.get_vehicle_status_by_id(
            session.vehicle.id, self.vehicles
        )
        if vehicle:
            vehicle.connection_status = VehicleConnectionStatus.DISCONNECTED
        charger = session.charger
        if charger:
            charger.status = ChargerStatus.DISCONNECTED

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

    def _on_target_reached(self, vehicle: VehicleStatus):
        session = self.session_manager.get_session_by_vehicle(vehicle_id=vehicle.id)
        if session is None:
            logger.warning(
                f"No active session found for vehicle {vehicle.id}, cannot report target SOC reached"
            )
            return
        if session.target_soc is None:
            logger.warning(
                f"Session for vehicle {vehicle.id} has no target_soc set, skipping"
            )
            return
        if session.charger is None:
            logger.warning(
                f"Session for vehicle {vehicle.id} has no charger set, skipping"
            )
            return

        logger.info(f"Target soc {session.target_soc} reached for {vehicle.id}")
        status = session.charger.get_status()
        if status == OperatingMode.Connected_Charging:
            session.charger.stop_charging()

    @staticmethod
    def _on_soc_changed(vehicle: VehicleStatus):
        logger.info(f"Vehicle {vehicle.id} changes SOC: {vehicle.soc}")

    @staticmethod
    def _on_high_consumption_stop(session):
        logger.warning(
            "Hourly energy threshold exceeded - stopping charging until next hour"
        )
        session.charger.status = ChargerStatus.PAUSED
        session.charger.reason = ChargerReason.PAUSED_HIGH_LOAD
        session.charger.current = 0
        session.charger.stop_charging()
        # self.effect_tariff_stopped_hour = datetime.datetime.now().hour

    def _on_high_consumption_start(self, session):
        logger.warning("Not implemented")
        pass

    def _on_updated_power_consumption(self, power):
        logger.debug(f"Received power consumption: {power} watts")
        self.power_consumption = power
        self.power_consumption_high = (
            self.power_consumption > self.config.high_load_threshold
        )

    def _on_power_production_changed(self, power: float):
        logger.debug(f"Received power production: {power} watts")
        self.power_production = power

    def _on_accumulated_hourly_consumption_changed(self, power: float):
        logger.debug(f"Received accumulated hourly consumption: {power} watts")
        self.power_accumulated_hourly_consumption = power
        self.power_accumulated_hourly_consumption_high = (
            self.power_accumulated_hourly_consumption
            > self.config.high_hourly_energy_threshold
        )

    def _handle_solar_charging(self, session: ChargingSession) -> None:
        """Handle solar surplus charging."""
        charger = session.charger

        if not charger:
            logger.debug(
                "No charger assigned to session - cannot handle solar charging"
            )
            return

        if not self._solar_limiter.try_acquire("solar_charging", blocking=False):
            return

        prediction = self.solar_charger_controller.get_solar_charge_prediction(session)

        if prediction.available:
            logger.info(
                f"Solar charging available - current: {prediction.current}, effective price: {prediction.effective_price}"
            )
            if charger.status != ChargerStatus.CHARGING:
                charger.start_charging()
            if charger.current != prediction.current:
                charger.set_current(prediction.current)
            # TODO: Decide if this should also be a status
            session.solar_charging = True
        else:
            logger.debug("Solar charging not available - not starting solar charging")
            if charger.status == ChargerStatus.CHARGING:
                charger.stop_charging()
            session.solar_charging = False

    def _handle_charging_control(self, session: ChargingSession) -> None:
        """Handle charging start/stop/change based on charging step and effect tariff."""
        charger = session.charger

        if not charger:
            logger.debug(
                "No charger assigned to session - cannot handle charging control"
            )
            return

        charging_step = session.get_current_charging_step()

        # Charger is ready to start charging
        if charging_step and charger.status == ChargerStatus.CONNECTED:
            logger.info(f"Starting charging, current {charging_step.current}")
            self._on_charge_start(session, charging_step)

        # Resume charging if it was paused due to high load and conditions are now good
        elif (
            session.charger.status == ChargerStatus.PAUSED
            and session.charger.reason == ChargerReason.PAUSED_HIGH_LOAD
            and not self.power_accumulated_hourly_consumption_high
            and charging_step
        ):
            logger.info("Resuming charging after high load pause")
            self._on_high_consumption_start(session)

        # Stop charging if we are currently charging but the hourly energy threshold is exceeded
        elif (
            self.power_accumulated_hourly_consumption_high
            and charger.status == ChargerStatus.CHARGING
        ):
            logger.warning(
                "Hourly energy threshold exceeded - stopping charging until next hour"
            )
            self._on_high_consumption_stop(session)

        # Set new current
        elif (
            charging_step
            and charger.status == ChargerStatus.CHARGING
            and charging_step.current != charger.current
        ):
            logger.info(f"Changing charging step, current {charging_step.current}")
            charger.set_current(charging_step.current)

        # Stop charging
        elif (
            not charging_step
            and charger.status == ChargerStatus.CHARGING
            and not session.solar_charging
        ):
            logger.info("Stop charging")
            charger.status = ChargerStatus.CONNECTED
            self._on_charge_stop(session)

    async def charger_loop(self, check_interval_seconds: int = 10) -> None:
        """
        Async loop that starts/stops charging based on the current session plans and solar surplus.
        :param check_interval_seconds: is the interval in seconds between each check of the sessions and plans. Default is 10 seconds.
        :return: None
        """
        logger.info("Starting async charger loop")

        try:
            while True:
                for session in self.session_manager.current_sessions:
                    if not session.get_current_charging_step():
                        self._handle_solar_charging(session)

                    self._handle_charging_control(session)

                await asyncio.sleep(check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("charger loop cancelled")
            raise

    async def send_status_loop(self, check_interval_seconds: int = 10) -> None:
        """
        Async loop that sends status updates to MQTT.
        :param check_interval_seconds: is the interval in seconds between each status update. Default is 10 seconds.
        :return: None
        """
        logger.info("Starting async send status loop")
        try:
            while True:
                tariff = self.tariff_provider.is_high_tariff()
                logger.debug(
                    f"Tariff enabled {tariff}, Power consumption high: {self.power_consumption_high}"
                )
                self.message_sender.publish(self.config.tariff.topic, tariff)
                self.message_sender.publish(
                    self.config.high_load_topic, self.power_consumption_high
                )
                self.message_sender.publish(
                    self.config.high_hourly_energy_topic,
                    self.power_accumulated_hourly_consumption_high,
                )

                for session in self.session_manager.current_sessions:
                    self.message_sender.publish(
                        f"{self.config.smart_charger_topic_prefix}/sessions/{session.id}",
                        session.model_dump_json(),
                    )

                for charger in self.chargers:
                    charger_config = self.config.get_charger_config_by_id(charger.id)
                    if charger_config:
                        self.message_sender.publish(
                            charger_config.get_outgoing_status_topic(
                                self.config.smart_charger_topic_prefix
                            ),
                            charger.status.value,
                        )
                        self.message_sender.publish(
                            charger_config.get_outgoing_current_topic(
                                self.config.smart_charger_topic_prefix
                            ),
                            charger.current,
                        )

                for vehicle in self.vehicles:
                    vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
                    if vehicle_config:
                        self.message_sender.publish(
                            vehicle_config.get_outgoing_status_topic(
                                self.config.smart_charger_topic_prefix
                            ),
                            vehicle.connection_status.value,
                        )
                        self.message_sender.publish(
                            vehicle_config.get_outgoing_soc_topic(
                                self.config.smart_charger_topic_prefix
                            ),
                            vehicle.soc,
                        )

                await asyncio.sleep(check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("send status loop cancelled")
            raise

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

    def check_health(self) -> HealthCheckResult:
        """Check the health of all system components."""
        issues = []
        details = {}

        mqtt_healthy = (
            self.message_listener.client is not None
            and self.message_listener.client.is_connected()
        )
        details["mqtt_listener"] = "connected" if mqtt_healthy else "disconnected"

        mqtt_sender_healthy = (
            self.message_sender.client is not None
            and self.message_sender.client.is_connected()
        )
        details["mqtt_sender"] = "connected" if mqtt_sender_healthy else "disconnected"

        if not mqtt_healthy or not mqtt_sender_healthy:
            issues.append("MQTT not connected")

        connected_vehicles = sum(1 for v in self.vehicles if v.connected)
        details["vehicles_connected"] = f"{connected_vehicles}/{len(self.vehicles)}"

        connected_chargers = sum(
            1 for c in self.chargers if c.status in [ChargerStatus.CONNECTED]
        )
        details["chargers_connected"] = f"{connected_chargers}/{len(self.chargers)}"

        active_sessions = len(self.session_manager.current_sessions)
        details["active_sessions"] = active_sessions

        if self.power_production > 0:
            details["solar_production_w"] = self.power_production

        if self.power_consumption > 0:
            details["consumption_w"] = self.power_consumption

        if issues:
            status = HealthStatus.UNHEALTHY
            message = "; ".join(issues)
        elif connected_vehicles == 0 and connected_chargers == 0:
            status = HealthStatus.DEGRADED
            message = "No vehicles or chargers connected"
        else:
            status = HealthStatus.HEALTHY
            message = "All systems operational"

        return HealthCheckResult(status=status, message=message, details=details)


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
    )
    argument_parser = ArgumentParser()
    argument_parser.add_argument(
        "--start", action="store_true", help="Start SmartCharger in the background"
    )
    argument_parser.add_argument(
        "--read-only",
        action="store_true",
        help="Run without controlling chargers (dry-run mode)",
    )
    argument_parser.add_argument(
        "--health", action="store_true", help="Run health check and exit"
    )
    args = argument_parser.parse_args()
    if args.health:
        import json

        smart_charger = SmartCharger(read_only=args.read_only)
        result = smart_charger.check_health()
        print(f"Health Status: {result.status.value}")
        print(f"Message: {result.message}")
        print(f"Details: {json.dumps(result.details, indent=2)}")
        return
    if args.start:
        charger = SmartCharger(read_only=args.read_only)
        charger.run_async()


if __name__ == "__main__":
    main()
