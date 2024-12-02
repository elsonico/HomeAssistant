#!/usr/bin/env python
import logging
import requests
import paho.mqtt.client as mqtt
import krakenex
import yaml

# Load secrets
def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:  # Note the path is /config inside container
        return yaml.safe_load(file)

secrets = load_secrets()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT broker details
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = secrets["mqtt_port"]
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]

# Kraken API client
api = krakenex.API()
api.key = secrets["kraken_api_key"]
api.secret = secrets["kraken_api_secret"]

# Cryptocurrency symbols to fetch
CRYPTO_SYMBOLS = ["LTC", "DOGE", "BTC", "ETH", "XRP", "SOL", "SHIB", "PEPE"]

# Fiat currency pairs to fetch
FIAT_PAIRS = {
    "usd_eur": "ZEURZUSD",
    "usd_cad": "ZUSDZCAD"
}

# MQTT topic bases
MQTT_TOPIC_BASE = "cryptocoin/value_"
CURRENCY_TOPIC_BASE = "currency/"

# Initialize MQTT client
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Kraken API symbols mapping
KRAKEN_SYMBOLS = {
    "LTC": "XLTCZUSD",
    "DOGE": "XDGUSD",
    "BTC": "XXBTZUSD",
    "ETH": "XETHZUSD",
    "XRP": "XXRPZUSD",
    "SOL": "SOLUSD",
    "SHIB": "SHIBUSD",
    "PEPE": "PEPEUSD",
}

def get_xpm_price_in_usd():
    url = 'https://api.coincap.io/v2/assets/primecoin'
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()
        price_usd = data['data']['priceUsd']
        return float(price_usd)
    except requests.exceptions.HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')
    except Exception as err:
        print(f'Other error occurred: {err}')

# Function to fetch cryptocurrency prices
def fetch_crypto_prices():
    try:
        response = api.query_public('Ticker', {'pair': ','.join(KRAKEN_SYMBOLS.values())})
        if response['error']:
            logging.error(f"Error fetching crypto data: {response['error']}")
            return None
        prices = {
            symbol: round(float(response['result'][KRAKEN_SYMBOLS[symbol]]['c'][0]), 8)
            for symbol in CRYPTO_SYMBOLS if KRAKEN_SYMBOLS[symbol] in response['result']
        }
        return prices
    except Exception as e:
        logging.error(f"Error fetching cryptocurrency prices: {e}")
        return None

# Function to fetch exchange rates
def fetch_exchange_rates():
    try:
        response = api.query_public('Ticker', {"pair": ",".join(FIAT_PAIRS.values())})
        if response.get('error'):
            logging.error(f"Error fetching exchange rates: {response['error']}")
            return None

        rates = {
            name: round(float(response['result'][pair]['c'][0]), 8)
            for name, pair in FIAT_PAIRS.items() if pair in response['result']
        }

        if "usd_eur" in rates and "usd_cad" in rates:
            usd_eur = rates["usd_eur"]
            usd_cad = rates["usd_cad"]
            eur_usd = round(1 / usd_eur, 8)
            eur_cad = round(usd_cad * usd_eur, 8)
            cad_eur = round(1 / eur_cad, 8)

            rates.update({"eur_usd": eur_usd, "eur_cad": eur_cad, "cad_eur": cad_eur})

        return rates
    except Exception as e:
        logging.error(f"Error fetching exchange rates: {e}")
        return None

# Function to publish cryptocurrency prices to MQTT
def publish_crypto_prices(prices):
    for symbol, price in prices.items():
        topic = f"{MQTT_TOPIC_BASE}{symbol.lower()}"
        try:
            mqtt_client.publish(topic, price)
            logging.info(f"Published {symbol} price: {price} to topic: {topic}")
        except Exception as e:
            logging.error(f"Error publishing to MQTT: {e}")

# Function to publish exchange rates to MQTT
def publish_exchange_rates(rates):
    for currency_pair, rate in rates.items():
        topic = f"{CURRENCY_TOPIC_BASE}{currency_pair}"
        try:
            mqtt_client.publish(topic, rate)
            logging.info(f"Published {currency_pair} rate: {rate} to topic: {topic}")
        except Exception as e:
            logging.error(f"Error publishing exchange rates to MQTT: {e}")

# Main loop
if __name__ == "__main__":
    logging.info("Fetching cryptocurrency prices...")
    crypto_data = fetch_crypto_prices()
    xpm_price = get_xpm_price_in_usd()
    if xpm_price:
        crypto_data["XPM"] = xpm_price
    if crypto_data:
        publish_crypto_prices(crypto_data)

    logging.info("Fetching exchange rates...")
    exchange_rates = fetch_exchange_rates()
    if exchange_rates:
        publish_exchange_rates(exchange_rates)

