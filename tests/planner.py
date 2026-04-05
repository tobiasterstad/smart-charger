import unittest
import datetime

from smart_charger.config import ChargerConfiguration
from smart_charger.planner import BasicPlanner, VehicleStatus


class TestPlanner(unittest.TestCase):
    def test_planner_initialization(self):
        config = ChargerConfiguration.load_defaults()

        planner = BasicPlanner(config)
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)
        plan = planner.plan_charging(vehicle)

        self.assertEqual(
            12.0, plan.energy_kwh
        )  # 80% target - 50% current = 30% of 40 kWh capacity
        self.assertEqual(80, plan.target_soc)

    def test_planned_energy_calculation(self):
        config = ChargerConfiguration.load_defaults()
        planner = BasicPlanner(config)

        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)

        plan = planner.plan_charging(vehicle)

        print(plan)

    def test_planned_energy_calculation_soc_23(self):
        config = ChargerConfiguration.load_defaults()
        planner = BasicPlanner(config)

        vehicle = VehicleStatus(id="leaf", soc=23, connected=True)
        plan = planner.plan_charging(vehicle)

        self.assertEqual(
            23, plan.energy_kwh
        )  # 80% target - 23% current = 57% of 40 kWh capacity

    def test_get_charge_hours(self):
        hours = BasicPlanner.get_charge_hours(23.0)
        self.assertEqual(7, hours)  # At 16A charging, 12 kWh requires 4 hours

    def test_get_charge_hours_at_10_amps(self):
        hours = BasicPlanner.get_charge_hours(23.0, current=10)
        self.assertEqual(10, hours)

    def test_energy_calculation(self):
        energy = BasicPlanner._get_energy(current=16, hours=1)
        self.assertAlmostEqual(
            3.68, energy, places=2
        )  # 16A * 230V * 1h / 1000 = 3.68 kWh

    def test_energy_calculation_multiple_hours(self):
        energy = BasicPlanner._get_energy(current=6, hours=3)
        self.assertAlmostEqual(4.14, energy)  # 6A * 230V * 3h / 1000 = 4.14 kWh

    def test_timestamp_from_hour(self):
        timestamp = BasicPlanner._get_timestamp_from_hour("18:30")

        now = datetime.datetime.now()
        expected_timestamp = now.replace(hour=18, minute=30, second=0, microsecond=0)
        if expected_timestamp < now:
            expected_timestamp += datetime.timedelta(days=1)

        self.assertEqual(expected_timestamp, timestamp)
