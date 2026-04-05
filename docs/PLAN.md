# Development Plan

## Goal

Enable smart charging of electric vehicles that:
1. Charges during the cheapest electricity hours (using Tibber prices)
2. Uses excess solar energy when available

## Current State

### Implemented Features

- **Price-aware charging**: `PriceAwarePlanner` selects cheapest electricity hours using Tibber API
- **Power production monitoring**: Listens to `power_production_topic` for real-time solar production data
- **Solar priority fields**: `ChargingStep` has `solar_priority` and `solar_max_current` fields (not actively used)
- **Charger integrations**: CTEK and Zaptec chargers supported
- **MQTT communication**: Full publish/subscribe for monitoring and control

### What's Missing

The system currently:
- Does NOT use solar production forecasts when planning charging times
- Does NOT dynamically adjust charging based on real-time solar excess
- Does NOT combine electricity prices with solar availability for optimal scheduling
- Does NOT replan optimal hours after solar charging

---

## Roadmap

### Phase 1: Solar Price Provider (High Priority)

**Objective**: Create a price provider that combines Tibber electricity prices with solar production forecasts.

**Tasks**:
1. [ ] Create `SolarPriceProvider` class in `price_providers.py`
   - Wraps `TibberPriceProvider` for electricity prices
   - Adds solar production data (from Tibber API or MQTT)
   - Scores hours based on: electricity price - solar benefit

2. [ ] Implement solar scoring logic
   - When solar production > threshold, treat hour as "free"
   - Prioritize hours with high solar production

**Files to modify**:
- `src/smart_charger/price_providers.py`

### Phase 2: Update PriceAwarePlanner (High Priority)

**Objective**: Modify the planner to factor in solar excess when selecting hours.

**Tasks**:
1. [ ] Update `PriceAwarePlanner` to accept solar price provider
2. [ ] Modify scoring algorithm to weight solar availability
3. [ ] Ensure `ChargingStep.solar_priority` is set correctly when solar is expected

**Files to modify**:
- `src/smart_charger/planner.py`

### Phase 3: Dynamic Real-Time Charging (Medium Priority)

**Objective**: Adjust charging current based on actual solar production at runtime.

**Tasks**:
1. [ ] In `charger_loop`, read current `power_production`
2. [ ] Calculate solar excess: `production - consumption`
3. [ ] Dynamically adjust charging current:
   - High solar excess → increase to max current
   - Low/no solar excess → reduce to minimum/scheduled current

**Files to modify**:
- `src/smart_charger/smartcharger.py`

### Phase 4: Configuration Options (Medium Priority)

**Objective**: Add user-configurable settings for solar-aware charging.

**Tasks**:
1. [ ] Add configuration options to `ChargerConfiguration`:
   - `solar_enabled`: bool - Enable solar-aware charging
   - `solar_min_excess_watts`: float - Minimum solar excess to trigger full current
   - `solar_max_current`: int - Maximum current when solar is available

2. [ ] Update `smartcharger.py` to read and use these settings

**Files to modify**:
- `src/smart_charger/config.py`
- `src/smart_charger/smartcharger.py`

### Phase 5: Testing (Medium Priority)

**Objective**: Ensure reliability of solar-aware charging.

**Tasks**:
1. [ ] Write unit tests for `SolarPriceProvider`
2. [ ] Write integration tests for solar-aware planning
3. [ ] Add edge case tests (no solar data, partial data, etc.)

**Files to modify**:
- `tests/test_price_aware_planner.py`
- `tests/test_solar_planner.py` (new)

---

## Implementation Details

### SolarPriceProvider Design

```python
class SolarPriceProvider(PriceProvider):
    def __init__(
        self,
        tibber_config: TibberConfig,
        solar_provider: SolarProvider,
        min_excess_watts: float = 1000
    ):
        self.tibber_provider = TibberPriceProvider(tibber_config)
        self.solar_provider = solar_provider
        self.min_excess_watts = min_excess_watts

    def price_at(self, dt: datetime.datetime) -> float:
        electricity_price = self.tibber_provider.price_at(dt)
        solar_production = self.solar_provider.get_production(dt)
        
        # Subtract "value" of solar production
        effective_price = electricity_price - self._calculate_solar_benefit(dt)
        return max(0, effective_price)

    def _calculate_solar_benefit(self, dt: datetime.datetime) -> float:
        # Calculate kWh we could charge with solar excess
        # Multiply by electricity price to get benefit
        pass
```

### Dynamic Charging Adjustment

In `charger_loop`, add logic:

```python
# Get current solar production
solar_excess = self.power_production - self.power_consumption

# Adjust current based on solar
if solar_excess > self.config.solar_min_excess_watts:
    # Use higher current when solar is available
    adjusted_current = min(
        self.config.solar_max_current,
        charging_step.current + 6  # or calculate based on excess
    )
else:
    adjusted_current = charging_step.current
```

---

## Notes

- Tibber API provides both electricity prices AND solar production data
- The system already monitors `power_production_topic` for real-time production
- Solar forecasts can come from Tibber or from your inverter (Fronius, etc.)
