import enum
import logging
import datetime
import uuid


from typing import Optional, Callable, List

from pydantic import BaseModel

from smart_charger.chargers import BaseCharger
from smart_charger.planner import ChargingPlan, VehicleStatus

logger = logging.getLogger(__name__)

class ChargingSessionStatus(enum.Enum):
    PARTIAL = "partial"

class ChargingSession(BaseModel):
    id: str
    start_timestamp: Optional[datetime.datetime] = None
    stop_timestamp: Optional[datetime.datetime] = None
    vehicle: Optional[VehicleStatus] = None
    charger: Optional[BaseCharger] = None
    plan: Optional[ChargingPlan] = None
    target_soc: Optional[int] = None


class SessionManager:
    """Manage current charging sessions and notify listeners on start/stop.

    Notes:
    - current_sessions and session_history are instance attributes to avoid
      accidental cross-instance sharing.
    - Consumers can register callbacks with `add_on_session_start_listener` and
      `add_on_session_stop_listener` to be notified when sessions start/stop.
    """

    def __init__(self):
        # instance state
        self.current_sessions: List[ChargingSession] = []
        self.session_history: List[ChargingSession] = []

        # listeners
        self._on_start_listeners: List[Callable[[ChargingSession], None]] = []
        self._on_stop_listeners: List[Callable[[ChargingSession], None]] = []

    def add_on_session_start_listener(self, callback: Callable[[ChargingSession], None]) -> None:
        self._on_start_listeners.append(callback)

    def add_on_session_stop_listener(self, callback: Callable[[ChargingSession], None]) -> None:
        self._on_stop_listeners.append(callback)

    def get_charger(self, vehicle_id: str, chargers: list[BaseCharger]) -> Optional[BaseCharger]:
        session = self.get_session_by_vehicle(vehicle_id, join=False)
        if session:
            logger.debug("Vehicle %s is connected to charger %s", vehicle_id, session.charger.id)
            charger = self.get_charger_status_by_id(chargers, session.charger.id)
            return charger
        return None

    def get_session_by_vehicle(self, vehicle_id: str, join = True) -> Optional[ChargingSession]:
        for session in self.current_sessions:
            if session.vehicle and session.vehicle.id == vehicle_id:
                return session

        if join:
            for session in self.current_sessions:
                if session.vehicle is None:
                    logger.info("Joining vehicle %s to existing session with charger %s", vehicle_id, session.charger.id)
                    return session

        return None

    def get_session_by_charger(self, charger_id: str, join=True) -> Optional[ChargingSession]:
        for session in self.current_sessions:
            if session.charger and session.charger.id == charger_id:
                return session

        if join:
            for session in self.current_sessions:
                if session.charger is None:
                    logger.info("Joining charger %s to existing session with vehicle %s", charger_id, session.vehicle.id)
                    return session

        return None

    def connected_charger(self, charger: BaseCharger) -> None:
        logger.info(f"Charger {charger.id} connected {charger.connected}")
        session = self.get_session_by_charger(charger.id)
        if session is None:
            if not charger.connected:
                logger.debug("Charger %s is not connected, no session to create", charger.id)
                return
            else:
                new_session = ChargingSession(
                    id=str(uuid.uuid4()),
                    vehicle=None,
                    charger=charger,
                    start_timestamp=datetime.datetime.now()
                )
                logger.info(f"Created session: \n{session}")
                self.current_sessions.append(new_session)
        elif session:
            if not charger.connected:
                logger.info("Charger %s is disconnected", charger.id)
                session.stop_timestamp = datetime.datetime.now()
                self._trigger_session_stop(session)
                return
            else:
                session.charger = charger
                logger.info(f"Found existing session: \n{session}")
                self._trigger_session_start(session)

    def connected_vehicle(self, vehicle_status: VehicleStatus) -> None:
        logger.info(f"Vehicle {vehicle_status.id} connected: {vehicle_status.connected}")
        session = self.get_session_by_vehicle(vehicle_status.id)
        if session is None:
            if not vehicle_status.connected:
                logger.debug("Vehicle %s is not connected, no session to create", vehicle_status.id)
                return
            else:
                new_session = ChargingSession(
                    id=str(uuid.uuid4()),
                    vehicle=vehicle_status,
                    charger=None,
                    start_timestamp=datetime.datetime.now()
                )
                logger.info(f"Created session: \n{new_session}")
                self.current_sessions.append(new_session)
        elif session:
            if not vehicle_status.connected:
                logger.info("Vehicle %s is disconnected", vehicle_status.id)
                session.stop_timestamp = datetime.datetime.now()
                self._trigger_session_stop(session)
            else:
                session.vehicle = vehicle_status
                logger.info(f"Found existing session: \n{session}")
                self._trigger_session_start(session)

    def archive_sessions(self):
        for session in list(self.current_sessions):
            if session.stop_timestamp:
                self.session_history.append(session)
                self.current_sessions.remove(session)

    @staticmethod
    def get_charger_status_by_id(chargers: list[BaseCharger], charger_id: str) -> Optional[BaseCharger]:
        for charger in chargers:
            if charger.id == charger_id:
                return charger
        return None

    @staticmethod
    def get_vehicle_status_by_id(vehicle_id: str, vehicles: list[VehicleStatus]) -> Optional[VehicleStatus]:
        for vehicle in vehicles:
            if vehicle.id == vehicle_id:
                return vehicle
        return None

    def _trigger_session_stop(self, session: ChargingSession):
        # notify listeners
        for cb in self._on_stop_listeners:
            try:
                cb(session)
            except Exception:
                logger.exception("on_session_stop listener raised an exception")

    def _trigger_session_start(self, session: ChargingSession):
        # notify listeners
        for cb in self._on_start_listeners:
            try:
                cb(session)
            except Exception:
                logger.exception("on_session_start listener raised an exception")



