import os
from typing import Optional
from datetime import datetime
from collections import defaultdict

import requests
import yaml
from pydantic import BaseModel, Field, computed_field


class PeakHour(BaseModel):
    time: datetime
    consumption: float

class MonthlyPeaks(BaseModel):
    month: int
    peak_hours: list[PeakHour]
    total_consumption: Optional[float] = None

    @computed_field
    @property
    def month_name(self) -> str:
        return datetime(1900, self.month, 1).strftime('%B')

    @computed_field
    @property
    def tariff_enabled(self) -> bool:
        if self.month in [1,2,3,11,12]:
            return True
        return False

    @computed_field
    @property
    def mean_consumption(self) -> float:
        if not self.peak_hours:
            return 0.0
        total = sum(hour.consumption for hour in self.peak_hours)
        return total / len(self.peak_hours)

    @computed_field
    @property
    def tariff_cost(self) -> float:
        if not self.tariff_enabled:
            return 0.0

        tarriff_cost = 57.17
        return tarriff_cost * self.mean_consumption

    @computed_field
    @property
    def transfer_cost(self) -> float:
        transfer_cost = 52.66 / 100.0
        if self.total_consumption is None:
            return 0.0
        return transfer_cost * self.total_consumption

    @computed_field
    @property
    def total_cost(self) -> float:
        fixed_cost = 6309
        cost = fixed_cost / 12 + self.tariff_cost + self.transfer_cost
        return cost

    @computed_field
    @property
    def cost_per_kwh(self) -> float:
        if self.total_consumption is None or self.total_consumption == 0:
            return 0.0
        return self.total_cost / self.total_consumption

    @computed_field
    @property
    def comparison_cost(self) -> float:
        return 6011 / 12 + (79.50 / 100.0) * self.total_consumption

class PeaksResponse(BaseModel):
    monthly_peaks: list[MonthlyPeaks] = Field(alias="monthlyPeaks")


# Tibber specific models
class TibberNode(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime
    consumption: Optional[float]

class TibberPageInfo(BaseModel):
    start_cursor: str = Field(alias="startCursor")
    end_cursor: str = Field(alias="endCursor")
    has_next_page: bool = Field(alias="hasNextPage")
    has_previous_page: bool = Field(alias="hasPreviousPage")

class TibberConsumptionResponse(BaseModel):
    nodes: list[TibberNode]
    page_info: TibberPageInfo = Field(alias="pageInfo")

class TibberCostPerHour:
    def __init__(self):
        with open(os.path.expanduser("~/.ctek/config.yaml"), "r") as f:
            config = yaml.safe_load(f.read())
            self.api_key = config.get("charger").get("tibber").get("api_key")

    def get_cost_per_hour(self, number_of_months: int = 3) -> PeaksResponse:
        all_nodes = []
        previous_page = None
        for i in range(0, number_of_months):
            consumption = self._get_hourly_consumption(previous_page=previous_page)
            all_nodes.extend(consumption.nodes)
            previous_page = consumption.page_info.start_cursor

        grouped = defaultdict(list)
        for node in all_nodes:
            grouped[(node.from_.year, node.from_.month)].append(
                PeakHour(time=node.from_, consumption=node.consumption if node.consumption is not None else 0.0)
            )
        monthly_peaks = [
            MonthlyPeaks(month=year_and_month[1], peak_hours=hours.sort(key=lambda x: x.time) or hours)
            for year_and_month, hours in grouped.items()
        ]
        result = PeaksResponse(monthlyPeaks=monthly_peaks)
        #print(json.dumps(result.model_dump(by_alias=True), indent=4, default=str))
        return result

    def get_top_consumption_hours(self, peak_data: PeaksResponse, n=3):
        # Sortera efter förbrukning, högsta först

        monthly_consumption = self.get_monthly_consumption()
        for month in peak_data.monthly_peaks:
            peak_hours = [
                hour
                for hour in month.peak_hours
                if hour.consumption is not None
                   and 7 <= hour.time.hour < 21
            ]

            top_hours = sorted(peak_hours, key=lambda x: x.consumption, reverse=True)[:n]
            month.peak_hours = top_hours

            # Beräkna total förbrukning för månaden
            month.total_consumption = 0.0
            for m in monthly_consumption.nodes:
                if m.from_.month == month.month and m.from_.year == month.peak_hours[0].time.year:
                    month.total_consumption = m.consumption
                    break

        #top3 = sorted(nodes, key=lambda x: x["consumption"], reverse=True)[:3]
        #for i, hour in enumerate(top3, 1):
        #    print(f"Topp {i}: {hour['from']} - {hour['consumption']} kWh")

        return peak_data

    def get_monthly_consumption(self, previous_page: str = None) -> TibberConsumptionResponse:
        url = "https://api.tibber.com/v1-beta/gql"
        headers = {"Authorization": "Bearer " + self.api_key}

        query = """
        query Consumption($page: String) {
          viewer {
            homes {
              consumption(resolution: MONTHLY, last: 12, before: $page) {
                nodes {
                  from
                  to
                  consumption
                }
                pageInfo {
                    startCursor
                    endCursor
                    hasNextPage
                    hasPreviousPage
                }
              }
            }
          }
        }
        """

        variables = {"page": previous_page} if previous_page else {}
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers).json()
        nodes = response["data"]["viewer"]["homes"][0]["consumption"]["nodes"]

        consumption = TibberConsumptionResponse.parse_obj(response["data"]["viewer"]["homes"][0]["consumption"])
        return consumption

    def _get_hourly_consumption(self, previous_page: str = None) -> TibberConsumptionResponse:
        url = "https://api.tibber.com/v1-beta/gql"
        headers = {"Authorization": "Bearer " + self.api_key}

        query = """
        query Consumption($page: String) {
          viewer {
            homes {
              consumption(resolution: HOURLY, last: 720, before: $page) {
                nodes {
                  from
                  to
                  consumption
                }
                pageInfo {
                    startCursor
                    endCursor
                    hasNextPage
                    hasPreviousPage
                }
              }
            }
          }
        }
        """

        variables = {"page": previous_page} if previous_page else {}
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers).json()
        nodes = response["data"]["viewer"]["homes"][0]["consumption"]["nodes"]

        consumption = TibberConsumptionResponse.parse_obj(response["data"]["viewer"]["homes"][0]["consumption"])
        return consumption


class TariffCalculator:

    def __init__(self, tariff_data):
        self.tariff_data = tariff_data

    def get_price_at(self, timestamp):
        """
        Get the electricity price at a specific timestamp.

        :param timestamp: The timestamp to check the price for.
        :return: The price at the given timestamp.
        """
        # Assuming tariff_data is a dict with timestamps as keys and prices as values
        return self.tariff_data.get(timestamp, None)
