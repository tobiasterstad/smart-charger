# Architecture

## System Overview

The Smart Charger system follows an event-driven architecture with MQTT for communication between components.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SmartCharger                             │
│  (Main controller - smartcharger.py)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  CTEK        │    │  Zaptec      │    │  Planner     │       │
│  │  Charger     │    │  Charger     │    │  (PriceAware)│       │
│  │              │    │              │    │              │       │
│  │ - start()    │    │ - start()    │    │ - plan()     │       │
│  │ - stop()     │    │ - stop()     │    │              │       │
│  │ - set_curr() │    │ - set_curr( )│    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                  │                    │               │
│         └──────────────────┴────────────────────┘               │
│                            │                                    │
│  ┌─────────────────────────┴───────────────────────────┐        │
│  │              SessionManager                         │        │
│  │  - Manages charging sessions                        │        │
│  │  - Coordinates between vehicles and chargers        │        │
│  └─────────────────────────────────────────────────────┘        │
│                            │                                    │
│  ┌─────────────────────────┴───────────────────────────┐        │
│  │              MessageListener / MessageSender        │        │
│  │  - MQTT communication                               │        │
│  │  - Publish/subscribe to topics                      │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### SmartCharger (smartcharger.py)

Main controller that coordinates all components:

- **charger_loop**: Async loop that monitors charging sessions and controls chargers
- **send_status_loop**: Publishes status updates to MQTT
- Event handlers for:
  - Session start/stop
  - Target SOC reached
  - Power consumption/production changes

### Chargers (chargers.py)

BaseCharger abstract class with implementations:

- **CtekCharger**: CTEK charger integration
- **ZaptecCharger**: Zaptec charger integration

### Planner (planner.py)

Charging plan generation:

- **SimpleHourPlanner**: Basic hourly scheduling (00:00-07:00 at 16A, otherwise 6A)
- **PriceAwarePlanner**: Price-optimized scheduling using Tibber prices
- **BasicPlanner**: Hardcoded test planner

### Price Providers (price_providers.py)

- **TibberPriceProvider**: Fetches real-time electricity prices from Tibber API
- **NightProvider**: Simple night-hour pricing
- **PriceProvider Protocol**: Interface for custom price providers

### Tibber Integration (tibber/)

- **tibber_util.py**: Tibber API client
- **tariff.py**: Tariff calculations

### Session Management (session.py)

- **SessionManager**: Tracks active charging sessions
- **ChargingSession**: Individual session state

## Data Flow

1. **Vehicle connects** → MessageListener detects → SessionManager creates session
2. **Session starts** → Planner generates charging plan → Charger receives instructions
3. **Charger loop** → Monitors plan → Starts/stops charging at scheduled times
4. **Status updates** → Published to MQTT → Available for home automation

## MQTT Topics

### Input Topics (subscribed)

| Topic                               | Payload  | Description                               |
|-------------------------------------|----------|-------------------------------------------|
| `{prefix}/chargers/{id}/connected`  | boolean  | Charger connection status                 |
| `{prefix}/chargers/{id}/status`     | string   | Charger status (charging, finished, etc.) |
| `{vehicle_soc_topic}`               | int      | Vehicle state of charge (0-100)           |
| `{vehicle_connected_topic}`         | boolean  | Vehicle connection status                 |
| `{power_consumption_topic}`         | float    | Current power consumption (watts)         |
| `{power_production_topic}`          | float    | Current solar production (watts)          |

### Output Topics (published)

| Topic                              | Payload | Description                  |
|------------------------------------|---------|------------------------------|
| `{prefix}/sessions/{id}`           | JSON    | Charging session details     |
| `{prefix}/chargers/{id}/charging`  | boolean | Is charger actively charging |
| `{prefix}/vehicles/{id}/connected` | boolean | Vehicle connection status    |
| `{prefix}/vehicles/{id}/soc`       | int     | Vehicle state of charge      |
| `terstad/energy/tariff`            | boolean | Current tariff status        |
| `terstad/energy/high_load`         | boolean | High load warning            |

## Configuration

See [Configuration Guide](CONFIGURATION.md) for details on:
- MQTT broker settings
- Charger configuration
- Vehicle settings
- Planner settings
