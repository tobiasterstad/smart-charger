"""Price providers for electricity pricing data."""

from __future__ import annotations

import datetime
from typing import Protocol

from smart_charger.tibber.tibber_util import (
    PriceInfo,
    TibberPrices,
    TibberConfig,
)


class PriceProvider(Protocol):
    """Protocol describing minimal price provider interface used by PriceAwarePlanner.

    Implementations should provide price_at(dt: datetime.datetime) -> float, which
    returns the price for the hour starting at dt.
    """

    def price_at(self, dt: datetime.datetime) -> float: ...


class NightProvider(PriceProvider):
    def __init__(self):
        pass

    def price_at(self, dt: datetime.datetime) -> float:
        if 0 <= dt.hour <= 6:
            return 0.1
        return 1


class TibberPriceProvider(PriceProvider):
    """Adapter that wraps `TibberPrices` (which fetches today/tomorrow from Tibber)
    and exposes `price_at(datetime) -> float` used by `PriceAwarePlanner`.

    Behavior:
    - On first call it fetches `today_tomorrow()` and builds a mapping of hour->price.
    - If a requested datetime is not present, it will refresh the mapping once and try again.
    - If still not found, returns `fallback_price`.
    """

    prices: list[PriceInfo] = None

    def __init__(self, tibber_config: TibberConfig):
        self.tibber_prices_util = TibberPrices(tibber_config)
        self.fallback_price = 0.0

    def _update_prices(self):
        self.prices = []
        prices = self.tibber_prices_util.today_tomorrow()
        for home in prices.data.viewer.homes:
            for p in home.currentSubscription.priceInfo.today:
                self.prices.append(p)
            for p in home.currentSubscription.priceInfo.tomorrow:
                self.prices.append(p)

    def _is_old_prices(self):
        if not self.prices:
            return True

        try:
            latest_date = max(p.startsAt.date() for p in self.prices)
        except Exception:
            return True

        now = datetime.datetime.now()
        today = now.date()
        expected_max_date = (
            today if now.hour < 14 else today + datetime.timedelta(days=1)
        )

        return latest_date < expected_max_date

    def price_at(self, dt: datetime.datetime) -> float:
        if self.prices is None or self._is_old_prices():
            if self.tibber_prices_util is not None:
                self._update_prices()

        if not self.prices:
            return self.fallback_price

        dt_hour = dt.replace(minute=0, second=0, microsecond=0)
        for p in self.prices:
            if p.startsAt.day == dt_hour.day and p.startsAt.hour == dt_hour.hour:
                return p.total
        return self.fallback_price
