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

```
# prepare
docker buildx install
```

```bash
docker build -t ghcr.io/tobiasterstad/smart-charger:latest .

# Build multi-arch image
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/smart-charger:latest .

# Build and push multi-arch image to GitHub Container Registry
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/tobiasterstad/smart-charger:latest --push .
```

### Push

```bash
docker push ghcr.io/tobiasterstad/smart-charger:latest
```

### Run

```bash
docker run -d --name smart-charger \
  --restart=unless-stopped \
  -v ~/.config/smart-charger:/root/.config/smart-charger \
  ghcr.io/tobiasterstad/smart-charger:latest
```

The secrets file at `~/.config/smart-charger/secrets.toml` is mounted into the container.