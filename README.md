# Smart Charger

A system for intelligently controlling electric vehicle chargers based on electricity prices and solar energy production.

## Features

- **Price-Aware Charging**: Automatically charge during cheapest electricity hours using Tibber price data
- **Solar Integration**: Utilize excess solar production for free charging
- **Multi-Charger Support**: Support for CTEK and Zaptec chargers
- **Multi-Vehicle Support**: Manage multiple vehicles with different target SOC levels
- **MQTT Integration**: Full MQTT-based communication for monitoring and control

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System architecture overview
- [Plan](docs/PLAN.md) - Development roadmap and planned features

## Quick Start

```bash
# Run the smart charger
python -m smart_charger --start
```