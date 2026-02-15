"""Solar-aware charging controller."""

from __future__ import annotations

import datetime
import json
import logging
import math
from typing import Optional

from smart_charger.config import ChargerConfiguration
from smart_charger.planner import ChargingStep, BasePlanner
from smart_charger.price_providers import PriceProvider
from smart_charger.session import ChargingSession
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
        return max(0.0, effective_price)

    def get_solar_charge_prediction(
        self, session: ChargingSession, step: ChargingStep
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
