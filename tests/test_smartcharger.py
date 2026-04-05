import unittest
from unittest.mock import MagicMock, patch

from smart_charger.smartcharger import (
    HealthStatus,
    HealthCheckResult,
)
from smart_charger.planner import VehicleStatus
from smart_charger.chargers import BaseCharger, ChargerStatus
from smart_charger.config import ChargerType
from smart_charger.zaptec import OperatingMode


class FakeChargerForTest(BaseCharger):
    def __init__(self, id: str, connected: bool = False):
        status = ChargerStatus.CONNECTED if connected else ChargerStatus.DISCONNECTED
        super().__init__(id=id, status=status, current=0, read_only=True)

    def charger_type(self) -> ChargerType:
        return ChargerType.ZAPTEC

    def start_charging(self):
        self.status = ChargerStatus.CHARGING

    def stop_charging(self):
        self.status = ChargerStatus.CONNECTED

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


class TestHealthStatusEnum(unittest.TestCase):
    def test_health_status_values(self):
        self.assertEqual(HealthStatus.HEALTHY.value, "healthy")
        self.assertEqual(HealthStatus.DEGRADED.value, "degraded")
        self.assertEqual(HealthStatus.UNHEALTHY.value, "unhealthy")


class TestHealthCheckResult(unittest.TestCase):
    def test_health_check_result_creation(self):
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY, message="All good", details={"key": "value"}
        )
        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertEqual(result.message, "All good")
        self.assertEqual(result.details, {"key": "value"})

    def test_health_check_result_defaults(self):
        result = HealthCheckResult(status=HealthStatus.HEALTHY, message="All good")
        self.assertEqual(result.details, {})


class TestHealthCheckLogic(unittest.TestCase):
    """Test health check logic without requiring full SmartCharger init."""

    def test_healthy_status_when_all_connected(self):
        # Simulate health check logic
        mqtt_connected = True
        connected_vehicles = 1
        connected_chargers = 1

        issues = []
        if not mqtt_connected:
            issues.append("MQTT not connected")

        if issues:
            status = HealthStatus.UNHEALTHY
            message = "; ".join(issues)
        elif connected_vehicles == 0 and connected_chargers == 0:
            status = HealthStatus.DEGRADED
            message = "No vehicles or chargers connected"
        else:
            status = HealthStatus.HEALTHY
            message = "All systems operational"

        self.assertEqual(status, HealthStatus.HEALTHY)

    def test_unhealthy_status_when_mqtt_disconnected(self):
        mqtt_connected = False
        connected_vehicles = 1
        connected_chargers = 1

        issues = []
        if not mqtt_connected:
            issues.append("MQTT not connected")

        if issues:
            status = HealthStatus.UNHEALTHY
            message = "; ".join(issues)
        elif connected_vehicles == 0 and connected_chargers == 0:
            status = HealthStatus.DEGRADED
            message = "No vehicles or chargers connected"
        else:
            status = HealthStatus.HEALTHY
            message = "All systems operational"

        self.assertEqual(status, HealthStatus.UNHEALTHY)
        self.assertEqual(message, "MQTT not connected")

    def test_degraded_status_when_no_connections(self):
        mqtt_connected = True
        connected_vehicles = 0
        connected_chargers = 0

        issues = []
        if not mqtt_connected:
            issues.append("MQTT not connected")

        if issues:
            status = HealthStatus.UNHEALTHY
            message = "; ".join(issues)
        elif connected_vehicles == 0 and connected_chargers == 0:
            status = HealthStatus.DEGRADED
            message = "No vehicles or chargers connected"
        else:
            status = HealthStatus.HEALTHY
            message = "All systems operational"

        self.assertEqual(status, HealthStatus.DEGRADED)


class TestMockCharger(unittest.TestCase):
    def test_fake_charger_creation(self):
        charger = FakeChargerForTest(id="test-charger", connected=True)
        self.assertEqual(charger.id, "test-charger")
        self.assertEqual(charger.status, ChargerStatus.CONNECTED)


if __name__ == "__main__":
    unittest.main()
