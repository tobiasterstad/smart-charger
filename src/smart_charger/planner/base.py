"""Base planner class with shared utilities."""

from __future__ import annotations

import abc
import datetime
import logging
import math
from typing import Protocol

from smart_charger.config import VehicleConfig
from smart_charger.vehicle import VehicleStatus

from .models import get_now

logger = logging.getLogger(__name__)


class PriceProvider(Protocol):
    """Protocol for electricity price providers."""

    def price_at(self, dt: datetime.datetime) -> float: ...


class SolarForecastProvider(Protocol):
    """Protocol for solar production forecast providers."""

    def forecast_at(self, dt: datetime.datetime) -> float: ...


class BasePlanner(abc.ABC):
    """Abstract base class for charging planners.

    Provides common utilities for energy calculations, time handling,
    and planning logic that subclasses can use.
    """

    @abc.abstractmethod
    def plan_charging(self, vehicle: VehicleStatus):
        """Create a charging plan for the given vehicle.

        Things to consider:
        - Time of day
        - Energy prices
        - Solar energy availability
        - Vehicle usage patterns
        - Grid constraints, high load periods
        - User preferences
        - Current SOC
        """
        pass

    @staticmethod
    def _get_timestamp_from_hour(
        time: str, increment_days: int = 0
    ) -> datetime.datetime:
        """Convert a time string (HH:MM) to a datetime for today or future days."""
        now = get_now()
        hour, minute = map(int, time.split(":"))
        planned_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        planned_time += datetime.timedelta(days=increment_days)
        return planned_time

    @staticmethod
    def _get_timestamp_hours_from_now(hours: int) -> datetime.datetime:
        """Get a timestamp N hours from now."""
        return get_now() + datetime.timedelta(hours=hours)

    @staticmethod
    def _get_planned_energy(
        vehicle: VehicleStatus, vehicle_config: VehicleConfig
    ) -> float:
        """Calculate energy needed to reach target SOC."""
        charge = vehicle_config.target_soc - vehicle.soc
        planned_energy_kwh = (charge / 100) * (vehicle_config.capacity_kwh or 0)
        logger.info(
            "Planning charging for vehicle %s: current SOC %d%%, target SOC %d%%, planned energy %.2f kWh",
            vehicle.id,
            vehicle.soc,
            vehicle_config.target_soc,
            planned_energy_kwh,
        )
        return math.ceil(planned_energy_kwh)

    @staticmethod
    def _get_energy(current: float, hours: float, voltage: float = 230) -> float:
        """Calculate energy (kWh) for given current and duration.

        Energy (kWh) = Power (kW) * Time (h)
        Power (kW) = Voltage (V) * Current (A) / 1000
        """
        energy_kwh = (voltage * current / 1000) * hours
        return energy_kwh

    @staticmethod
    def get_charge_hours(planned_energy_kwh: float, current: float = 16.0) -> int:
        """Calculate number of hours needed to charge the planned energy.

        Args:
            planned_energy_kwh: Planned energy in kWh
            current: Charging current in Amperes

        Returns:
            Number of hours needed (rounded up)
        """
        effect = (230 * current) / 1000  # kW
        planned_charge_hours = math.ceil(planned_energy_kwh / effect)
        return planned_charge_hours

    def _get_night_window(
        self, now: datetime.datetime
    ) -> tuple[datetime.datetime, datetime.datetime]:
        """Get the night window start and end times.

        Args:
            now: The current datetime used to determine which night window to use.
                If before 7am, uses tonight's window (same day).
                If after 7am, uses tomorrow night's window (next day).

        Returns:
            A tuple of (night_start, night_end) datetimes.
            Night window is 00:00 to 07:00.
        """
        if now.hour < 7:
            return (
                self._get_timestamp_from_hour("00:00", increment_days=0),
                self._get_timestamp_from_hour("07:00", increment_days=0),
            )
        return (
            self._get_timestamp_from_hour("00:00", increment_days=1),
            self._get_timestamp_from_hour("07:00", increment_days=1),
        )
