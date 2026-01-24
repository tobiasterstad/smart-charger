import datetime
import math
import unittest
from unittest.mock import patch

import pytest

from smart_charger import planner
from smart_charger.config import ChargerConfiguration
from smart_charger.planner import SimpleHourPlanner, VehicleStatus

class TestPlanner(unittest.TestCase):

    def set_now(self, monkeypatch, fixed_dt: datetime.datetime):
        # Replace basicplanner.datetime.datetime with a subclass whose now() returns fixed_dt
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_dt

        monkeypatch.setattr(planner.datetime, 'datetime', FixedDateTime)


    @patch('')
    def test_simple_planner_prioritizes_night_when_enough_time(self, monkeypatch):
        # now = 2026-01-22 20:00 -> full night window next day is available (7h)
        fixed_dt = datetime.datetime(2026, 1, 22, 20, 0)
        self.set_now(monkeypatch, fixed_dt)

        config = ChargerConfiguration.load_defaults()
        planner = SimpleHourPlanner(config)

        # vehicle needs about 12 kWh (leaf default: capacity 40, target 80, default soc 50 in tests)
        vehicle = VehicleStatus(id='leaf', soc=50)

        plan = planner.plan_charging(vehicle)

        # Using the existing config, this should result in 4 planned hours at 16A in the night
        assert plan.steps, "Expected at least one step"
        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.current == 16
        duration_hours = (step.stop_time - step.start_time).total_seconds() / 3600
        assert math.isclose(duration_hours, 4, rel_tol=0.2)
        assert step.stop_time.hour == 7


    def test_simple_planner_limited_time_prioritizes_night(self, monkeypatch):
        # now inside night window (2026-01-23 05:00), only 2 hours until 07:00
        fixed_dt = datetime.datetime(2026, 1, 23, 5, 0)
        self.set_now(monkeypatch, fixed_dt)

        config = ChargerConfiguration.load_defaults()
        planner = SimpleHourPlanner(config)

        # Make vehicle require many hours so we exceed available time
        vehicle = VehicleStatus(id='leaf', soc=0)

        plan = planner.plan_charging(vehicle)

        # Only 2 hours are available until 07:00; planner should allocate those with 16A
        assert plan.steps, "Expected at least one step"
        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.current == 16
        duration_hours = (step.stop_time - step.start_time).total_seconds() / 3600
        assert math.isclose(duration_hours, 2, rel_tol=0.2)


    def test_simple_planner_day_and_night_split(self, monkeypatch):
        # now = 2026-01-22 18:00, many hours available; expect night prioritized then daytime hours
        fixed_dt = datetime.datetime(2026, 1, 22, 18, 0)
        self.set_now(monkeypatch, fixed_dt)

        config = ChargerConfiguration.load_defaults()
        planner = SimpleHourPlanner(config)

        # Force large required energy
        vehicle = VehicleStatus(id='leaf', soc=0)

        plan = planner.plan_charging(vehicle)

        # Because we need many hours, planner should create a night block (7h @16A) and a daytime block (remaining hours @6A)
        assert plan.steps, "Expected at least one step"
        assert len(plan.steps) >= 1

        # Night block should be first and use 16A
        night_step = plan.steps[0]
        assert night_step.current == 16
        night_duration = (night_step.stop_time - night_step.start_time).total_seconds() / 3600
        assert math.isclose(night_duration, 7, rel_tol=0.2)

        # If there's a second step, it should be daytime at 6A
        if len(plan.steps) > 1:
            day_step = plan.steps[1]
            assert day_step.current == 6


    def test_simple_planner_zero_energy(self, monkeypatch):
        # If vehicle already at target SOC, planner should return empty steps
        fixed_dt = datetime.datetime(2026, 1, 22, 12, 0)
        self.set_now(monkeypatch, fixed_dt)

        config = ChargerConfiguration.load_defaults()
        planner = SimpleHourPlanner(config)

        # Create vehicle at target SOC
        vehicle_config = config.get_vehicle_config_by_id('leaf')
        vehicle = VehicleStatus(id='leaf', soc=vehicle_config.target_soc)

        plan = planner.plan_charging(vehicle)
        assert plan.steps == []
