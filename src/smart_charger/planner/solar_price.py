"""Solar and price-aware charging planner."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import List, Optional

from smart_charger.config import ChargerConfiguration
from smart_charger.vehicle import VehicleStatus

from .base import BasePlanner, PriceProvider, SolarForecastProvider
from .models import ChargingPlan, ChargingStep, SolarCandidate, get_now

logger = logging.getLogger(__name__)


class SolarPriceAwarePlanner(BasePlanner):
    """Planner that combines solar production forecasts with electricity prices.

    This planner calculates an 'effective price' for each hour that accounts for
    the value of solar energy. Hours with high solar production have lower
    effective prices, making them more attractive for charging.

    Effective price calculation:
        effective_price = grid_price - solar_benefit
        solar_benefit = (solar_watts / 1000) * grid_price

    When solar production fully covers charging needs, effective price can be 0
    or even negative.

    The planner also adjusts charging current based on effective price:
    - When effective_price < solar_max_effective_price: use max current (16A)
    - Otherwise: use night current (16A) or day current (6A) based on time
    """

    def __init__(
        self,
        config: ChargerConfiguration,
        price_provider: Optional[PriceProvider] = None,
        solar_forecast_provider: Optional[SolarForecastProvider] = None,
    ):
        self.config = config
        self.price_provider = price_provider
        self.solar_forecast_provider = solar_forecast_provider

    def plan_charging(self, vehicle: VehicleStatus) -> ChargingPlan:
        """Create a charging plan that optimizes for solar + price.

        The plan prioritizes hours with the lowest effective price, which
        combines grid price with solar production benefits.
        """
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        if vehicle_config is None:
            raise ValueError(f"No vehicle config found for {vehicle.id}")

        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)

        if planned_energy_kwh <= 0:
            return ChargingPlan(
                vehicle_id=vehicle.id,
                start_time=get_now(),
                stop_time=get_now(),
                target_soc=vehicle_config.target_soc,
                energy_kwh=0,
                charge_hours=0,
                steps=[],
            )

        now = get_now()
        night_start, night_end = self._get_night_window(now)

        candidates = self._generate_solar_candidates(night_start, night_end, now)
        self._select_candidates(candidates, planned_energy_kwh)

        chosen_hours = [c for c in candidates if c.chosen]
        chosen_hours.sort(key=lambda c: c.dt)
        logger.debug(f"Chosen hours sorted: {chosen_hours}")

        steps = self._group_candidates_into_steps(chosen_hours)

        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=night_end,
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=len(chosen_hours),
            steps=steps,
        )

        logger.info(
            "SolarPriceAwarePlanner created plan with %d steps, energy %.2f kWh",
            len(steps),
            plan.total_energy_kwh,
        )
        return plan

    def _generate_solar_candidates(
        self,
        night_start: datetime.datetime,
        night_end: datetime.datetime,
        now: datetime.datetime,
    ) -> List[SolarCandidate]:
        """Generate candidate charging hours with solar and price data.

        Each candidate includes:
        - Grid price from price provider
        - Solar forecast from solar forecast provider
        - Effective price calculated from both
        - Optimal current based on effective price

        Candidates are sorted by effective price (cheapest first).
        """
        start_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0 or now.microsecond > 0:
            start_hour += datetime.timedelta(hours=1)

        candidates: List[SolarCandidate] = []
        cursor = start_hour

        while cursor < night_end:
            is_night = night_start <= cursor < night_end and 0 <= cursor.hour < 7

            # Get grid price
            grid_price = (
                self.price_provider.price_at(cursor) if self.price_provider else 0.5
            )

            # Get solar forecast
            solar_watts = (
                self.solar_forecast_provider.forecast_at(cursor)
                if self.solar_forecast_provider
                else 0.0
            )

            # Calculate effective price
            effective_price = self._calculate_effective_price(
                grid_price, solar_watts, cursor
            )

            # Determine current based on effective price
            current = self._determine_current(effective_price, is_night)

            candidates.append(
                SolarCandidate(
                    dt=cursor,
                    is_night=is_night,
                    current=current,
                    grid_price=grid_price,
                    solar_watts=solar_watts,
                    effective_price=effective_price,
                )
            )
            cursor += datetime.timedelta(hours=1)

        # Sort by effective price (cheapest first)
        candidates.sort(
            key=lambda c: (
                c.effective_price if c.effective_price is not None else float("inf")
            )
        )

        logger.debug(
            "Generated %d candidates, cheapest effective price: %.4f",
            len(candidates),
            candidates[0].effective_price if candidates else 0,
        )

        return candidates

    def _calculate_effective_price(
        self, grid_price: float, solar_watts: float, dt: datetime.datetime
    ) -> float:
        """Calculate effective price accounting for solar benefit.

        effective_price = grid_price - solar_benefit
        solar_benefit = (solar_watts / 1000) * grid_price

        This means:
        - 1 kW of solar at 0.50 EUR/kWh saves 0.50 EUR
        - 3 kW of solar at 0.50 EUR/kWh saves 1.50 EUR (price goes negative)
        """
        if solar_watts <= 0:
            return grid_price

        # Solar benefit in EUR/kWh (or your currency)
        # Each kW of solar production saves grid_price per kWh
        solar_kwh = solar_watts / 1000
        solar_benefit = solar_kwh * grid_price

        effective_price = grid_price - solar_benefit
        return round(effective_price, 4)

    def _determine_current(self, effective_price: float, is_night: bool) -> int:
        """Determine charging current based on effective price.

        When effective price is below the solar threshold, use max current.
        Otherwise, use time-based current (16A at night, 6A during day).
        """
        solar_max_effective_price = self.config.solar_max_effective_price

        # If effective price is very low (good solar), charge at max current
        if effective_price <= solar_max_effective_price:
            return 16

        # Otherwise, use standard day/night current
        return 16 if is_night else 6

    def _select_candidates(
        self,
        candidates: List[SolarCandidate],
        planned_energy_kwh: float,
    ) -> None:
        """Select candidates to fulfill the required energy.

        Greedily selects candidates with lowest effective price until
        the energy requirement is met.
        """
        accumulated_energy = 0.0
        for cand in candidates:
            hour_energy = self._get_energy(cand.current, 1)
            cand.chosen = True
            accumulated_energy += hour_energy
            if accumulated_energy >= planned_energy_kwh:
                break

    @staticmethod
    def _group_candidates_into_steps(
        chosen_hours: List[SolarCandidate],
    ) -> List[ChargingStep]:
        """Group chosen candidates into contiguous charging steps.

        Adjacent hours with the same current are combined into a single
        ChargingStep. The mean effective price is stored as mean_price.
        """
        steps: List[ChargingStep] = []
        if not chosen_hours:
            return steps

        block_start = chosen_hours[0].dt
        block_current = chosen_hours[0].current
        block_prices: List[float] = (
            [chosen_hours[0].effective_price]
            if chosen_hours[0].effective_price is not None
            else []
        )
        block_end = block_start + datetime.timedelta(hours=1)

        for h in chosen_hours[1:]:
            if h.current == block_current and h.dt == block_end:
                if h.effective_price is not None:
                    block_prices.append(h.effective_price)
                block_end += datetime.timedelta(hours=1)
            else:
                block_price = (
                    sum(block_prices) / len(block_prices) if block_prices else None
                )
                steps.append(
                    ChargingStep(
                        id=str(uuid.uuid4()),
                        start_time=block_start,
                        stop_time=block_end,
                        current=block_current,
                        description="Solar+price optimized",
                        mean_price=block_price,
                    )
                )
                block_start = h.dt
                block_current = h.current
                block_prices = (
                    [h.effective_price] if h.effective_price is not None else []
                )
                block_end = h.dt + datetime.timedelta(hours=1)

        block_price = sum(block_prices) / len(block_prices) if block_prices else None
        steps.append(
            ChargingStep(
                id=str(uuid.uuid4()),
                start_time=block_start,
                stop_time=block_end,
                current=block_current,
                description="Solar+price optimized",
                mean_price=block_price,
            )
        )
        return steps
