"""Price-aware charging planner."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import List, Optional

from smart_charger.config import ChargerConfiguration
from smart_charger.vehicle import VehicleStatus

from .base import BasePlanner, PriceProvider
from .models import Candidate, ChargingPlan, ChargingStep, get_now

logger = logging.getLogger(__name__)


class PriceAwarePlanner(BasePlanner):
    """Planner that selects cheapest hours between now and the night window.

    Features:
    - Accepts a `price_provider` implementing `price_at(datetime) -> float`
    - Calculates energy required and greedily selects cheapest hour blocks
    - Builds contiguous ChargingStep blocks grouped by hour and current
    - Night hours (00:00-07:00) use 16A, day hours use 6A
    """

    def __init__(
        self,
        config: ChargerConfiguration,
        price_provider: Optional[PriceProvider] = None,
    ):
        self.config = config
        self.price_provider = price_provider

    def plan_charging(self, vehicle: VehicleStatus) -> ChargingPlan:
        """Create a charging plan optimized for lowest electricity price."""
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
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

        candidates = self._generate_candidates(night_start, night_end, now)
        self._select_candidates(candidates, planned_energy_kwh, night_start, night_end)

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
            "PriceAwarePlanner created plan with %d steps, energy %.2f kWh",
            len(steps),
            plan.total_energy_kwh,
        )
        return plan

    def _generate_candidates(
        self,
        night_start: datetime.datetime,
        night_end: datetime.datetime,
        now: datetime.datetime,
    ) -> List[Candidate]:
        """Generate candidate charging hours sorted by price.

        Creates hourly candidate slots from the next hour until the night window ends.
        Each candidate is enriched with electricity price and sorted by price (ascending).

        Args:
            night_start: Start of the night window (00:00).
            night_end: End of the night window (07:00).
            now: Current datetime used to determine the start hour.

        Returns:
            List of Candidate objects sorted by score (price), cheapest first.
        """
        start_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0 or now.microsecond > 0:
            start_hour += datetime.timedelta(hours=1)

        candidates: List[Candidate] = []
        cursor = start_hour
        while cursor < night_end:
            is_night = night_start <= cursor < night_end
            current = 16 if is_night else 6
            candidates.append(Candidate(dt=cursor, is_night=is_night, current=current))
            cursor += datetime.timedelta(hours=1)

        for cand in candidates:
            price = (
                self.price_provider.price_at(cand.dt) if self.price_provider else 0.0
            )
            cand.price = price
            cand.score = price

        candidates.sort(
            key=lambda c: (c.score if c.score is not None else float("inf"))
        )
        return candidates

    def _select_candidates(
        self,
        candidates: List[Candidate],
        planned_energy_kwh: float,
        night_start: datetime.datetime,
        night_end: datetime.datetime,
    ) -> None:
        """Select candidates to fulfill the required energy.

        First pass: selects cheapest candidates (already sorted by price) until
        the required energy is met.

        Second pass: if more energy is needed, selects remaining candidates in
        chronological order (preferring night hours with 16A current).

        Args:
            candidates: List of Candidate objects. Modified in place.
            planned_energy_kwh: Total energy needed in kWh.
            night_start: Start of night window for determining 16A vs 6A current.
            night_end: End of night window for determining 16A vs 6A current.
        """
        accumulated_energy = 0.0
        for cand in candidates:
            hour_energy = self._get_energy(cand.current, 1)
            cand.chosen = True
            accumulated_energy += hour_energy
            if accumulated_energy >= planned_energy_kwh:
                break

        if accumulated_energy < planned_energy_kwh:
            for cand in candidates:
                if cand.chosen:
                    continue
                current = 16 if (night_start <= cand.dt < night_end) else 6
                hour_energy = self._get_energy(current, 1)
                cand.chosen = True
                accumulated_energy += hour_energy
                if accumulated_energy >= planned_energy_kwh:
                    break

    @staticmethod
    def _group_candidates_into_steps(
        chosen_hours: List[Candidate],
    ) -> List[ChargingStep]:
        """Group chosen candidates into contiguous charging steps.

        Adjacent hours with the same current are combined into a single
        ChargingStep. The mean price is calculated for each step.

        Args:
            chosen_hours: List of Candidate objects sorted chronologically.

        Returns:
            List of ChargingStep objects representing contiguous charging blocks.
        """
        steps: List[ChargingStep] = []
        if not chosen_hours:
            return steps

        block_start = chosen_hours[0].dt
        block_current = chosen_hours[0].current
        block_prices: List[float] = (
            [chosen_hours[0].price] if chosen_hours[0].price is not None else []
        )
        block_end = block_start + datetime.timedelta(hours=1)

        for h in chosen_hours[1:]:
            if h.current == block_current and h.dt == block_end:
                if h.price is not None:
                    block_prices.append(h.price)
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
                        description="Price-aware block",
                        mean_price=block_price,
                    )
                )
                block_start = h.dt
                block_current = h.current
                block_prices = [h.price] if h.price is not None else []
                block_end = h.dt + datetime.timedelta(hours=1)

        block_price = sum(block_prices) / len(block_prices) if block_prices else None
        steps.append(
            ChargingStep(
                id=str(uuid.uuid4()),
                start_time=block_start,
                stop_time=block_end,
                current=block_current,
                description="Price-aware block",
                mean_price=block_price,
            )
        )
        return steps
