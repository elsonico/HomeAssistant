# Home Assistant Configuration

This repository contains my personal Home Assistant configuration, focusing on cryptocurrency tracking and smart home automation. The setup includes custom Python scripts for tracking various cryptocurrency wallets and exchange balances, along with standard home automation features.

## Features

- **Cryptocurrency Tracking**
  - Binance balance monitoring
  - Kraken balance monitoring
  - Exodus wallet tracking
  - Litewallet balance tracking
  - Real-time price updates
  - Multi-currency conversion (USD, EUR, CAD)

- **Infrastructure**
  - MQTT integration
  - InfluxDB data storage
  - AWS Route53 DNS management
  - Docker deployment
  - SSL/TLS support

## Structure

Key configuration files:
- `configuration.yaml` - Main configuration
- `automations.yaml` - Automation rules
- `docker-compose.yaml` - Docker configuration
- `influxdb.yaml` - InfluxDB configuration
- `mqtt.yaml` - MQTT settings
- `notify.yaml` - Notification settings
- `sensors.yaml` - Sensor configurations
- `shell.yaml` - Shell commands

Python Scripts:
- `python_scripts/`
  - `get_binance_balance.py` - Binance balance tracking
  - `kraken_balance.py` - Kraken balance tracking
  - `exodus_mqtt.py` - Exodus wallet tracking
  - `litewallet_balance.py` - Litewallet tracking
  - `fetch_crypto_values_and_currencies.py` - Price updates

## Security

This repository follows security best practices:
- All credentials and sensitive data are stored in `secrets.yaml` (not included in repository)
- Environment variables for sensitive configuration
- SSL/TLS encryption for web interface
- Minimal permissions for service accounts

## Installation

1. Clone this repository
2. Create `secrets.yaml` with your credentials
3. Install requirements: `pip install -r python_scripts/requirements.txt`
4. Run with Docker: `docker-compose up -d`

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Disclaimer

This configuration is provided as-is. While I strive to maintain security, using this configuration in your own setup is at your own risk. Always review code and configurations before implementing them in your environment.

## Contributing

Feel free to submit issues and pull requests.
