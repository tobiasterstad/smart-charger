from __future__ import annotations

import datetime
from typing import Protocol, Optional

from pydantic import BaseModel


class TariffProvider(Protocol):
    def is_high_tariff(self, timestamp: Optional[datetime.datetime] = None) -> bool: ...


class GenericTariffConfig(BaseModel):
    topic: str
    model: str
    months: list[int]
    days: list[int]
    hours: list[int]


class WinterPeak1(GenericTariffConfig):
    model: str = "winter_peak_1"
    months: list[int] = [1, 2, 3, 10, 11, 12]
    days: list[int] = [0, 1, 2, 3, 4, 5, 6]
    hours: list[int] = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]


class WinterPeak2(GenericTariffConfig):
    model: str = "winter_peak_2"
    months: list[int] = [1, 2, 3, 10, 11, 12]
    days: list[int] = [1, 2, 3, 4, 5]
    hours: list[int] = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]


class WinterPeakTariffProvider:
    def __init__(self, config: GenericTariffConfig):
        self.config = config

    def is_high_tariff(self, timestamp: Optional[datetime.datetime] = None) -> bool:
        if timestamp is None:
            timestamp = datetime.datetime.now()
        if timestamp.month not in self.config.months:
            return False
        if timestamp.weekday() not in self.config.days:
            return False
        if timestamp.hour not in self.config.hours:
            return False
        return True


def create_tariff_provider(config: GenericTariffConfig) -> TariffProvider:
    if config.model in ["winter_peak_1", "winter_peak_2"]:
        return WinterPeakTariffProvider(config)
    raise ValueError(f"Unknown tariff model: {config.model}")
