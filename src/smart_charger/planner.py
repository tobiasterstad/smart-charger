import abc
import datetime
import logging
import math
import uuid

from pydantic import BaseModel, Field

from smart_charger.config import ChargerConfiguration, VehicleConfig
from smart_charger.tibber.tibber_util import TibberPrices
from smart_charger.vehicle import VehicleStatus

logger = logging.getLogger(__name__)


# Helper to obtain current time; can be patched in tests without replacing datetime types
def get_now() -> datetime.datetime:
    return datetime.datetime.now()


class ChargingStep(BaseModel):
    id: str
    start_time: datetime.datetime
    stop_time: datetime.datetime
    current: int = Field(default=16, description="Charging current in Amperes")
    description: str
    solar_priority: bool = False
    solar_max_current: Optional[int] = None

    @property
    def energy_kwh(self) -> float:
        hours = (self.stop_time - self.start_time).total_seconds() / 3600
        current = self.solar_max_current if self.solar_priority and self.solar_max_current else self.current
        energy_kwh = (230 * current / 1000) * hours
        return energy_kwh

class ChargingPlan(BaseModel):
    vehicle_id: str
    start_time: datetime.datetime
    stop_time: datetime.datetime
    target_soc: int
    energy_kwh: float
    charge_hours: int
    steps: list[ChargingStep]
    active_step: Optional[ChargingStep] = None

    @property
    def total_energy_kwh(self) -> float:
        return sum(step.energy_kwh for step in self.steps)

    def get_charging_step(self, timestamp: Optional[datetime.datetime] = None, solar_priority=False) -> Optional[ChargingStep]:
        if not timestamp:
            timestamp = get_now()
        for step in self.steps:
            if step.start_time <= timestamp <= step.stop_time and step.solar_priority == solar_priority:
                return step
        return None


class BasePlanner(abc.ABC):
    def plan_charging(self, vehicle: VehicleStatus):
        # Things to consider:
        # - Time of day
        # - Energy prices
        # - Solar energy availability
        # - Vehicle usage patterns
        # - Grid constraints, high load periods
        # - User preferences
        #   - Charge to 80% on all days
        #   - Charge to 100% now
        #   - Charge to 100% for tomorrow morning
        # - SOC

        pass

    @staticmethod
    def _get_timestamp_from_hour(time: str, increment_days: int = 0) -> datetime.datetime:
        now = get_now()
        hour, minute = map(int, time.split(":"))
        planned_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        planned_time += datetime.timedelta(days=increment_days)
        return planned_time

    @staticmethod
    def _get_timestamp_hours_from_now(hours: int) -> datetime.datetime:
        return get_now() + datetime.timedelta(hours=hours)

    @staticmethod
    def _get_planned_energy(vehicle: VehicleStatus, vehicle_config: VehicleConfig) -> float:
        charge = vehicle_config.target_soc - vehicle.soc
        planned_energy_kwh = (charge / 100) * (vehicle_config.capacity_kwh or 0)
        logger.info("Planning charging for vehicle %s: current SOC %d%%, target SOC %d%%, planned energy %.2f kWh",
                    vehicle.id, vehicle.soc, vehicle_config.target_soc, planned_energy_kwh)
        return math.ceil(planned_energy_kwh)

    @staticmethod
    def _get_energy(current, hours, voltage=230) -> float:
        # Current
        # U = V * I
        # Energy (kWh) = Power (kW) * Time (h)
        # Power (kW) = Voltage (V) * Current (A) / 1000
        # Current (A) = Energy (kWh) * 1000 / (Voltage (V) * Time (h))

        energy_kwh = (voltage * current / 1000) * hours
        return energy_kwh

    @staticmethod
    def get_charge_hours(planned_energy_kwh, current=16.0):
        """
        Calculate number of hours needed to charge
        planned_energy_kwh: float - Planned energy in kWh
        current: float - Charging current in Amperes
        """
        effect = (230 * current) / 1000  # kW
        planned_charge_hours = math.ceil(planned_energy_kwh / effect)
        return planned_charge_hours


class HourlyPlanner(BasePlanner):

    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus):
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
        planned_charge_hours = self.get_charge_hours(planned_energy_kwh)


        # Find planned_charge_hours hours, from now until 07:00 tomorrow for charging.
        # Between 00:00 to 07:00 the current should be 16A
        # All other times, the current should be 6A
        # It is possible that there is not enough time to charge all hours.
        # If charging is quicker, prioritize the hours between 00:00 - 07:00.

        now = get_now()
        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=now + datetime.timedelta(hours=planned_charge_hours),
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=planned_charge_hours,
            steps=[]
        )

        if planned_charge_hours <= 7:
            plan.steps.append(ChargingStep(
                id=str(uuid.uuid4()),
                start_time=self._get_timestamp_from_hour("00:00") + datetime.timedelta(hours=7-planned_charge_hours),
                stop_time=self._get_timestamp_from_hour("07:00"),
                current=16,
                description=f"Nightly full charge"
            ))
        elif planned_charge_hours > 7:
            plan.steps.append(ChargingStep(
                id=str(uuid.uuid4()),
                start_time=self._get_timestamp_from_hour("00:00") + datetime.timedelta(days=1),
                stop_time=self._get_timestamp_from_hour("07:00") + datetime.timedelta(days=1),
                current=16,
                description=f"Nightly full charge"
            ))

            rest = planned_energy_kwh - plan.total_energy_kwh
            remaining_hours = math.ceil(self.get_charge_hours(rest, 6))
            plan.steps.append(ChargingStep(
                id=str(uuid.uuid4()),
                start_time=self._get_timestamp_from_hour("00:00") - datetime.timedelta(hours=remaining_hours),
                stop_time=self._get_timestamp_from_hour("00:00") + datetime.timedelta(days=1),
                current=6,
                description=f"Evening charge"
            ))

        return plan


class BasicPlanner(BasePlanner):
    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus):
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
                # ChargingStep(
                #     description="Solar charging prioritized",
                #     start_time=datetime.datetime.now(),
                #     end_time=self._get_timestamp_from_hour("18:00"),
                #     solar_priority=True,
                #     solar_max_current=6
                # ),
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("20:27"),
                    stop_time=self._get_timestamp_from_hour("23:13"),
                    current=6,
                    description=f"Evening charge"
                ),
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("23:13"),
                    stop_time=self._get_timestamp_from_hour("23:15"),
                    current=8,
                    description="test"
                ),
                ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=self._get_timestamp_from_hour("00:00", 1),
                    stop_time=self._get_timestamp_from_hour("06:00", 1),
                    current=10,
                    description=f"Nightly charge"
                )
            ]
        )
        logger.warning(f"Plan: {plan}")

        return plan


# New SimpleHourPlanner implementation
class SimpleHourPlanner(BasePlanner):
    """Schedule integer hours between now and next day's 07:00.

    Rules:
    - Night window: next day's 00:00..07:00 uses 16A
    - Other times use 6A
    - Prioritize filling night window first when hours are limited
    """

    def __init__(self, config: ChargerConfiguration):
        self.config = config

    def plan_charging(self, vehicle: VehicleStatus):
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
        planned_charge_hours = int(self.get_charge_hours(planned_energy_kwh))

        now = get_now()
        # Choose the night window to prioritize:
        # - If it's currently before 07:00, prioritize the current day's 00:00..07:00 (remaining hours until 07:00)
        # - Otherwise, prioritize the next day's 00:00..07:00
        if now.hour < 7:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=0)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=0)
        else:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=1)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=1)

        # total available hours between now and night_end
        total_available_seconds = max(0.0, (night_end - now).total_seconds())
        total_available_hours = math.ceil(total_available_seconds / 3600)

        # compute available night hours (portion of the night window that occurs after now)
        if night_end <= now:
            night_available_seconds = 0.0
        else:
            night_available_seconds = max(0.0, (night_end - max(now, night_start)).total_seconds())
        night_available_hours = math.ceil(night_available_seconds / 3600)

        # we cannot schedule more hours than available
        hours_to_schedule = min(planned_charge_hours, total_available_hours)

        steps: list[ChargingStep] = []

        # allocate night hours first (take the latest hours in the night window ending at 07:00)
        if hours_to_schedule > 0 and night_available_hours > 0:
            night_hours = min(hours_to_schedule, night_available_hours)
            # place night block to end at night_end
            night_block_start = night_end - datetime.timedelta(hours=night_hours)
            if night_block_start < now:
                # ensure start is not before now
                night_block_start = now
            steps.append(ChargingStep(
                id=str(uuid.uuid4()),
                start_time=night_block_start,
                stop_time=night_end if night_block_start < night_end else night_block_start + datetime.timedelta(hours=1),
                current=16,
                description="Nightly prioritized charge"
            ))
            hours_to_schedule -= night_hours

        # allocate remaining hours before the night window (from now up to night_start)
        if hours_to_schedule > 0:
            # available before the night window: time from now until night_start (if night_start > now)
            before_night_seconds = max(0.0, (night_start - now).total_seconds())
            before_night_hours = math.ceil(before_night_seconds / 3600)
            day_hours = min(hours_to_schedule, before_night_hours)
            if day_hours > 0:
                # schedule contiguous block ending at night_start if possible, otherwise up to now+day_hours
                day_block_end = min(night_start, now + datetime.timedelta(hours=day_hours))
                day_block_start = day_block_end - datetime.timedelta(hours=day_hours)
                if day_block_start < now:
                    day_block_start = now
                    day_block_end = now + datetime.timedelta(hours=day_hours)
                steps.append(ChargingStep(
                    id=str(uuid.uuid4()),
                    start_time=day_block_start,
                    stop_time=day_block_end,
                    current=6,
                    description="Daytime charge"
                ))
                hours_to_schedule -= day_hours

        # Build plan timeframe
        plan_start = now
        plan_stop = night_end
        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=plan_start,
            stop_time=plan_stop,
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=planned_charge_hours,
            steps=steps
        )

        logger.info("SimpleHourPlanner plan created: %s", plan)
        return plan


# New PriceAwarePlanner
from typing import Protocol, List, Tuple, Optional
from pydantic.dataclasses import dataclass

class TariffProvider(Protocol):
    """Protocol describing minimal tariff provider interface used by PriceAwarePlanner.

    Implementations should provide price_at(dt: datetime.datetime) -> float, which
    returns the price for the hour starting at dt.
    """
    def price_at(self, dt: datetime.datetime) -> float: ...


# Candidate dataclass represents a single candidate hour for charging.
@dataclass
class Candidate:
    dt: datetime.datetime
    is_night: bool
    current: int
    price: Optional[float] = None
    score: Optional[float] = None
    chosen: bool = False


class PriceAwarePlanner(BasePlanner):
    """Planner that selects cheapest hours between now and the prioritized night window.

    - Accepts a `tariff_provider` implementing `price_at(datetime) -> float`.
    - Calculates energy required and greedily selects cheapest hour blocks until
      required energy is satisfied (prefers night hours by small bias).
    - Builds contiguous ChargingStep blocks grouped by hour and current.
    """

    def __init__(self, config: ChargerConfiguration, tariff_provider: Optional[TariffProvider] = None, tibber_prices: Optional[TibberPrices] = None, fallback_price: float = 0.0):
        self.config = config
        # If a concrete tariff provider is provided, use it. If a TibberPrices-like
        # object is provided, wrap it in the TibberPricesAdapter (local import to
        # avoid circular imports).
        if tariff_provider is not None:
            self.tariff_provider = tariff_provider
        elif tibber_prices is not None:
            # local import to avoid circular dependency
            from smart_charger.tibber_adapter import TibberPricesAdapter
            self.tariff_provider = TibberPricesAdapter(tibber_prices, fallback_price=fallback_price)
        else:
            self.tariff_provider = None

    def plan_charging(self, vehicle: VehicleStatus):
        vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
        planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)

        if planned_energy_kwh <= 0:
            return ChargingPlan(vehicle_id=vehicle.id, start_time=get_now(), stop_time=get_now(), target_soc=vehicle_config.target_soc, energy_kwh=0, charge_hours=0, steps=[])

        now = get_now()
        # Choose night window same as SimpleHourPlanner
        if now.hour < 7:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=0)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=0)
        else:
            night_start = self._get_timestamp_from_hour("00:00", increment_days=1)
            night_end = self._get_timestamp_from_hour("07:00", increment_days=1)

        # build list of candidate hour start datetime from now (rounded up to next hour) until night_end
        start_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0 or now.microsecond > 0:
            start_hour += datetime.timedelta(hours=1)

        candidates: List[Candidate] = []
        cursor = start_hour
        while cursor < night_end:
            is_night = (night_start <= cursor < night_end)
            current = 16 if is_night else 6
            candidates.append(Candidate(dt=cursor, is_night=is_night, current=current))
            cursor += datetime.timedelta(hours=1)

        # enrich candidates with price and score in-place, then sort the candidates list by score
        for cand in candidates:
            price = self.tariff_provider.price_at(cand.dt) if self.tariff_provider else 0.0
            cand.price = price
            cand.score = price - (0.0001 if cand.is_night else 0.0)

        # sort candidates by candidate.score (cheap first). Put unknown scores at the end.
        candidates.sort(key=lambda c: (c.score if c.score is not None else float('inf')))

        accumulated_energy = 0.0
        # select cheapest candidates by marking them chosen
        for cand in candidates:
            hour_energy = self._get_energy(cand.current, 1)
            cand.chosen = True
            accumulated_energy += hour_energy
            if accumulated_energy >= planned_energy_kwh:
                break

        if accumulated_energy < planned_energy_kwh:
            # pick remaining hours in chronological order excluding already chosen
            for cand in candidates:
                if cand.chosen:
                    continue
                current = 16 if (night_start <= cand.dt < night_end) else 6
                hour_energy = self._get_energy(current, 1)
                cand.chosen = True
                accumulated_energy += hour_energy
                if accumulated_energy >= planned_energy_kwh:
                    break

        # build chosen_hours from candidates and group adjacent hours with same current into steps
        chosen_hours: List[Tuple[datetime.datetime, int]] = [(c.dt, c.current) for c in candidates if c.chosen]
        # ensure chronological order
        chosen_hours.sort(key=lambda t: t[0])
        steps: List[ChargingStep] = []
        if chosen_hours:
            block_start = chosen_hours[0][0]
            block_current = chosen_hours[0][1]
            block_end = block_start + datetime.timedelta(hours=1)

            for dt, current in chosen_hours[1:]:
                if current == block_current and dt == block_end:
                    # extend block
                    block_end += datetime.timedelta(hours=1)
                else:
                    steps.append(ChargingStep(id=str(uuid.uuid4()), start_time=block_start, stop_time=block_end, current=block_current, description="Price-aware block"))
                    block_start = dt
                    block_current = current
                    block_end = dt + datetime.timedelta(hours=1)

            # append last block
            steps.append(ChargingStep(id=str(uuid.uuid4()), start_time=block_start, stop_time=block_end, current=block_current, description="Price-aware block"))

        plan = ChargingPlan(
            vehicle_id=vehicle.id,
            start_time=now,
            stop_time=night_end,
            target_soc=vehicle_config.target_soc,
            energy_kwh=planned_energy_kwh,
            charge_hours=len(chosen_hours),
            steps=steps
        )

        logger.info("PriceAwarePlanner created plan with %d steps, energy %.2f kWh", len(steps), plan.total_energy_kwh)
        return plan

