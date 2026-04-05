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
uv run smart-charger --start
```

## Docker

### Build

```bash
docker build -t ghcr.io/terstad/smart-charger:latest .
```

### Push

```bash
docker push ghcr.io/terstad/smart-charger:latest
```

### Run

```bash
docker run -v ~/.config/smart-charger:/root/.config/smart-charger ghcr.io/terstad/smart-charger:latest
```

The secrets file at `~/.config/smart-charger/secrets.toml` is mounted into the container.