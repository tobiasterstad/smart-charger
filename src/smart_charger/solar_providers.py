"""Solar-aware price provider that combines Tibber prices with solar production data."""

from __future__ import annotations

import datetime
import logging
from typing import Protocol, Optional


logger = logging.getLogger(__name__)


class SolarProvider(Protocol):
    """Protocol for solar production data providers."""

    def get_production(self, dt: datetime.datetime) -> float:
        """Return expected solar production in watts for the given hour."""
        ...

    def get_production_for_hour(self, hour: int) -> float:
        """Return expected solar production in watts for a specific hour of day (0-23)."""
        ...


class MQTTSolarProvider:
    """Solar provider that receives production data from MQTT messages.

    Stores the latest production and consumption values and provides
    typical hourly production profiles for planning purposes.
    """

    def __init__(self, default_production_profile: Optional[dict[int, float]] = None):
        self._current_production_watts: float = 0.0
        self._current_consumption_watts: float = 0.0
        self._default_profile = default_production_profile or {
            0: 0,
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0,
            6: 100,
            7: 500,
            8: 1200,
            9: 2000,
            10: 2800,
            11: 3200,
            12: 3400,
            13: 3200,
            14: 2800,
            15: 2200,
            16: 1500,
            17: 800,
            18: 300,
            19: 100,
            20: 0,
            21: 0,
            22: 0,
            23: 0,
        }

    def update_production(self, watts: float):
        """Called when MQTT receives production update."""
        logger.info(f"Received power production {watts} w")
        self._current_production_watts = watts

    def update_consumption(self, watts: float):
        """Called when MQTT receives consumption update."""
        self._current_consumption_watts = watts

    @property
    def current_production_watts(self) -> float:
        return self._current_production_watts

    @property
    def current_consumption_watts(self) -> float:
        return self._current_consumption_watts

    @property
    def current_excess_watts(self) -> float:
        """Calculate current solar excess (production - consumption)."""
        return max(0, self._current_production_watts - self._current_consumption_watts)

    def get_production(self, dt: datetime.datetime) -> float:
        """Return expected solar production in watts for the given datetime.

        Uses the default profile for planning (hour of day).
        """
        return self._default_profile.get(dt.hour, 0.0)

    def get_production_for_hour(self, hour: int) -> float:
        """Return expected solar production in watts for a specific hour of day (0-23)."""
        return self._default_profile.get(hour, 0.0)


class SolarPriceProvider:
    """Price provider that combines Tibber electricity prices with solar production.

    When solar production is available, the effective price is reduced by the
    "value" of the solar energy that can be used for charging.

    The provider tracks real-time production/consumption from MQTT and uses
    a typical production profile for planning future hours.
    """

    def __init__(
        self,
        tibber_price_provider,
        solar_provider: Optional[SolarProvider] = None,
        min_excess_watts: float = 1000,
    ):
        self.tibber_provider = tibber_price_provider
        self.solar_provider = solar_provider or MQTTSolarProvider()
        self.min_excess_watts = min_excess_watts
        self.voltage = 230

    def price_at(self, dt: datetime.datetime) -> float:
        """Calculate effective price accounting for solar production.

        Returns the effective price per kWh. When solar production is expected,
        the price is reduced based on how much solar energy can offset grid usage.
        """
        electricity_price = self.tibber_provider.price_at(dt)
        solar_benefit = self._calculate_solar_benefit(dt)
        effective_price = electricity_price - solar_benefit
        return max(0.0, effective_price)

    def _calculate_solar_benefit(self, dt: datetime.datetime) -> float:
        """Calculate the monetary benefit of solar production for a given hour.

        Returns the reduction in price per kWh based on expected solar production.
        """
        solar_watts = self.solar_provider.get_production(dt)

        if solar_watts < self.min_excess_watts:
            return 0.0

        solar_kwh = solar_watts / 1000

        electricity_price = self.tibber_provider.price_at(dt)

        benefit = solar_kwh * electricity_price

        return benefit

    def get_solar_excess(self) -> float:
        """Get current solar excess in watts from real-time MQTT data."""
        return self.solar_provider.current_excess_watts

    def is_solar_available(self) -> bool:
        """Check if currently there's meaningful solar production."""
        return self.solar_provider.current_excess_watts >= self.min_excess_watts
