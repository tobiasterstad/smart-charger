# AGENTS.md - Smart Charger Project Guidelines

## Project Overview

Smart Charger is a Python project for intelligently controlling electric vehicle chargers based on electricity prices and solar energy production. It uses MQTT for communication and Tibber API for price data.

**Python Version**: 3.13+  
**Build System**: hatch  
**Package Manager**: uv

---

## Commands

### Running Tests

```bash
# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_solar_providers.py

# Run a single test
uv run pytest tests/test_solar_providers.py::TestMQTTSolarProvider::test_default_profile

# Run with coverage
uv run pytest --cov=src/smart_charger --cov-report=term-missing
```

### Linting

```bash
# Run ruff linter
uv run ruff check src/

# Format code
uv run ruff format src/
```

### Building

```bash
# Build package
uv build

# Install in editable mode
uv pip install -e .
```

---

## Code Style Guidelines

### Imports

- Use absolute imports: `from smart_charger.config import ChargerConfiguration`
- Group imports in this order: stdlib, third-party, local
- Use `from __future__ import annotations` for forward references
- Sort imports alphabetically within groups

```python
from __future__ import annotations

import datetime
import logging
from typing import Protocol, Optional

from pydantic import BaseModel, Field

from smart_charger.config import ChargerConfiguration
from smart_charger.price_providers import PriceProvider
```

### Types

- Use Python 3.13+ type hints
- Use `Optional[X]` instead of `X | None` for compatibility
- Use `list[X]`, `dict[X, Y]` (not List, Dict from typing)
- Add return types to all functions and methods

```python
def get_now() -> datetime.datetime:
    return datetime.datetime.now()

class ChargingStep(BaseModel):
    id: str
    start_time: datetime.datetime
    stop_time: Optional[datetime.datetime] = None
```

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `ChargingStep`, `PriceAwarePlanner`)
- **Functions/methods**: `snake_case` (e.g., `get_now()`, `price_at()`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`)
- **Private methods**: prefix with underscore (e.g., `_update_prices()`)

### Pydantic Models

- Use `BaseModel` for data classes with validation
- Use `Field()` for fields with defaults or validation
- Place optional fields with defaults last

```python
class ChargingStep(BaseModel):
    id: str
    start_time: datetime.datetime
    stop_time: Optional[datetime.datetime] = None
    current: int = Field(default=16, description="Charging current in Amperes")
    description: str
```

### Error Handling

- Use exceptions for unexpected errors
- Catch specific exceptions, not bare `Exception`
- Log errors before re-raising

```python
try:
    latest_date = max(p.startsAt.date() for p in self.prices)
except Exception:
    return True  # Treat malformed data as old
```

### Protocols

Use Protocol for interface definitions:

```python
class PriceProvider(Protocol):
    def price_at(self, dt: datetime.datetime) -> float: ...
```

### Docstrings

- Use Google-style docstrings for public APIs
- Keep docstrings concise; prefer code comments for implementation details

---

## Project Structure

```
src/smart_charger/
├── __init__.py
├── chargers.py        # Charger abstractions and implementations
├── config.py         # Configuration models
├── messages.py       # MQTT message handling
├── planner.py        # Charging planners
├── price_providers.py # Electricity price providers
├── solar_providers.py # Solar production providers
├── session.py       # Charging session management
├── smartcharger.py  # Main application
├── vehicle.py       # Vehicle models
├── zaptec.py       # Zaptec charger integration
├── secret.py       # Secrets (API keys, credentials)
├── tibber/
│   ├── tibber_util.py
│   └── tariff.py
└── lib/
    └── ctek/       # CTEK charger integration
```

---

## Testing Guidelines

- Place tests in `tests/` directory
- Name test files as `test_<module>.py`
- Use pytest with the `test_` prefix for functions
- Use `unittest.mock.MagicMock` for mocking
- Test both success and failure cases

---

## Key Patterns

### Provider Pattern

Implement `PriceProvider` or `SolarProvider` Protocol to add new price/solar sources:

```python
class TibberPriceProvider(PriceProvider):
    def __init__(self, tibber_config: TibberConfig):
        ...

    def price_at(self, dt: datetime.datetime) -> float:
        ...
```

### Event Listeners

Use callback lists for event-driven communication:

```python
self._on_power_production_changed: list[Callable[[float], None]] = []

def add_on_power_production_changed(self, callback: Callable[[float], None]):
    self._on_power_production_changed.append(callback)
```

---

## Configuration

Configuration is managed via:
- `src/smart_charger/config.py` - Default configuration (ChargerConfiguration)
- `src/smart_charger/secret.py` - API keys and credentials

Do not hardcode settings, use the config files instead since the app should be generic and configurable.

---

## MQTT Topics

### Incoming Topics (devices → smart-charger)

Raw device data published by external devices (chargers, vehicles, energy monitors):

| Topic | Payload | Source |
|-------|---------|--------|
| `terstad/devices/chargers/{id}/status` | Zaptec OperatingMode (e.g., `"Connected_Charging"`) | Charger |
| `terstad/devices/vehicles/{id}/connected` | boolean | Vehicle |
| `terstad/devices/vehicles/{id}/soc` | integer (0-100) | Vehicle |
| `terstad/energy/consumption` | float (watts) | Energy monitor |
| `terstad/energy/production` | float (watts) | Solar inverter |

### Outgoing Topics (smart-charger → external)

Processed status and control data published by smart-charger:

| Topic | Payload | Purpose |
|-------|---------|---------|
| `terstad/smartcharger/chargers/{id}/status` | ChargerStatus (e.g., `"charging"`) | Status broadcast |
| `terstad/smartcharger/chargers/{id}/current` | float (Amperes) | Current setting |
| `terstad/smartcharger/vehicles/{id}/connected` | boolean | Vehicle status |
| `terstad/smartcharger/vehicles/{id}/soc` | integer | Vehicle SOC |
| `terstad/smartcharger/sessions/{id}` | JSON | Session details |
| `terstad/energy/high_load` | boolean | High load alert |
| `terstad/energy/tariff` | boolean | Tariff status |

# Run the smart-charger

## Connect vehicle leaf

uv run mqtt-tool --connect-vehicle leaf:true

## Connect charger 

uv run mqtt-tool --connect-charger gpn018087:true

---

## Solar-Aware Charging Requirements

### Overview

The smart charger supports solar-aware charging that combines solar production with grid electricity prices to determine when it's cheapest to charge. The system calculates an "effective price" that accounts for solar energy value.

### How It Works

**Effective Price Calculation:**
- `effective_price = grid_price - solar_benefit`
- `solar_benefit = (solar_watts / 1000) * grid_price` (kWh of solar × grid price)
- Solar benefit applies at **all production levels**, not just when there's excess

**Example:**
| Hour | Grid Price | Solar Prod | Solar Benefit | Effective Price |
|------|------------|------------|---------------|-----------------|
| 10:00 | 0.30 EUR/kWh  | 2800W | 0.84 | -0.54 (free) |
| 08:00 | 0.25 EUR/kWh | 1200W | 0.30 | -0.05 (near free) |
| 17:00 | 0.22 EUR/kWh | 800W | 0.18 | 0.04 |
| 06:00 | 0.18 EUR/kWh | 100W | 0.02 | 0.16 |

### Current Adjustment with Rate Limiting

The charger adjusts current based on effective price, but limits how often changes can occur to protect the charger hardware.

**Behavior:**
- **Every 15 minutes** (configurable), the system checks if current should be adjusted
- If effective price < `solar_max_effective_price` (default 0.15 EUR/kWh): charge at **16A** (max)
- If effective price >= `solar_max_effective_price`: charge at **6A** (min)
- If less than 15 minutes since last change: **maintain current**

This protects against rapid cycling when clouds pass over - if solar drops suddenly, the charger waits up to 15 minutes before adjusting down.

### Configuration Options

New configuration options in `config.py`:

```python
solar_surplus_charging: bool = True          # Enable solar surplus charging
solar_min_excess_watts: float = 1500         # Min excess for legacy surplus mode
solar_max_effective_price: float = 0.15      # Max effective price for max current (EUR/kWh)
solar_min_current_amps: int = 6              # Minimum current when solar not cheap enough
solar_charge_interval_minutes: int = 15      # Min time between current changes
```

### Key Benefits

1. **Charge during daylight** even when solar alone isn't enough - the effective price accounts for any solar contribution
2. **Automatic optimization** - no manual intervention needed for price/solar tradeoffs
3. **Hardware protection** - rate limiting prevents excessive current changes
4. **Flexible thresholds** - all settings are configurable for different setups