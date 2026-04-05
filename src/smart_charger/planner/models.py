"""Data models for charging plans and candidates."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass


def get_now() -> datetime.datetime:
    """Helper to obtain current time; can be patched in tests."""
    return datetime.datetime.now()


class ChargingStep(BaseModel):
    """A single charging step with start/stop times and current setting."""

    id: str
    start_time: datetime.datetime
    stop_time: Optional[datetime.datetime] = None
    current: int = Field(default=16, description="Charging current in Amperes")
    description: str
    mean_price: Optional[float] = None

    @property
    def energy_kwh(self) -> float:
        """Calculate energy delivered during this step."""
        hours = (self.stop_time - self.start_time).total_seconds() / 3600
        energy_kwh = (230 * self.current / 1000) * hours
        return energy_kwh


class ChargingPlan(BaseModel):
    """A complete charging plan with multiple steps."""

    vehicle_id: str
    start_time: datetime.datetime
    stop_time: datetime.datetime
    target_soc: int
    energy_kwh: float
    charge_hours: int
    steps: list[ChargingStep]

    @property
    def total_energy_kwh(self) -> float:
        """Calculate total energy across all steps."""
        return sum(step.energy_kwh for step in self.steps)

    def format_for_log(self) -> str:
        """Return a human-readable string for logging."""
        step_info = []
        for step in self.steps:
            start = step.start_time.strftime("%H:%M")
            stop = step.stop_time.strftime("%H:%M") if step.stop_time else "?"
            price = f"{step.mean_price:.4f}" if step.mean_price else "?"
            step_info.append(f"{start}-{stop} ({step.current}A, {price})")
        return f"Plan: {self.charge_hours}h, {self.energy_kwh:.2f}kWh, {', '.join(step_info)}"

    def get_charging_step(
        self, timestamp: Optional[datetime.datetime] = None
    ) -> Optional[ChargingStep]:
        """Get the active charging step at the given timestamp."""
        if not timestamp:
            timestamp = get_now()
        for step in self.steps:
            if step.start_time <= timestamp <= step.stop_time:
                return step
        return None


@dataclass
class Candidate:
    """A candidate hour for price-aware charging."""

    dt: datetime.datetime
    is_night: bool
    current: int
    price: Optional[float] = None
    score: Optional[float] = None
    chosen: bool = False


@dataclass
class SolarCandidate:
    """A candidate hour for solar-aware charging.

    Extends the basic Candidate with solar production data and effective price.
    """

    dt: datetime.datetime
    is_night: bool
    current: int
    grid_price: Optional[float] = None
    solar_watts: Optional[float] = None
    effective_price: Optional[float] = None
    chosen: bool = False
