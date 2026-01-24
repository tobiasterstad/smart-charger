"""Adapter to expose Tibber tariff data through the TariffProvider protocol.

This adapter is intentionally lightweight: it accepts either a pre-built
TariffCalculator (from `smart_charger.tibber.tariff`) or a plain mapping of
timestamps->prices (the latter is passed into TariffCalculator). The adapter
implements `price_at(datetime) -> float` and is test-friendly.
"""
from __future__ import annotations

from typing import Optional, Dict
import datetime
from datetime import datetime

from smart_charger.planner import TariffProvider
from smart_charger.tibber.tibber_util import TibberPrices
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

    def __init__(self, tibber_prices: TibberPrices, fallback_price: float = 0.0):
        self.tibber = tibber_prices
        self.fallback_price = fallback_price
        self._hourly_map: Dict[datetime, float] = {}
        self._fetched = False

    def _build_map_from_prices(self, prices_obj: any) -> None:
        # prices_obj is expected to have attributes `today` and `tomorrow` which are
        # iterable of dict-like or pydantic models with fields `startsAt`/`starts_at` and `total`.
        self._hourly_map = {}

        def ingest_list(lst):
            if not lst:
                return
            for item in lst:
                # item may be a dict or pydantic model
                starts = None
                total = None
                if isinstance(item, dict):
                    starts = item.get('startsAt') or item.get('starts_at') or item.get('from')
                    total = item.get('total') or item.get('price') or item.get('energy')
                else:
                    # try attribute access
                    starts = getattr(item, 'startsAt', None) or getattr(item, 'starts_at', None) or getattr(item, 'from_', None) or getattr(item, 'time', None)
                    total = getattr(item, 'total', None) or getattr(item, 'price', None) or getattr(item, 'energy', None) or getattr(item, 'consumption', None)

                if starts is None or total is None:
                    continue

                # parse starts into datetime if it's a string
                if isinstance(starts, str):
                    try:
                        dt = datetime.fromisoformat(starts.replace('Z', '+00:00'))
                    except Exception:
                        try:
                            dt = datetime.fromisoformat(starts)
                        except Exception:
                            continue
                elif isinstance(starts, datetime):
                    dt = starts
                else:
                    continue

                # normalize to hour start
                dt_hour = dt.replace(minute=0, second=0, microsecond=0)
                try:
                    price = float(total)
                except Exception:
                    continue

                self._hourly_map[dt_hour] = price

        ingest_list(getattr(prices_obj, 'today', None) or getattr(prices_obj, 'today', None))
        ingest_list(getattr(prices_obj, 'tomorrow', None) or getattr(prices_obj, 'tomorrow', None))

    def _ensure_map(self, refresh: bool = False):
        if self._fetched and not refresh:
            return
        prices_obj = self.tibber.today_tomorrow()
        self._build_map_from_prices(prices_obj)
        self._fetched = True

    def price_at(self, dt: datetime) -> float:
        # normalize to hour
        dt_hour = dt.replace(minute=0, second=0, microsecond=0)
        # ensure we have a map
        self._ensure_map()
        price = self._hourly_map.get(dt_hour)
        if price is not None:
            return price
        # try refreshing once
        self._ensure_map(refresh=True)
        return self._hourly_map.get(dt_hour, self.fallback_price)
