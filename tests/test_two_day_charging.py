import datetime
import unittest
import unittest.mock
from typing import Dict

from smart_charger import planner
from smart_charger.config import ChargerConfiguration
from smart_charger.solar_providers import MQTTSolarProvider, SolarPriceProvider


class SimpleTariffProvider:
    def __init__(self, price_by_hour: Dict[int, float]):
        self.price_by_hour = price_by_hour

    def price_at(self, dt: datetime.datetime) -> float:
        return self.price_by_hour.get(dt.hour, 1.0)


class TestTwoDayChargingScenario(unittest.TestCase):
    def setUp(self):
        self._patchers = []

    def tearDown(self):
        for p in reversed(self._patchers):
            try:
                p.stop()
            except Exception:
                pass
        self._patchers = []

    def set_now(self, fixed_dt: datetime.datetime):
        p = unittest.mock.patch.object(planner, "get_now", lambda: fixed_dt)
        p.start()
        self._patchers.append(p)

    def test_two_day_charging_scenario(self):
        price_by_hour = {
            0: 0.1,
            1: 0.1,
            2: 0.1,
            3: 0.1,
            4: 0.1,
            5: 0.1,
            6: 0.1,
            7: 1.0,
            8: 1.0,
            9: 1.0,
            10: 1.0,
            11: 1.0,
            12: 1.0,
            13: 1.0,
            14: 1.0,
            15: 1.0,
            16: 1.0,
            17: 1.0,
            18: 2.0,
            19: 2.0,
            20: 2.0,
            21: 2.0,
            22: 2.0,
            23: 2.0,
        }
        tariff_provider = SimpleTariffProvider(price_by_hour)

        solar_profile = {hour: 0 for hour in range(24)}
        solar_profile[12] = 3000
        solar_profile[13] = 3000
        solar_profile[14] = 3000
        solar_provider = MQTTSolarProvider(default_production_profile=solar_profile)

        config = ChargerConfiguration.load_defaults()

        day1_evening = datetime.datetime(2026, 2, 13, 18, 12)
        self.set_now(day1_evening)

        vehicle = planner.VehicleStatus(id="leaf", soc=20, connected=True)

        planner_obj = planner.PriceAwarePlanner(config, price_provider=tariff_provider)
        plan = planner_obj.plan_charging(vehicle)

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

        assert night_hours > 0, "Should select night hours (0-6) when they're cheapest"
        assert night_hours >= day_hours, "Should prefer night hours over day hours"

        day2_midday = datetime.datetime(2026, 2, 14, 12, 0)
        self.set_now(day2_midday)

        solar_price_provider = SolarPriceProvider(tariff_provider, solar_provider)

        midday_price = solar_price_provider.price_at(day2_midday)
        assert midday_price < 0.5, "Solar should make midday price very cheap"

        night_price = solar_price_provider.price_at(
            datetime.datetime(2026, 2, 14, 2, 0)
        )
        assert night_price == 0.1, "Night price should be unchanged (no solar benefit)"

        self.set_now(day2_midday)
        planner_with_solar = planner.PriceAwarePlanner(
            config, price_provider=solar_price_provider
        )
        plan_with_solar = planner_with_solar.plan_charging(vehicle)

        solar_hours = 0
        for step in plan_with_solar.steps:
            cursor = step.start_time
            while cursor < step.stop_time:
                if 12 <= cursor.hour <= 14:
                    solar_hours += 1
                cursor += datetime.timedelta(hours=1)

        assert solar_hours > 0, (
            "Should include solar hours (12-14) when solar is available"
        )

        day2_night = datetime.datetime(2026, 2, 14, 22, 0)
        self.set_now(day2_night)

        planner_night = planner.PriceAwarePlanner(
            config, price_provider=tariff_provider
        )
        plan_night = planner_night.plan_charging(vehicle)

        night_hours_final = 0
        for step in plan_night.steps:
            cursor = step.start_time
            while cursor < step.stop_time:
                if 0 <= cursor.hour <= 6:
                    night_hours_final += 1
                cursor += datetime.timedelta(hours=1)

        assert night_hours_final > 0, "Should select night hours for final charging"

        assert plan_night.target_soc == 80, "Target SOC should be 80%"

        vehicle_config = config.get_vehicle_config_by_id("leaf")
        energy_needed = (
            (vehicle_config.target_soc - vehicle.soc)
            / 100
            * (vehicle_config.capacity_kwh or 62)
        )
        assert plan_night.energy_kwh >= energy_needed * 0.9, (
            f"Plan should provide at least 90% of needed energy, "
            f"got {plan_night.energy_kwh} kWh, need {energy_needed} kWh"
        )


if __name__ == "__main__":
    unittest.main()
