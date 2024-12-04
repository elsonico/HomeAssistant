#!/usr/bin/env python
import requests
import time
import hmac
import hashlib
import paho.mqtt.client as mqtt
import yaml
import os
import logging

# Logging configuration
LOG_MSG_FORMAT = '%(asctime)s,%(msecs)03d %(levelname)s [%(filename)s:%(lineno)d] - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'
LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_MSG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("get_binance_balance")

def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Use secrets in your script
API_KEY = secrets["binance_api_key2"]
SECRET_KEY = secrets["binance_secret_key2"]

# CoinMarketCap API credentials
COINMARKETCAP_API_KEY = secrets["coinmarketcap_api_key"]
COINMARKETCAP_API_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

# MQTT broker details
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = 1883
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]
MQTT_TOPICS = {
    "LTC": "binance2/balance_ltc",
    "DOGE": "binance2/balance_doge", 
    "BTC": "binance2/balance_btc",
    "XRP": "binance2/balance_xrp",
    "PEPE": "binance2/balance_pepe",
    "BNB": "binance2/balance_bnb",
    "TOTAL_USD": "binance2/balance_total_usd",
    "TOTAL_CAD": "binance2/balance_total_cad",
    "TOTAL_EUR": "binance2/balance_total_eur",
}

def get_binance_balance(asset):
    base_url = "https://api.binance.com"
    endpoint = "/api/v3/account"
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"

    # Create HMAC SHA256 signature
    signature = hmac.new(SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"

    headers = {
        "X-MBX-APIKEY": API_KEY
    }

    logging.debug("Requesting Binance balance with URL: %s", url)
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        logging.debug("Received response: %s", data)
        for balance in data["balances"]:
            if balance["asset"] == asset:
                logging.info("%s Balance: %s", asset, balance['free'])
                return float(balance["free"])
        logging.warning("%s balance not found in response.", asset)
    else:
        logging.error("Error %s: %s", response.status_code, response.text)
    return None

def get_conversion_rates():
    try:
        logging.info("Fetching conversion rates from CoinMarketCap...")
        currencies = ["USD", "CAD", "EUR"]
        conversion_rates = {"LTC": {}, "DOGE": {}, "BTC": {}, "XRP": {}, "PEPE": {}, "BNB": {}}

        for currency in currencies:
            params = {
                "symbol": "LTC,DOGE,BTC,XRP,PEPE,BNB",
                "convert": currency
            }
            headers = {
                "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY
            }
            response = requests.get(COINMARKETCAP_API_URL, headers=headers, params=params)
            logging.debug("Response content for %s: %s", currency, response.content.decode('utf-8'))
            response.raise_for_status()

            data = response.json().get("data", {})
            conversion_rates["LTC"][currency.lower()] = data["LTC"]["quote"][currency]["price"]
            conversion_rates["DOGE"][currency.lower()] = data["DOGE"]["quote"][currency]["price"]
            conversion_rates["BTC"][currency.lower()] = data["BTC"]["quote"][currency]["price"]
            conversion_rates["XRP"][currency.lower()] = data["XRP"]["quote"][currency]["price"]
            conversion_rates["PEPE"][currency.lower()] = data["PEPE"]["quote"][currency]["price"]
            conversion_rates["BNB"][currency.lower()] = data["BNB"]["quote"][currency]["price"]

        logging.info("Retrieved conversion rates: %s", conversion_rates)
        return conversion_rates

    except requests.exceptions.RequestException as e:
        logging.error("Error fetching conversion rates from CoinMarketCap: %s", e)
        return None


def publish_to_mqtt(topic, message):
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(topic, message)
        logging.info("Published %s to MQTT topic %s", message, topic)
        client.disconnect()
    except Exception as e:
        logging.error("An error occurred while publishing to MQTT: %s", e)

if __name__ == "__main__":
    logging.info("Starting Binance balance retrieval and publish script.")
    balances = {asset: get_binance_balance(asset) for asset in \
                MQTT_TOPICS.keys() if asset in ["LTC", "DOGE", "BTC", "XRP", "PEPE", "BNB"]}
    rates = get_conversion_rates()

    if balances and rates:
        # Publish individual balances
        for asset, balance in balances.items():
            if balance is not None:
                publish_to_mqtt(MQTT_TOPICS[asset], f"{balance:.8f}")

        # Calculate and publish total balances in USD, CAD, EUR
        total_usd = sum(
            balances[asset] * rates[asset]["usd"] for asset in balances if balances[asset] is not None and asset in rates
        )
        total_cad = sum(
            balances[asset] * rates[asset]["cad"] for asset in balances if balances[asset] is not None and asset in rates
        )
        total_eur = sum(
            balances[asset] * rates[asset]["eur"] for asset in balances if balances[asset] is not None and asset in rates
        )

        publish_to_mqtt(MQTT_TOPICS["TOTAL_USD"], f"{total_usd:.2f}")
        publish_to_mqtt(MQTT_TOPICS["TOTAL_CAD"], f"{total_cad:.2f}")
        publish_to_mqtt(MQTT_TOPICS["TOTAL_EUR"], f"{total_eur:.2f}")

    logging.info("Binance balance script finished.")

