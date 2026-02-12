import unittest
from unittest.mock import MagicMock, patch

from smart_charger.session import SessionManager, ChargingSession
from smart_charger.planner import VehicleStatus
from smart_charger.chargers import BaseCharger
from smart_charger.config import ChargerType
from smart_charger.zaptec import OperatingMode


class FakeCharger(BaseCharger):
    def __init__(self, id: str):
        super().__init__(
            id=id, connected=False, charging=False, current=0, read_only=False
        )

    def charger_type(self) -> ChargerType:
        return ChargerType.ZAPTEC

    def start_charging(self):
        self.charging = True

    def stop_charging(self):
        self.charging = False

    def set_current(self, current: float):
        self.current = current

    def get_status(self) -> OperatingMode:
        return OperatingMode.Disconnected

    @staticmethod
    def get_connected_from_status(status: str) -> bool:
        return False

    @staticmethod
    def get_charging_from_status(status: str) -> bool:
        return False


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_initialization(self):
        self.assertEqual(self.manager.current_sessions, [])
        self.assertEqual(self.manager.session_history, [])
        self.assertEqual(self.manager._on_start_listeners, [])
        self.assertEqual(self.manager._on_stop_listeners, [])

    def test_add_session_start_listener(self):
        callback = MagicMock()
        self.manager.add_on_session_start_listener(callback)
        self.assertIn(callback, self.manager._on_start_listeners)

    def test_add_session_stop_listener(self):
        callback = MagicMock()
        self.manager.add_on_session_stop_listener(callback)
        self.assertIn(callback, self.manager._on_stop_listeners)

    def test_get_charger_status_by_id(self):
        charger1 = FakeCharger("charger1")
        charger2 = FakeCharger("charger2")
        chargers = [charger1, charger2]

        result = SessionManager.get_charger_status_by_id(chargers, "charger1")
        self.assertEqual(result, charger1)

        result = SessionManager.get_charger_status_by_id(
            chargers, "charger_nonexistent"
        )
        self.assertIsNone(result)

    def test_get_vehicle_status_by_id(self):
        vehicle1 = VehicleStatus(id="leaf", soc=50)
        vehicle2 = VehicleStatus(id="rav4", soc=30)
        vehicles = [vehicle1, vehicle2]

        result = SessionManager.get_vehicle_status_by_id("leaf", vehicles)
        self.assertEqual(result, vehicle1)

        result = SessionManager.get_vehicle_status_by_id("nonexistent", vehicles)
        self.assertIsNone(result)


class TestChargingSession(unittest.TestCase):
    def test_session_creation(self):
        session = ChargingSession(
            id="test-session-1",
            vehicle=None,
            charger=None,
        )
        self.assertEqual(session.id, "test-session-1")
        self.assertIsNone(session.vehicle)
        self.assertIsNone(session.charger)
        self.assertIsNone(session.start_timestamp)
        self.assertIsNone(session.stop_timestamp)


class TestSessionManagerConnectedCharger(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_connected_charger_not_connected(self):
        charger = FakeCharger(id="charger1")
        charger.connected = False

        self.manager.connected_charger(charger)

        self.assertEqual(len(self.manager.current_sessions), 0)

    def test_connected_charger_creates_session(self):
        charger = FakeCharger(id="charger1")
        charger.connected = True

        self.manager.connected_charger(charger)

        self.assertEqual(len(self.manager.current_sessions), 1)
        self.assertEqual(self.manager.current_sessions[0].charger.id, "charger1")

    def test_connected_charger_disconnected_stops_session(self):
        charger = FakeCharger(id="charger1")
        charger.connected = True

        self.manager.connected_charger(charger)
        self.assertEqual(len(self.manager.current_sessions), 1)

        callback = MagicMock()
        self.manager.add_on_session_stop_listener(callback)

        charger.connected = False
        self.manager.connected_charger(charger)

        # Session should get stop_timestamp set, trigger callback
        # Note: session remains in current_sessions until archive_sessions is called
        self.assertIsNotNone(self.manager.current_sessions[0].stop_timestamp)
        callback.assert_called_once()


class TestSessionManagerConnectedVehicle(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_connected_vehicle_not_connected(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=False)

        self.manager.connected_vehicle(vehicle)

        self.assertEqual(len(self.manager.current_sessions), 0)

    def test_connected_vehicle_creates_session(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)

        self.manager.connected_vehicle(vehicle)

        self.assertEqual(len(self.manager.current_sessions), 1)
        self.assertEqual(self.manager.current_sessions[0].vehicle.id, "leaf")

    def test_connected_vehicle_disconnects_stops_session(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)

        self.manager.connected_vehicle(vehicle)
        self.assertEqual(len(self.manager.current_sessions), 1)

        callback = MagicMock()
        self.manager.add_on_session_stop_listener(callback)

        # Create a new vehicle status with connected=False to simulate disconnect
        disconnected_vehicle = VehicleStatus(id="leaf", soc=50, connected=False)
        self.manager.connected_vehicle(disconnected_vehicle)

        # Session should get stop_timestamp set, trigger callback
        # Note: session remains in current_sessions until archive_sessions is called
        self.assertIsNotNone(self.manager.current_sessions[0].stop_timestamp)
        callback.assert_called_once()


class TestSessionManagerGetSession(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_get_session_by_vehicle_found(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)
        session = ChargingSession(
            id="session1",
            vehicle=vehicle,
            charger=None,
        )
        self.manager.current_sessions.append(session)

        result = self.manager.get_session_by_vehicle("leaf")
        self.assertEqual(result, session)

    def test_get_session_by_vehicle_not_found(self):
        result = self.manager.get_session_by_vehicle("nonexistent")
        self.assertIsNone(result)

    def test_get_session_by_charger_found(self):
        charger = FakeCharger(id="charger1")
        session = ChargingSession(
            id="session1",
            vehicle=None,
            charger=charger,
        )
        self.manager.current_sessions.append(session)

        result = self.manager.get_session_by_charger("charger1")
        self.assertEqual(result, session)

    def test_get_session_by_charger_not_found(self):
        result = self.manager.get_session_by_charger("nonexistent")
        self.assertIsNone(result)


class TestArchiveSessions(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_archive_completed_session(self):
        import datetime

        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)
        session = ChargingSession(
            id="session1",
            vehicle=vehicle,
            charger=None,
            stop_timestamp=datetime.datetime.now(),
        )
        self.manager.current_sessions.append(session)

        self.manager.archive_sessions()

        self.assertEqual(len(self.manager.current_sessions), 0)
        self.assertEqual(len(self.manager.session_history), 1)

    def test_archive_keeps_active_sessions(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)
        session = ChargingSession(
            id="session1",
            vehicle=vehicle,
            charger=None,
        )
        self.manager.current_sessions.append(session)

        self.manager.archive_sessions()

        self.assertEqual(len(self.manager.current_sessions), 1)
        self.assertEqual(len(self.manager.session_history), 0)


class TestTriggerListeners(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def test_trigger_session_start(self):
        callback = MagicMock()
        self.manager.add_on_session_start_listener(callback)

        session = ChargingSession(id="session1")
        self.manager._trigger_session_start(session)

        callback.assert_called_once_with(session)

    def test_trigger_session_stop(self):
        callback = MagicMock()
        self.manager.add_on_session_stop_listener(callback)

        session = ChargingSession(id="session1")
        self.manager._trigger_session_stop(session)

        callback.assert_called_once_with(session)

    def test_trigger_handles_exception(self):
        def raising_callback(session):
            raise ValueError("test error")

        self.manager.add_on_session_start_listener(raising_callback)

        session = ChargingSession(id="session1")
        # Should not raise
        self.manager._trigger_session_start(session)


if __name__ == "__main__":
    unittest.main()
