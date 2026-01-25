import json

from smart_charger.tibber.tariff import TibberCostPerHour


class TestTariff:
    def test_example(self):
        tibber = TibberCostPerHour()
        data = tibber.get_cost_per_hour(number_of_months=12)
        top_peaks = tibber.get_top_consumption_hours(data)
        print(json.dumps(top_peaks.model_dump(), indent=4, default=str))

    def test_monthly_consumption(self):
        tibber = TibberCostPerHour()
        data = tibber.get_monthly_consumption()
        print(json.dumps(data.model_dump(), indent=4, default=str))
