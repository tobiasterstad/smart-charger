from enum import Enum
import dataclasses


class DAYS(int, Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


CURRENT_LIMITS = [6, 8, 10, 12, 14, 16]

@dataclasses.dataclass
class Schedule:
    start_day: DAYS
    start_time: str
    stop_day: DAYS
    stop_time: str