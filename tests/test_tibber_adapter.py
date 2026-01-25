import datetime
import unittest

from smart_charger.tibber_adapter import TibberPricesAdapter
from smart_charger.tibber.tibber_util import (
    PriceInfo,
    PriceData,
    CurrentSubscription,
    Home,
    Viewer,
    Data,
    Prices,
)


def make_priceinfo_list(iso_price_pairs):
    """Return a list of PriceInfo objects with .startsAt (datetime) and .total (float)."""
    items = []
    for ts, price in iso_price_pairs:
        # parse ISO timestamp; ensure tz-aware
        if ts.endswith("Z"):
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.datetime.fromisoformat(ts)
        # PriceInfo(total: float, energy: float, tax: float, startsAt: datetime, level: Optional[str] = "NORMAL")
        items.append(PriceInfo(total=price, energy=price, tax=0.0, startsAt=dt))
    return items


def get_tibber_prices(today_pairs=None, tomorrow_pairs=None):
    today_pairs = today_pairs or []
    tomorrow_pairs = tomorrow_pairs or []

    today_list = make_priceinfo_list(today_pairs)
    tomorrow_list = make_priceinfo_list(tomorrow_pairs)

    price_data = PriceData(today=today_list, tomorrow=tomorrow_list)
    current_sub = CurrentSubscription(priceInfo=price_data)
    home = Home(currentSubscription=current_sub)
    viewer = Viewer(homes=[home])
    data = Data(viewer=viewer)
    prices = Prices(data=data)
    return prices


class TestTibberAdapter(unittest.TestCase):
    def test_tibber_adapter_maps_prices_and_returns_value(self):
        # Prepare tibber data containing a single hour
        iso_dt = "2026-01-24T00:00:00Z"
        price_value = 0.42
        prices = get_tibber_prices(today_pairs=[(iso_dt, price_value)])
        adapter = TibberPricesAdapter(prices, fallback_price=9.99)

        # Query using timezone-aware datetime that matches the parsed 'Z' -> +00:00 key
        query_dt = datetime.datetime.fromisoformat("2026-01-24T00:00:00+00:00")
        p = adapter.price_at(query_dt)
        self.assertAlmostEqual(p, price_value, places=9)

    def test_tibber_adapter_returns_fallback_on_missing(self):
        # No prices provided -> fallback used
        prices = get_tibber_prices(today_pairs=[], tomorrow_pairs=[])
        adapter = TibberPricesAdapter(prices, fallback_price=7.77)

        query_dt = datetime.datetime.fromisoformat("2026-01-24T01:00:00+00:00")
        p = adapter.price_at(query_dt)
        self.assertEqual(p, 7.77)

    def test_tibber_adapter_uses_tomorrow_prices(self):
        # If a price appears only in tomorrow, the adapter should include it
        missing_today = []
        tomorrow_pair = [("2026-01-24T03:00:00Z", 0.12)]

        prices = get_tibber_prices(
            today_pairs=missing_today, tomorrow_pairs=tomorrow_pair
        )
        adapter = TibberPricesAdapter(prices, fallback_price=5.5)

        query_dt = datetime.datetime.fromisoformat("2026-01-24T03:00:00+00:00")
        p = adapter.price_at(query_dt)
        self.assertAlmostEqual(p, 0.12, places=9)
