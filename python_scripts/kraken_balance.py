#!/usr/bin/env python
import krakenex
import paho.mqtt.client as mqtt
import requests
import logging
import yaml

# External API for conversion rates
conversion_api_url = "https://open.er-api.com/v6/latest/USD"

# Change logging configuration to output to console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # This sends output to console
    ]
)

def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:  # Note the path is /config inside container
        return yaml.safe_load(file)

secrets = load_secrets()

# Use secrets
api_key = secrets["kraken_api_key"]
api_secret = secrets["kraken_api_secret"]
mqtt_broker = secrets["mqtt_broker"]
mqtt_port = secrets["mqtt_port"]
mqtt_user = secrets["mqtt_username"]
mqtt_password = secrets["mqtt_password"]

# Initialize Kraken API client
api = krakenex.API()
api.key = api_key
api.secret = api_secret

def get_account_balances():
    logging.info("Querying account balances...")
    try:
        response = api.query_private('Balance')
        if response.get('error'):
            logging.error(f"Error fetching balances: {response['error']}")
            return None

        balances = response.get('result', {})
        ltc_balance = float(balances.get('XLTC', 0))
        doge_balance = float(balances.get('XXDG', 0))

        logging.info(f"Retrieved balances: LTC={ltc_balance}, DOGE={doge_balance}")
        return ltc_balance, doge_balance
    except Exception as e:
        logging.exception(f"An error occurred while fetching balances: {str(e)}")
        return None

def get_asset_prices():
    logging.info("Querying asset prices...")
    try:
        response = api.query_public('Ticker', {'pair': 'XLTCZUSD,XDGUSD'})
        if response.get('error'):
            logging.error(f"Error fetching asset prices: {response['error']}")
            return None

        prices = response.get('result', {})
        ltc_price_usd = float(prices.get('XLTCZUSD', {}).get('c', [0])[0])
        doge_price_usd = float(prices.get('XDGUSD', {}).get('c', [0])[0])

        logging.info(f"Retrieved prices: LTC/USD={ltc_price_usd}, DOGE/USD={doge_price_usd}")
        return ltc_price_usd, doge_price_usd
    except Exception as e:
        logging.exception(f"An error occurred while fetching asset prices: {str(e)}")
        return None

def get_conversion_rates():
    logging.info("Querying conversion rates from external API...")
    try:
        response = requests.get(conversion_api_url)
        if response.status_code == 200:
            data = response.json()
            usd_to_cad = data['rates']['CAD']
            usd_to_eur = data['rates']['EUR']
            logging.info(f"Retrieved conversion rates: USD/CAD={usd_to_cad}, USD/EUR={usd_to_eur}")
            return usd_to_cad, usd_to_eur
        else:
            logging.error(f"Error fetching conversion rates: HTTP {response.status_code}")
            return None
    except Exception as e:
        logging.exception(f"An error occurred while fetching conversion rates: {str(e)}")
        return None

def publish_to_mqtt(topic, message):
    try:
        client = mqtt.Client()
        client.username_pw_set(mqtt_user, mqtt_password)
        client.connect(mqtt_broker, mqtt_port, 60)
        client.publish(topic, message)
        logging.info(f"Published to {topic}: {message}")
        client.disconnect()
    except Exception as e:
        logging.exception(f"An error occurred while publishing to MQTT: {str(e)}")

def main():
    logging.info("Starting Kraken balance script...")
    balances = get_account_balances()
    prices = get_asset_prices()
    rates = get_conversion_rates()

    if balances and prices and rates:
        ltc_balance, doge_balance = balances
        ltc_price_usd, doge_price_usd = prices
        usd_to_cad, usd_to_eur = rates

        # Log raw values
        logging.debug(f"LTC Balance: {ltc_balance}, DOGE Balance: {doge_balance}")
        logging.debug(f"LTC/USD Price: {ltc_price_usd}, DOGE/USD Price: {doge_price_usd}")
        logging.debug(f"USD/CAD Rate: {usd_to_cad}, USD/EUR Rate: {usd_to_eur}")

        # Calculate total balance in USD
        total_usd = (ltc_balance * ltc_price_usd) + (doge_balance * doge_price_usd)
        logging.debug(f"Total USD: {total_usd}")

        # Calculate total balance in CAD and EUR
        total_cad = total_usd * usd_to_cad
        total_eur = total_usd * usd_to_eur
        logging.debug(f"Total CAD: {total_cad}, Total EUR: {total_eur}")

        # Publish balances to MQTT
        publish_to_mqtt('kraken/balance_ltc', round(ltc_balance, 8))
        publish_to_mqtt('kraken/balance_doge', round(doge_balance, 8))
        publish_to_mqtt('kraken/balance_total_usd', round(total_usd, 2))
        publish_to_mqtt('kraken/balance_total_cad', round(total_cad, 2))
        publish_to_mqtt('kraken/balance_total_eur', round(total_eur, 2))

    logging.info("Kraken balance script finished.")

if __name__ == '__main__':
    main()

