"""Charging planner module.

This module provides various charging planners that optimize when and how
to charge electric vehicles based on different criteria:

- SimpleHourPlanner: Time-based scheduling prioritizing night hours
- PriceAwarePlanner: Optimizes for lowest electricity price
- SolarPriceAwarePlanner: Combines solar production with price optimization

Usage:
    from smart_charger.planner import PriceAwarePlanner, ChargingPlan

    planner = PriceAwarePlanner(config, price_provider=tibber_provider)
    plan = planner.plan_charging(vehicle)
"""

# Models
from .models import (
    get_now,
    ChargingStep,
    ChargingPlan,
    Candidate,
    SolarCandidate,
)

# Base classes and protocols
from .base import (
    BasePlanner,
    PriceProvider,
    SolarForecastProvider,
)

# Planners
from .simple import (
    HourlyPlanner,
    BasicPlanner,
    SimpleHourPlanner,
)

from .price import PriceAwarePlanner

from .solar_price import SolarPriceAwarePlanner

# Re-export VehicleStatus for backward compatibility
# (it was previously importable from planner)
from smart_charger.vehicle import VehicleStatus

__all__ = [
    # Models
    "get_now",
    "ChargingStep",
    "ChargingPlan",
    "Candidate",
    "SolarCandidate",
    # Base
    "BasePlanner",
    "PriceProvider",
    "SolarForecastProvider",
    # Planners
    "HourlyPlanner",
    "BasicPlanner",
    "SimpleHourPlanner",
    "PriceAwarePlanner",
    "SolarPriceAwarePlanner",
    # Re-exports
    "VehicleStatus",
]
