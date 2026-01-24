import datetime
from types import SimpleNamespace
import unittest

from smart_charger.tibber_adapter import TibberPricesAdapter


class FakeTibber:
    """Fake TibberPrices-like object that returns provided price objects in sequence.

    today_tomorrow() will return the next item from `responses` on each call.
    """
    def __init__(self, responses):
        self._responses = list(responses)
        self._call = 0

    def today_tomorrow(self):
        # Return current response and advance (but cap at last)
        resp = self._responses[min(self._call, len(self._responses) - 1)]
        self._call += 1
        return resp


def make_prices_from_iso_list(iso_price_pairs):
    """Helper: build a SimpleNamespace with `today` and `tomorrow` lists where each item is a dict
    containing 'startsAt' and 'total' keys (strings/numbers accepted).
    iso_price_pairs: list of tuples (iso_timestamp, price)
    Returns SimpleNamespace(today=[...], tomorrow=[])
    """
    items = []
    for ts, price in iso_price_pairs:
        items.append({"startsAt": ts, "total": price})
    return SimpleNamespace(today=items, tomorrow=[])


class TestTibberAdapter(unittest.TestCase):

    def test_tibber_adapter_maps_prices_and_returns_value(self):
        # Prepare fake tibber response containing a single hour
        iso_dt = "2026-01-24T00:00:00Z"
        price_value = 0.42
        prices_obj = make_prices_from_iso_list([(iso_dt, price_value)])

        fake = FakeTibber([prices_obj])
        adapter = TibberPricesAdapter(fake, fallback_price=9.99)

        # Query using timezone-aware datetime that matches the parsed 'Z' -> +00:00 key
        query_dt = datetime.datetime.fromisoformat("2026-01-24T00:00:00+00:00")
        p = adapter.price_at(query_dt)
        self.assertAlmostEqual(p, price_value, places=9)


    def test_tibber_adapter_returns_fallback_on_missing(self):
        # No prices provided -> fallback used
        prices_obj = make_prices_from_iso_list([])
        fake = FakeTibber([prices_obj])
        adapter = TibberPricesAdapter(fake, fallback_price=7.77)

        query_dt = datetime.datetime.fromisoformat("2026-01-24T01:00:00+00:00")
        p = adapter.price_at(query_dt)
        self.assertEqual(p, 7.77)


    def test_tibber_adapter_refreshes_on_miss_and_finds_price(self):
        # First response has no price for the requested hour; second response (after refresh) includes it.
        missing = make_prices_from_iso_list([])
        found = make_prices_from_iso_list([("2026-01-24T03:00:00Z", 0.12)])

        fake = FakeTibber([missing, found])
        adapter = TibberPricesAdapter(fake, fallback_price=5.5)

        query_dt = datetime.datetime.fromisoformat("2026-01-24T03:00:00+00:00")
        # First call to price_at will fetch (missing), then refresh and get the found price
        p = adapter.price_at(query_dt)
        self.assertAlmostEqual(p, 0.12, places=9)
