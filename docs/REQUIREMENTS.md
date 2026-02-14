# Requirements Document

## Project Overview

**Smart Charger** is a Python application that intelligently controls electric vehicle (EV) chargers based on:
- Real-time electricity prices from Tibber API
- Solar energy production data
- Time-of-use tariffs (winter peak pricing)

## Functional Requirements

### 1. Charger Management

- **FR1.1**: Support multiple charger types (CTEK, Zaptec)
- **FR1.2**: Start/stop charging sessions remotely
- **FR1.3**: Adjust charging current (6-16A range)
- **FR1.4**: Monitor charger connection and charging status

### 2. Vehicle Management

- **FR2.1**: Support multiple vehicles with unique IDs
- **FR2.2**: Track vehicle State of Charge (SOC) via MQTT
- **FR2.3**: Configure per-vehicle target SOC (default 80%)
- **FR2.4**: Configure per-vehicle battery capacity (kWh)

### 3. Price-Aware Charging

- **FR3.1**: Fetch real-time electricity prices from Tibber API
- **FR3.2**: Plan charging during cheapest hours (PriceAwarePlanner)
- **FR3.3**: Fall back to simple hourly planner (SimpleHourPlanner)
- **FR3.4**: Support both Tibber and Simple planner types

### 4. Solar Surplus Charging

- **FR4.1**: Receive solar production data via MQTT
- **FR4.2**: Calculate solar excess (production - consumption)
- **FR4.3**: Start charging when solar excess exceeds minimum threshold (default 1500W)
- **FR4.4**: Use reduced current (6A) for solar surplus charging

### 5. Tariff Management

- **FR5.1**: Implement winter peak tariff detection
- **FR5.2**: High tariff months: January-March, October-December
- **FR5.3**: High tariff hours: 07:00-21:00
- **FR5.4**: Publish tariff status to MQTT

### 6. MQTT Communication

- **FR6.1**: Subscribe to vehicle/charger status topics
- **FR6.2**: Subscribe to power consumption/production topics
- **FR6.3**: Publish charger status updates
- **FR6.4**: Publish vehicle connection and SOC updates
- **FR6.5**: Publish charging session data

### 7. Session Management

- **FR7.1**: Create charging sessions when vehicle+charger connect
- **FR7.2**: Assign charging plans to sessions
- **FR7.3**: Stop charging when target SOC reached
- **FR7.4**: Archive completed sessions

### 8. CLI Tools

- **FR8.1**: `mqtt-tool` - Publish test messages to MQTT topics
- **FR8.2**: `smart-charger` - Main application entry point
- **FR8.3**: `ctek-tool` - CTEK charger meter service

## MQTT Topics

| Topic                                         | Direction | Description                 |
|-----------------------------------------------|-----------|-----------------------------|
| `terstad/vehicles/{id}/connected`             | In        | Vehicle connection status   |
| `terstad/vehicles/{id}/soc`                   | In        | Vehicle SOC percentage      |
| `terstad/energy/consumption`                  | In        | Power consumption (watts)   |
| `terstad/energy/production`                   | In        | Solar production (watts)    |
| `terstad/smartcharger/chargers/{id}/status`   | In        | Charger operating mode      |
| `terstad/smartcharger/chargers/{id}/charging` | Out       | Charger active status       |
| `terstad/energy/tariff`                       | Out       | High tariff status          |
| `terstad/energy/high_load`                    | Out       | High load warning           |
| `terstad/smartcharger/sessions/{id}`          | Out       | Session JSON data           |

## Configuration

All configuration is hardcoded in `src/smart_charger/config.py`:

- MQTT broker: `10.100.0.10:1883`
- Topic prefix: `terstad/smartcharger`
- Default vehicles: Nissan Leaf (40kWh), Toyota RAV4 (18kWh)
- Default chargers: CTEK, Zaptec
- Solar surplus: enabled, min 1500W
- High load threshold: 4000W

## Supported Chargers

### 1. Zaptec Charger (full implementation)

- OAuth authentication with Zaptec API
- Start/stop commands
- Adjustable current
- Status monitoring

### 2. CTEK Charger (partial implementation)

- Stub implementation for interface compatibility
- CTEK meter service available separately

## Architecture

```
smart_charger/
├── smartcharger.py      # Main application (SmartCharger class)
├── config.py           # Configuration models
├── chargers.py         # Charger abstractions
├── planner.py          # Charging planners
├── price_providers.py  # Tibber price integration
├── solar_providers.py  # Solar production handling
├── session.py          # Session management
├── messages.py         # MQTT listener/sender
├── vehicle.py          # Vehicle status model
├── zaptec.py           # Zaptec API client
├── tariff.py           # Tariff providers
├── secret.py           # API credentials
└── lib/ctek/          # CTEK integration
```

## CLI Commands

```bash
# Start smart charger
uv run smart-charger --start

# Start in read-only mode (no charger commands)
uv run smart-charger --start --read-only

# Health check
uv run smart-charger --health

# MQTT test tool
uv run mqtt-tool --connect-vehicle leaf:true
uv run mqtt-tool --connect-charger gpn018087:true
uv run mqtt-tool --production 3500
uv run mqtt-tool --consumption 2000
uv run mqtt-tool --update-soc leaf:75

# CTEK meter service
uv run ctek-tool --start --interval 900
```

## Dependencies

- pydantic (>=2.12.5) - Data validation
- pyyaml (>=6.0.3) - YAML parsing
- click (>=8.3.1) - CLI framework
- requests (>=2.32.5) - HTTP client
- paho-mqtt (>=2.1.0) - MQTT client
- mqtt-discovery (>=1.0.0) - Home Assistant MQTT discovery

## Limitations

1. Configuration is hardcoded (no external config file)
2. CTEK charger is a stub implementation
3. Secrets are hardcoded in source (not secure for production)
4. No persistent storage of session history
5. No authentication on MQTT broker
6. No unit tests in test suite (tests marked as integration)
