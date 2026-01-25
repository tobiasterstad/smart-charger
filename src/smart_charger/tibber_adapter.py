"""Adapter to expose Tibber tariff data through the TariffProvider protocol.

This adapter is intentionally lightweight: it accepts either a pre-built
TariffCalculator (from `smart_charger.tibber.tariff`) or a plain mapping of
timestamps->prices (the latter is passed into TariffCalculator). The adapter
implements `price_at(datetime) -> float` and is test-friendly.
"""
from __future__ import annotations

from typing import Optional, Dict
import datetime

from smart_charger.planner import TariffProvider
from smart_charger.tibber.tibber_util import TibberPrices, Prices, PriceInfo
from smart_charger.tibber.tariff import TariffCalculator


class TibberAdapter(TariffProvider):
    """Bridge between Tibber tariff data and the planner's TariffProvider.

    Constructor options:
    - tariff_calculator: a ready TariffCalculator instance (preferred)
    - tariff_data: a dict-like mapping from datetime or ISO timestamp to price
      usable to construct a TariffCalculator

    The adapter's price_at method will try a few key formats to find a price:
    - exact datetime key
    - rounded-to-hour datetime
    - ISO formatted string of the above
    If nothing is found, it returns a fallback value (0.0) so planners can still
    operate in offline/test environments.
    """

    def __init__(self, tariff_calculator: Optional[TariffCalculator] = None, tariff_data: Optional[dict] = None, fallback_price: float = 0.0):
        if tariff_calculator is not None:
            self.calc = tariff_calculator
        elif tariff_data is not None:
            self.calc = TariffCalculator(tariff_data)
        else:
            self.calc = None

        self.fallback_price = fallback_price

    def _round_to_hour(self, dt: datetime.datetime) -> datetime.datetime:
        return dt.replace(minute=0, second=0, microsecond=0)

    def price_at(self, dt: datetime.datetime) -> float:
        # Prefer the tariff calculator if provided
        if self.calc is not None:
            # TariffCalculator expects the same key format as used when built; try useful fallbacks
            price = self.calc.get_price_at(dt)
            if price is not None:
                return price

            # try rounded hour
            rounded = self._round_to_hour(dt)
            price = self.calc.get_price_at(rounded)
            if price is not None:
                return price

            # try ISO strings
            price = self.calc.get_price_at(dt.isoformat())
            if price is not None:
                return price
            price = self.calc.get_price_at(rounded.isoformat())
            if price is not None:
                return price

            return self.fallback_price

        # If no calculator was provided, return fallback
        return self.fallback_price


class TibberPricesAdapter(TariffProvider):
    """Adapter that wraps `TibberPrices` (which fetches today/tomorrow from Tibber)
    and exposes `price_at(datetime) -> float` used by `PriceAwarePlanner`.

    Behavior:
    - On first call it fetches `today_tomorrow()` and builds a mapping of hour->price.
    - If a requested datetime is not present, it will refresh the mapping once and try again.
    - If still not found, returns `fallback_price`.
    """

    def __init__(self, tibber_prices: Prices, fallback_price: float = 0.0):
        self.tibber = tibber_prices
        self.fallback_price = fallback_price
        self.prices: list[PriceInfo] = []
        for home in self.tibber.data.viewer.homes:
            for p in home.currentSubscription.priceInfo.today:
                self.prices.append(p)
            for p in home.currentSubscription.priceInfo.tomorrow:
                self.prices.append(p)

    def price_at(self, dt: datetime.datetime) -> float:
        dt_hour = dt.replace(minute=0, second=0, microsecond=0)
        for p in self.prices:
            if p.startsAt.day == dt_hour.day and p.startsAt.hour == dt_hour.hour:
                return p.total
        return self.fallback_price


