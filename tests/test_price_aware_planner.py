import datetime
import random
import unittest
from typing import List
from unittest import mock

import pytest

from smart_charger.planner import models as planner_models
from smart_charger.planner import base as planner_base
from smart_charger.planner import price as planner_price
from smart_charger.secrets import Secrets
from smart_charger.config import ChargerConfiguration
from smart_charger.planner import PriceAwarePlanner, VehicleStatus
from smart_charger.tibber.tibber_util import (
    TibberConfig,
    TibberPrices,
    Prices,
    Data,
    Viewer,
    Home,
    CurrentSubscription,
    PriceData,
    PriceInfo,
)
from smart_charger.price_providers import TibberPriceProvider


class SimpleTariffProvider:
    def __init__(self, cheap_hours: List[int]):
        self.cheap_hours = set(cheap_hours)

    def price_at(self, dt: datetime.datetime) -> float:
        return 0.1 if dt.hour in self.cheap_hours else 1.0


class TestPriceAwarePlanner(unittest.TestCase):
    def setUp(self):
        # manage active patchers
        self._patchers = []

    def tearDown(self):
        for p in reversed(self._patchers):
            try:
                p.stop()
            except Exception:
                pass
        self._patchers = []

    def set_now(self, fixed_dt: datetime.datetime):
        # Patch get_now in ALL modules where it's imported
        # Use default arg to capture value, not reference
        for module in [planner_models, planner_base, planner_price]:
            p = mock.patch.object(module, "get_now", lambda dt=fixed_dt: dt)
            p.start()
            self._patchers.append(p)

    def _count_hours_in_steps(
        self, steps: List[planner.ChargingStep], current: int
    ) -> float:
        return sum(
            (s.stop_time - s.start_time).total_seconds() / 3600
            for s in steps
            if s.current == current
        )

    def test_price_aware_picks_night_hours_when_cheaper(self):
        # now = 2026-01-22 18:30
        fixed_dt = datetime.datetime(2026, 1, 22, 18, 30)
        self.set_now(fixed_dt)

        config = ChargerConfiguration.load_defaults()
        # make night hours (0-6) cheap
        provider = SimpleTariffProvider(list(range(0, 7)))
        planner_obj = PriceAwarePlanner(config, price_provider=provider)

        vehicle = VehicleStatus(id="leaf", soc=50)
        plan = planner_obj.plan_charging(vehicle)

        # Ensure planner produced some hours and that total energy meets or exceeds the requested
        assert plan.charge_hours > 0
        assert plan.total_energy_kwh >= plan.energy_kwh

        # Count night vs day hours in the produced steps (night defined as hour in 0..6)
        night_hours = 0
        day_hours = 0
        for step in plan.steps:
            cursor = step.start_time
            while cursor < step.stop_time:
                if 0 <= cursor.hour <= 6:
                    night_hours += 1
                else:
                    day_hours += 1
                cursor += datetime.timedelta(hours=1)

        # With cheap night prices, the planner should prefer night hours (at least as many as day hours)
        assert night_hours >= day_hours

    def test_price_aware_groups_adjacent_hours(self):
        # now = 2026-01-22 21:10 -> start hour 22:00
        fixed_dt = datetime.datetime(2026, 1, 22, 21, 10)
        self.set_now(fixed_dt)

        config = ChargerConfiguration.load_defaults()
        # make a run of cheap consecutive hours 22,23,0,1,2
        provider = SimpleTariffProvider([22, 23, 0, 1, 2])
        planner_obj = PriceAwarePlanner(config, price_provider=provider)

        # Vehicle needs around 4 hours (as in previous test)
        vehicle = VehicleStatus(id="leaf", soc=50)
        plan = planner_obj.plan_charging(vehicle)

        # All chosen hours should be among the cheap set; and because they are consecutive
        # they should be grouped into a single ChargingStep (or at most 2 if crossing midnight handled)
        assert plan.steps, "Expected at least one step"
        # group count reasonable (1 or 2 depending on midnight boundary)
        assert len(plan.steps) <= 2

        # Confirm chosen hours are cheap
        for step in plan.steps:
            # iter each hour in step
            cursor = step.start_time
            while cursor < step.stop_time:
                assert cursor.hour in provider.cheap_hours
                cursor += datetime.timedelta(hours=1)

    def test_price_aware_fallback_no_provider(self):
        # When tariff provider is None, PriceAwarePlanner should still return a plan and
        # prefer night hours (tiny night bias) — ensure energy coverage
        fixed_dt = datetime.datetime(2026, 1, 22, 19, 45)
        self.set_now(fixed_dt)

        config = ChargerConfiguration.load_defaults()
        planner_obj = PriceAwarePlanner(config, price_provider=None)

        vehicle = VehicleStatus(id="leaf", soc=50)
        plan = planner_obj.plan_charging(vehicle)

        assert plan.charge_hours > 0
        assert plan.total_energy_kwh >= plan.energy_kwh

    def test_price_aware_not_enough_hours(self):
        # If there are fewer candidate hours than required, planner should schedule all candidates
        # Choose now late so only small number of candidate hours are available
        fixed_dt = datetime.datetime(
            2026, 1, 23, 6, 30
        )  # only 0.5h until 07:00 -> start_hour = 7:00 -> zero candidates before night_end
        self.set_now(fixed_dt)

        config = ChargerConfiguration.load_defaults()
        provider = SimpleTariffProvider([0, 1, 2, 3, 4, 5, 6])
        planner_obj = PriceAwarePlanner(config, price_provider=provider)

        vehicle = VehicleStatus(id="leaf", soc=0)  # large demand
        plan = planner_obj.plan_charging(vehicle)

        # compute expected candidate count using same logic as planner
        from smart_charger.planner import BasePlanner, get_now

        now = get_now()
        if now.hour < 7:
            night_start = BasePlanner._get_timestamp_from_hour(
                "00:00", increment_days=0
            )
            night_end = BasePlanner._get_timestamp_from_hour("07:00", increment_days=0)
        else:
            night_start = BasePlanner._get_timestamp_from_hour(
                "00:00", increment_days=1
            )
            night_end = BasePlanner._get_timestamp_from_hour("07:00", increment_days=1)

        start_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0 or now.microsecond > 0:
            start_hour += datetime.timedelta(hours=1)

        candidates = []
        cursor = start_hour
        while cursor < night_end:
            candidates.append(cursor)
            cursor += datetime.timedelta(hours=1)

        # planner should select <= len(candidates) hours; if not enough energy then all candidates
        assert plan.charge_hours <= max(0, len(candidates))

        # If no candidates, ensure plan.steps is empty
        if len(candidates) == 0:
            assert plan.steps == []

    @pytest.mark.integration
    def test_tibber2(self):
        vehicle = VehicleStatus(id="leaf", soc=50, connected=True)
        config = ChargerConfiguration.load_defaults()
        secrets = Secrets()
        tibber_config = TibberConfig(api_key=secrets.tibber_api_key)
        tibber_tariff_provider = TibberPriceProvider(tibber_config)
        test_planner = PriceAwarePlanner(config, price_provider=tibber_tariff_provider)
        plan = test_planner.plan_charging(vehicle)
        print(plan)

    def test_planner_for_many_hours(self):
        vehicle = VehicleStatus(id="leaf", soc=1, connected=True)
        config = ChargerConfiguration.load_defaults()

        today = []
        for hour in [20, 21, 22, 23]:
            ts = datetime.datetime.now()
            total = (random.random() * 2) / 10
            ts.replace(hour=hour, minute=0, second=0, microsecond=0)
            p = PriceInfo(startsAt=ts, total=total, energy=0, tax=0)
            today.append(p)

        tomorrow = []
        for hour in [0, 1, 2, 3, 4, 5, 6]:
            ts = datetime.datetime.now()
            total = (random.random()) / 10
            ts.replace(hour=hour, minute=0, second=0, microsecond=0)
            p = PriceInfo(startsAt=ts, total=0, energy=0, tax=0)
            tomorrow.append(p)
        prices = Prices(
            data=Data(
                viewer=Viewer(
                    homes=[
                        Home(
                            currentSubscription=CurrentSubscription(
                                priceInfo=PriceData(today=today, tomorrow=tomorrow)
                            )
                        )
                    ]
                )
            )
        )

        tibber_cfg = TibberConfig(api_key="dummy")
        with mock.patch.object(TibberPrices, "today_tomorrow", return_value=prices):
            tibber_tariff_provider = TibberPriceProvider(tibber_cfg)
            test_planner = PriceAwarePlanner(
                config, price_provider=tibber_tariff_provider
            )
            plan = test_planner.plan_charging(vehicle)
