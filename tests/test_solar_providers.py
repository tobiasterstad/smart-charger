import pytest
from unittest.mock import MagicMock

from smart_charger.solar_providers import SolarChargerController
from smart_charger.config import ChargerConfiguration


class TestSolarChargerController:
    @pytest.fixture
    def config(self):
        return ChargerConfiguration.load_defaults()

    def test_update_consumption(self, config):
        controller = SolarChargerController(config)

        controller.update_consumption(2000)

        assert controller.power_consumption == 2000


class TestSolarChargerControllerWithPriceProvider:
    @pytest.fixture
    def config(self):
        return ChargerConfiguration.load_defaults()

    @pytest.fixture
    def mock_price_provider(self):
        provider = MagicMock()
        provider.price_at.return_value = 1.0  # 1 SEK/kWh
        return provider

    def test_get_effective_price_now_no_solar(self, config, mock_price_provider):
        controller = SolarChargerController(config, price_provider=mock_price_provider)
        controller.update_production(0)

        price = controller.get_effective_price(planned_energy_kwh=10.0)

        assert price == 1.0

    def test_get_effective_price_now_with_solar(self, config, mock_price_provider):
        controller = SolarChargerController(config, price_provider=mock_price_provider)
        controller.update_production(5000)

        price = controller.get_effective_price(planned_energy_kwh=10.0)

        assert price == 0.5

    def test_get_effective_price_now_with_solar_excessive(
        self, config, mock_price_provider
    ):
        controller = SolarChargerController(config, price_provider=mock_price_provider)
        controller.update_production(12000)

        price = controller.get_effective_price(planned_energy_kwh=10.0)

        assert price == 0

    def test_get_effective_price_now_no_provider(self, config):
        controller = SolarChargerController(config, price_provider=None)

        price = controller.get_effective_price(planned_energy_kwh=10.0)

        assert price == 0.0
