"""Simple time-based planners."""

from __future__ import annotations

import datetime
import logging
import math
import uuid
from typing import List

from smart_charger.config import ChargerConfiguration
from smart_charger.vehicle import VehicleStatus

from .base import BasePlanner
from .models import ChargingPlan, ChargingStep, get_now

logger = logging.getLogger(__name__)


class HourlyPlanner(BasePlanner):
    """Legacy planner that schedules charging in the night window.

    Deprecated: Consider using SimpleHourPlanner or PriceAwarePlanner instead.
    """

    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus) -> ChargingPlan:
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
        planned_charge_hours = self.get_charge_hours(planned_energy_kwh)

        now = get_now()
        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=now + datetime.timedelta(hours=planned_charge_hours),
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=planned_charge_hours,
            steps=[],
        )

        if planned_charge_hours <= 7:
            plan.steps.append(
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("00:00")
                    + datetime.timedelta(hours=7 - planned_charge_hours),
                    stop_time=self._get_timestamp_from_hour("07:00"),
                    current=16,
                    description="Nightly full charge",
                )
            )
        elif planned_charge_hours > 7:
            plan.steps.append(
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("00:00")
                    + datetime.timedelta(days=1),
                    stop_time=self._get_timestamp_from_hour("07:00")
                    + datetime.timedelta(days=1),
                    current=16,
                    description="Nightly full charge",
                )
            )

            rest = planned_energy_kwh - plan.total_energy_kwh
            remaining_hours = math.ceil(self.get_charge_hours(rest, 6))
            plan.steps.append(
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("00:00")
                    - datetime.timedelta(hours=remaining_hours),
                    stop_time=self._get_timestamp_from_hour("00:00")
                    + datetime.timedelta(days=1),
                    current=6,
                    description="Evening charge",
                )
            )

        return plan


class BasicPlanner(BasePlanner):
    """Basic planner with hardcoded charging schedule.

    Deprecated: This is for testing purposes only.
    """

    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus) -> ChargingPlan:
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
        planned_charge_hours = self.get_charge_hours(planned_energy_kwh)

        now = get_now()
        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=now + datetime.timedelta(hours=planned_charge_hours),
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=planned_charge_hours,
            steps=[
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("20:27"),
                    stop_time=self._get_timestamp_from_hour("23:13"),
                    current=6,
                    description="Evening charge",
                ),
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("23:13"),
                    stop_time=self._get_timestamp_from_hour("23:15"),
                    current=8,
                    description="test",
                ),
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("00:00", 1),
                    stop_time=self._get_timestamp_from_hour("06:00", 1),
                    current=10,
                    description="Nightly charge",
                ),
            ],
        )
        logger.warning(f"Plan: {plan}")

        return plan


class SimpleHourPlanner(BasePlanner):
    """Schedule integer hours between now and next day's 07:00.

    Rules:
    - Night window: next day's 00:00..07:00 uses 16A
    - Other times use 6A
    - Prioritize filling night window first when hours are limited
    """

    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus) -> ChargingPlan:
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
        planned_charge_hours = int(self.get_charge_hours(planned_energy_kwh))

        now = get_now()
        # Choose the night window to prioritize:
        # - If it's currently before 07:00, prioritize the current day's 00:00..07:00
        # - Otherwise, prioritize the next day's 00:00..07:00
        if now.hour < 7:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=0)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=0)
        else:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=1)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=1)

        # Total available hours between now and night_end
        total_available_seconds = max(0.0, (night_end - now).total_seconds())
        total_available_hours = math.ceil(total_available_seconds / 3600)

        # Compute available night hours (portion of night window after now)
        if night_end <= now:
            night_available_seconds = 0.0
        else:
            night_available_seconds = max(
                0.0, (night_end - max(now, night_start)).total_seconds()
            )
        night_available_hours = math.ceil(night_available_seconds / 3600)

        # We cannot schedule more hours than available
        hours_to_schedule = min(planned_charge_hours, total_available_hours)

        steps: List[ChargingStep] = []

        # Allocate night hours first (latest hours in night window ending at 07:00)
        if hours_to_schedule > 0 and night_available_hours > 0:
            night_hours = min(hours_to_schedule, night_available_hours)
            night_block_start = night_end - datetime.timedelta(hours=night_hours)
            if night_block_start < now:
                night_block_start = now
            steps.append(
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=night_block_start,
                    stop_time=night_end
                    if night_block_start < night_end
                    else night_block_start + datetime.timedelta(hours=1),
                    current=16,
                    description="Nightly prioritized charge",
                )
            )
            hours_to_schedule -= night_hours

        # Allocate remaining hours before the night window
        if hours_to_schedule > 0:
            before_night_seconds = max(0.0, (night_start - now).total_seconds())
            before_night_hours = math.ceil(before_night_seconds / 3600)
            day_hours = min(hours_to_schedule, before_night_hours)
            if day_hours > 0:
                day_block_end = min(
                    night_start, now + datetime.timedelta(hours=day_hours)
                )
                day_block_start = day_block_end - datetime.timedelta(hours=day_hours)
                if day_block_start < now:
                    day_block_start = now
                    day_block_end = now + datetime.timedelta(hours=day_hours)
                steps.append(
                    ChargingStep(
                        id=str(uuid.uuid4()),
                        start_time=day_block_start,
                        stop_time=day_block_end,
                        current=6,
                        description="Daytime charge",
                    )
                )
                hours_to_schedule -= day_hours

        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=night_end,
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=planned_charge_hours,
            steps=steps,
        )
        return plan
