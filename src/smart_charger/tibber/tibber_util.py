import json
from enum import Enum

import requests

from pydantic import BaseModel


class TibberConfig(BaseModel):
    api_key: str


from pydantic.dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


class DAYS(int, Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass
class PriceInfo:
    total: float
    energy: float
    tax: float
    startsAt: datetime
    level: Optional[str] = "NORMAL"


@dataclass
class PriceData:
    today: List[PriceInfo]
    tomorrow: List[PriceInfo]


@dataclass
class CurrentSubscription:
    priceInfo: PriceData


@dataclass
class Home:
    currentSubscription: CurrentSubscription


@dataclass
class Viewer:
    homes: List[Home]


@dataclass
class Data:
    viewer: Viewer


@dataclass
class Prices:
    data: Data


@dataclass
class InternalPriceData:
    day: DAYS
    hour: int
    price: float
    date_str: str


@dataclass
class PriceInterval:
    day: DAYS
    start: int
    stop: int
    items: List[InternalPriceData]


class TibberPrices:
    def __init__(self, config: TibberConfig):
        self.api_key = config.api_key

        self.url = "https://api.tibber.com/v1-beta/gql"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def today_tomorrow(self) -> Prices:
        payload = {
            "query": "{viewer {homes {currentSubscription {priceInfo {today {total energy tax startsAt level } tomorrow { total energy tax startsAt level} } } } }}"
        }
        response = requests.request(
            "POST", self.url, json=payload, headers=self.headers
        )
        if response.status_code != 200:
            raise Exception("Failed to get prices")

        return Prices(**json.loads(response.text))
