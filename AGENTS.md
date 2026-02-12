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

- Power consumption: `terstad/energy/consumption` (watts)
- Power production: `terstad/energy/production` (watts)
- Vehicle SOC: `terstad/vehicles/{id}/soc`
- Charger status: `terstad/smartcharger/chargers/{id}/status`
