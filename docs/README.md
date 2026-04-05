# Smart Charger

A system for intelligently controlling electric vehicle chargers based on electricity prices and solar energy production.

## Features

- **Price-Aware Charging**: Automatically charge during cheapest electricity hours using Tibber price data
- **Solar Integration**: Utilize excess solar production for free charging
- **Multi-Charger Support**: Support for CTEK and Zaptec chargers
- **Multi-Vehicle Support**: Manage multiple vehicles with different target SOC levels
- **MQTT Integration**: Full MQTT-based communication for monitoring and control

## Supported Chargers

- CTEK Charger
- Zaptec Charger

## Supported Vehicles

- Nissan Leaf
- Toyota RAV4
- (Configurable for any EV)

## Quick Start

```bash
# Install dependencies
pip install -e .

# Run the smart charger
python -m smart_charger --start
```

## Configuration

Configuration is managed through `src/smart_charger/config.py` and `src/smart_charger/secret.py`.

### MQTT Topics

| Topic | Description |
|-------|-------------|
| `terstad/energy/tariff` | Energy tariff status |
| `terstad/energy/consumption` | Current power consumption (W) |
| `terstad/energy/production` | Current solar production (W) |
| `terstad/energy/high_load` | High load warning |
| `terstad/smartcharger/vehicles/{id}/status` | Vehicle status |
| `terstad/smartcharger/vehicles/{id}/soc` | Vehicle state of charge |
| `terstad/smartcharger/chargers/{id}/status` | Charger status |

## Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Plan](PLAN.md) - Development roadmap and planned features
