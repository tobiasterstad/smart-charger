"""Solar-aware charging controller and forecasting."""

from __future__ import annotations

import datetime
import json
import logging
import math
from typing import Optional, Protocol

from smart_charger.config import ChargerConfiguration
from smart_charger.planner import BasePlanner
from smart_charger.price_providers import PriceProvider
from smart_charger.session import ChargingSession
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SolarForecastProvider(Protocol):
    """Protocol for solar production forecast providers.

    Implementations should provide forecast_at(dt: datetime.datetime) -> float,
    which returns the predicted solar production in watts for the hour starting at dt.
    """

    def forecast_at(self, dt: datetime.datetime) -> float: ...


class SimpleSolarForecastProvider:
    """Simple solar forecast using a bell curve profile for daylight hours.

    This provides a basic forecast based on typical sunny-day production patterns.
    Production follows a bell curve centered around solar noon (default 12:00).

    Attributes:
        peak_watts: Maximum production at solar noon (default 5000W).
        sunrise_hour: Hour when production starts (default 6).
        sunset_hour: Hour when production ends (default 20).
        noon_hour: Hour of peak production (default 12).
    """

    def __init__(
        self,
        peak_watts: float = 5000.0,
        sunrise_hour: int = 6,
        sunset_hour: int = 20,
        noon_hour: int = 12,
    ):
        self.peak_watts = peak_watts
        self.sunrise_hour = sunrise_hour
        self.sunset_hour = sunset_hour
        self.noon_hour = noon_hour

    def forecast_at(self, dt: datetime.datetime) -> float:
        """Return predicted solar production in watts for the given hour.

        Uses a cosine-based bell curve centered at solar noon.
        Returns 0 outside daylight hours.
        """
        hour = dt.hour

        # No production outside daylight hours
        if hour < self.sunrise_hour or hour >= self.sunset_hour:
            return 0.0

        # Use cosine curve centered at noon_hour
        # Peak at noon_hour, zero at sunrise and sunset
        # cos(x) = 1 at x=0, -1 at x=pi
        # We map hours to [-pi, pi] centered at noon
        half_day = max(
            self.noon_hour - self.sunrise_hour, self.sunset_hour - self.noon_hour
        )
        hours_from_noon = hour - self.noon_hour

        # Normalize to [-1, 1] range, where 0 is noon
        position = hours_from_noon / half_day

        # cos(position * pi) gives 1 at noon (position=0), -1 at edges
        # Scale to [0, 1]
        curve_value = (1 + math.cos(position * math.pi)) / 2

        return self.peak_watts * curve_value


class MQTTSolarForecastProvider:
    """Solar forecast provider that uses recent MQTT production data.

    This provider tracks real-time solar production and uses it as the
    basis for forecasting. It applies a daily profile adjustment to
    estimate future production based on current conditions.

    For hours that have already passed today, it uses actual recorded values.
    For future hours, it scales based on the typical daily profile and
    current production level.
    """

    def __init__(
        self,
        peak_watts: float = 5000.0,
        sunrise_hour: int = 6,
        sunset_hour: int = 20,
    ):
        self.peak_watts = peak_watts
        self.sunrise_hour = sunrise_hour
        self.sunset_hour = sunset_hour
        self._current_production: float = 0.0
        self._last_update: Optional[datetime.datetime] = None
        self._simple_provider = SimpleSolarForecastProvider(
            peak_watts=peak_watts,
            sunrise_hour=sunrise_hour,
            sunset_hour=sunset_hour,
        )

    def update_production(self, watts: float) -> None:
        """Update current solar production from MQTT."""
        self._current_production = watts
        self._last_update = datetime.datetime.now()

    def forecast_at(self, dt: datetime.datetime) -> float:
        """Return predicted solar production for the given hour.

        If no recent production data is available, falls back to simple profile.
        Otherwise, scales the profile based on current production vs expected.
        """
        # If no recent data (older than 1 hour), use simple profile
        if (
            self._last_update is None
            or (datetime.datetime.now() - self._last_update).total_seconds() > 3600
        ):
            return self._simple_provider.forecast_at(dt)

        # Get expected production now and at requested time
        now = datetime.datetime.now()
        expected_now = self._simple_provider.forecast_at(now)
        expected_at_dt = self._simple_provider.forecast_at(dt)

        # If expected now is 0, we can't scale - use simple profile
        if expected_now <= 0:
            return expected_at_dt

        # Scale factor: actual / expected production right now
        scale_factor = self._current_production / expected_now

        # Apply scale factor to expected production at target time
        # Cap at 1.5x to avoid unrealistic forecasts from brief cloud gaps
        scale_factor = min(scale_factor, 1.5)

        return expected_at_dt * scale_factor


class SolarChargePrediction(BaseModel):
    available: bool
    effective_price: float = 0.0
    current: int = 0


class SolarChargerController:
    """
    Controller that manages charging based on solar production and electricity prices.

    Combines real-time solar production data with price information to determine
    when solar charging is beneficial.
    """

    def __init__(
        self,
        config: ChargerConfiguration,
        price_provider: Optional[PriceProvider] = None,
    ):
        self.config = config
        self.price_provider = price_provider

        self.power_production: float = 0.0
        self.power_consumption: float = 0.0

    def update_production(self, watts: float) -> None:
        """Update current solar production in watts."""
        logger.info(f"Received power production {watts} W")
        self.power_production = watts

    def update_consumption(self, watts: float) -> None:
        """Update current power consumption in watts."""
        self.power_consumption = watts

    def get_effective_price(
        self,
        ts: datetime.datetime = datetime.datetime.now(),
        planned_energy_kwh: Optional[float] = None,
    ) -> float:
        """
        Get the effective grid price per kWh for the planned energy, accounting for solar offset.

        effective_price = max(0, grid_price - (solar_watts / 1000) * grid_price / planned_energy_kwh)

        If solar covers all planned energy, effective price is 0.
        If no solar or no planned energy, effective price is the grid price.
        """
        if self.price_provider is None:
            return 0.0

        grid_price = self.price_provider.price_at(ts)
        solar_watts = self.power_production

        if solar_watts <= 0 or planned_energy_kwh is None or planned_energy_kwh <= 0:
            return grid_price

        solar_kwh = solar_watts / 1000
        effective_price = grid_price - (solar_kwh * grid_price / planned_energy_kwh)
        return round(max(0.0, effective_price), 2)

    def get_solar_charge_prediction(
        self, session: ChargingSession
    ) -> SolarChargePrediction:
        """Check if solar charging is available based on current production and if the
        relative price is below the price planned later in the charging session.

        This allows us to start charging even if solar production alone isn't enough
        to cover all needs, as long as it provides a meaningful benefit.
        """
        if self.power_production <= 0 or not session.plan:
            return SolarChargePrediction(available=False)

        # Current (A) = Energy (kWh) * 1000 / (Voltage (V) * Time (h))
        hours = 1
        voltage = 230
        planned_energy = self.power_production * hours
        current = math.ceil(planned_energy / (voltage * hours))

        # TODO: Add min and max current for the charger configuration. For now, we assume 6-16 A range.
        current = max(6, min(16, current))

        # Get the effective price for the planned energy, if charging at current.
        planned_energy_kwh = BasePlanner._get_energy(current, hours)
        effective_price = self.get_effective_price(
            planned_energy_kwh=planned_energy_kwh
        )
        logger.info(
            f"Effective price for next hour: %.2f SEK/kWh, charging at {current}A",
            effective_price,
        )

        now = datetime.datetime.now()
        future_prices = [
            step.mean_price
            for step in session.plan.steps
            if step.start_time > now and step.mean_price is not None
        ]

        logger.debug(f"Charging plan: {session.plan.model_dump_json(indent=2)}")
        logger.debug(f"Future prices: {json.dumps(future_prices, indent=2)}")

        if not future_prices:
            return SolarChargePrediction(available=False)

        min_future_price = min(future_prices)
        charging_available = effective_price < min_future_price

        logger.info(
            "Minimum future price in session plan: %.2f SEK/kWh", min_future_price
        )

        if charging_available:
            logger.debug("Solar charging is available and beneficial")
        else:
            logger.debug("Solar charging is not beneficial compared to future prices")

        return SolarChargePrediction(
            available=charging_available,
            effective_price=effective_price,
            current=current,
        )
