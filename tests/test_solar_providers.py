import datetime
import pytest
from unittest.mock import MagicMock

from smart_charger.solar_providers import (
    MQTTSolarProvider,
    SolarPriceProvider,
    SolarProvider,
)


class TestMQTTSolarProvider:
    def test_default_profile(self):
        provider = MQTTSolarProvider()

        assert provider.get_production_for_hour(0) == 0
        assert provider.get_production_for_hour(6) == 100
        assert provider.get_production_for_hour(10) == 2800
        assert provider.get_production_for_hour(12) == 3400
        assert provider.get_production_for_hour(18) == 300
        assert provider.get_production_for_hour(23) == 0

    def test_custom_profile(self):
        custom_profile = {i: i * 100 for i in range(24)}
        provider = MQTTSolarProvider(default_production_profile=custom_profile)

        assert provider.get_production_for_hour(0) == 0
        assert provider.get_production_for_hour(5) == 500
        assert provider.get_production_for_hour(12) == 1200

    def test_update_production(self):
        provider = MQTTSolarProvider()

        provider.update_production(5000)

        assert provider.current_production_watts == 5000

    def test_update_consumption(self):
        provider = MQTTSolarProvider()

        provider.update_consumption(2000)

        assert provider.current_consumption_watts == 2000

    def test_current_excess_with_excess(self):
        provider = MQTTSolarProvider()

        provider.update_production(5000)
        provider.update_consumption(2000)

        assert provider.current_excess_watts == 3000

    def test_current_excess_no_excess(self):
        provider = MQTTSolarProvider()

        provider.update_production(2000)
        provider.update_consumption(5000)

        assert provider.current_excess_watts == 0

    def test_get_production_with_datetime(self):
        provider = MQTTSolarProvider()

        dt = datetime.datetime(2024, 6, 15, 12, 0, 0)  # noon
        assert provider.get_production(dt) == 3400

    def test_get_production_unknown_hour(self):
        provider = MQTTSolarProvider()

        assert provider.get_production_for_hour(24) == 0
        assert provider.get_production_for_hour(-1) == 0


class TestSolarPriceProvider:
    @pytest.fixture
    def mock_tibber_provider(self):
        provider = MagicMock()
        provider.price_at.return_value = 1.0  # 1 SEK/kWh
        return provider

    @pytest.fixture
    def solar_provider(self):
        return MQTTSolarProvider(
            default_production_profile={
                0: 0,
                1: 0,
                2: 0,
                3: 0,
                4: 0,
                5: 0,
                6: 0,
                7: 0,
                8: 1000,
                9: 2000,
                10: 3000,
                11: 3000,
                12: 3000,
                13: 2000,
                14: 1000,
                15: 0,
                16: 0,
                17: 0,
                18: 0,
                19: 0,
                20: 0,
                21: 0,
                22: 0,
                23: 0,
            }
        )

    def test_price_at_no_solar(self, mock_tibber_provider, solar_provider):
        # Use a profile with no solar production at noon
        solar_provider._default_profile = {i: 0 for i in range(24)}

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        dt = datetime.datetime(2024, 6, 15, 12, 0, 0)
        price = provider.price_at(dt)

        assert price == 1.0
        mock_tibber_provider.price_at.assert_called_once_with(dt)

    def test_price_at_with_solar_below_threshold(
        self, mock_tibber_provider, solar_provider
    ):
        # Solar benefit is now applied at ALL levels (even low production)
        solar_provider._default_profile = {i: 500 for i in range(24)}

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        dt = datetime.datetime(2024, 6, 15, 10, 0, 0)
        price = provider.price_at(dt)

        # 500W = 0.5 kWh, benefit = 0.5 * 1.0 = 0.5
        # Effective price = 1.0 - 0.5 = 0.5
        assert price == 0.5
        mock_tibber_provider.price_at.assert_called_once_with(dt)

    def test_price_at_with_solar_above_threshold(
        self, mock_tibber_provider, solar_provider
    ):
        solar_provider.update_production(5000)

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        dt = datetime.datetime(2024, 6, 15, 10, 0, 0)  # 3000W expected production
        price = provider.price_at(dt)

        assert price < 1.0
        assert price >= 0.0

    def test_price_at_minimum_zero(self, mock_tibber_provider, solar_provider):
        mock_tibber_provider.price_at.return_value = 0.5

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        dt = datetime.datetime(2024, 6, 15, 10, 0, 0)  # 3000W expected production
        price = provider.price_at(dt)

        assert price >= 0.0

    def test_get_solar_excess(self, mock_tibber_provider):
        solar_provider = MQTTSolarProvider()
        solar_provider.update_production(5000)
        solar_provider.update_consumption(2000)

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        assert provider.get_solar_excess() == 3000

    def test_is_solar_available_true(self, mock_tibber_provider):
        solar_provider = MQTTSolarProvider()
        solar_provider.update_production(5000)

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        assert provider.is_solar_available() is True

    def test_is_solar_available_false(self, mock_tibber_provider):
        solar_provider = MQTTSolarProvider()
        solar_provider.update_production(0)

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        assert provider.is_solar_available() is False

    def test_solar_benefit_calculation(self, mock_tibber_provider):
        solar_provider = MQTTSolarProvider(
            default_production_profile={
                0: 0,
                1: 0,
                2: 0,
                3: 0,
                4: 0,
                5: 0,
                6: 0,
                7: 0,
                8: 0,
                9: 0,
                10: 2000,
                11: 2000,
                12: 2000,
                13: 2000,
                14: 2000,
                15: 0,
                16: 0,
                17: 0,
                18: 0,
                19: 0,
                20: 0,
                21: 0,
                22: 0,
                23: 0,
            }
        )

        mock_tibber_provider.price_at.return_value = 2.0  # 2 SEK/kWh

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        dt = datetime.datetime(2024, 6, 15, 10, 0, 0)
        price = provider.price_at(dt)

        # Solar production: 2000W = 2 kWh
        # Benefit: 2 kWh * 2 SEK/kWh = 4 SEK
        # Effective price: 2 - 4 = -2, but floored to 0
        assert price == 0.0

    def test_uses_profile_for_planning(self, mock_tibber_provider):
        solar_provider = MQTTSolarProvider(
            default_production_profile={
                0: 0,
                1: 0,
                2: 0,
                3: 0,
                4: 0,
                5: 0,
                6: 0,
                7: 0,
                8: 0,
                9: 0,
                10: 3000,
                11: 3000,
                12: 3000,
                13: 3000,
                14: 3000,
                15: 0,
                16: 0,
                17: 0,
                18: 0,
                19: 0,
                20: 0,
                21: 0,
                22: 0,
                23: 0,
            }
        )

        mock_tibber_provider.price_at.return_value = 1.0

        provider = SolarPriceProvider(mock_tibber_provider, solar_provider)

        # Morning (low solar) - should use profile from init
        dt_morning = datetime.datetime(2024, 6, 15, 8, 0, 0)
        price_morning = provider.price_at(dt_morning)

        # Midday (high solar) - should use profile from init
        dt_midday = datetime.datetime(2024, 6, 15, 12, 0, 0)
        price_midday = provider.price_at(dt_midday)

        assert price_midday < price_morning


class TestSolarProviderProtocol:
    def test_protocol_implementation(self):
        """Test that MQTTSolarProvider fulfills SolarProvider protocol."""
        provider = MQTTSolarProvider()

        # These should work without error
        result = provider.get_production(datetime.datetime.now())
        assert isinstance(result, (int, float))

        result = provider.get_production_for_hour(12)
        assert isinstance(result, (int, float))
