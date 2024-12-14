#!/home/tav/.pyenv/shims/python3
import requests
import logging
import paho.mqtt.client as mqtt
import yaml

# Load secrets
def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT Broker Configuration
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = secrets["mqtt_port"]
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]
MQTT_TOPICS = {
    "ltc_balance": "exodus/balance_ltc",
    "doge_balance": "exodus/balance_doge",
    "btc_balance": "exodus/balance_btc",
    "total_usd": "exodus/balance_total_usd",
    "total_cad": "exodus/balance_total_cad",
    "total_eur": "exodus/balance_total_eur"
}

# API Endpoints
LTC_API_URL = "https://api.blockcypher.com/v1/ltc/main/addrs/{}/balance"
DOGE_API_URL = "https://api.blockcypher.com/v1/doge/main/addrs/{}/balance"
BTC_API_URL = "https://api.blockcypher.com/v1/btc/main/addrs/{}/balance"

# Function to get balance for a specific cryptocurrency
def get_balance(api_url, address):
    url = api_url.format(address)
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        balance_satoshis = data.get('balance', 0)
        return balance_satoshis / 1e8  # Convert satoshis to coins
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error occurred while fetching balance for {address}: {http_err}")
    except Exception as err:
        logging.error(f"An error occurred while fetching balance for {address}: {err}")
    return None

# Function to fetch prices for LTC, DOGE, and BTC in USD using CoinMarketCap
def get_crypto_prices():
    api_key = secrets["coinmarketcap_api_key"]
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key,
    }
    params = {"symbol": "LTC,DOGE,BTC", "convert": "USD"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        ltc_price_usd = data["data"]["LTC"]["quote"]["USD"]["price"]
        doge_price_usd = data["data"]["DOGE"]["quote"]["USD"]["price"]
        btc_price_usd = data["data"]["BTC"]["quote"]["USD"]["price"]
        return ltc_price_usd, doge_price_usd, btc_price_usd
    except Exception as e:
        logging.error(f"An error occurred while fetching crypto prices from CoinMarketCap: {e}")
        return None, None, None

# Function to fetch conversion rates for USD to CAD and EUR
def get_conversion_rates():
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
        response.raise_for_status()
        data = response.json()
        usd_to_cad = data["rates"]["CAD"]
        usd_to_eur = data["rates"]["EUR"]
        return usd_to_cad, usd_to_eur
    except Exception as e:
        logging.error(f"An error occurred while fetching conversion rates: {e}")
        return None, None

# Function to publish balance to MQTT
def publish_to_mqtt(topic, message):
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(topic, message)
        logging.info(f"Published {message} to MQTT topic {topic}")
        client.disconnect()
    except Exception as err:
        logging.error(f"An error occurred while publishing to MQTT: {err}")

if __name__ == "__main__":
    # Get wallet addresses from secrets
    ltc_address = secrets["exodus_ltc_address"]
    doge_address = secrets["exodus_doge_address"]
    btc_address = secrets["exodus_btc_address"]

    # Fetch balances
    ltc_balance = get_balance(LTC_API_URL, ltc_address)
    doge_balance = get_balance(DOGE_API_URL, doge_address)
    btc_balance = get_balance(BTC_API_URL, btc_address)

    # Fetch prices and conversion rates
    ltc_price_usd, doge_price_usd, btc_price_usd = get_crypto_prices()
    usd_to_cad, usd_to_eur = get_conversion_rates()

    # Calculate total balances
    total_usd = total_cad = total_eur = 0
    if ltc_balance is not None and ltc_price_usd is not None:
        total_usd += ltc_balance * ltc_price_usd
    if doge_balance is not None and doge_price_usd is not None:
        total_usd += doge_balance * doge_price_usd
    if btc_balance is not None and btc_price_usd is not None:
        total_usd += btc_balance * btc_price_usd
    if usd_to_cad is not None:
        total_cad = total_usd * usd_to_cad
    if usd_to_eur is not None:
        total_eur = total_usd * usd_to_eur

    # Publish balances to MQTT
    if ltc_balance is not None:
        publish_to_mqtt(MQTT_TOPICS["ltc_balance"], f"{ltc_balance:.8f}")
    if doge_balance is not None:
        publish_to_mqtt(MQTT_TOPICS["doge_balance"], f"{doge_balance:.8f}")
    if btc_balance is not None:
        publish_to_mqtt(MQTT_TOPICS["btc_balance"], f"{btc_balance:.8f}")
    if total_usd is not None:
        publish_to_mqtt(MQTT_TOPICS["total_usd"], f"{total_usd:.2f}")
    if total_cad is not None:
        publish_to_mqtt(MQTT_TOPICS["total_cad"], f"{total_cad:.2f}")
    if total_eur is not None:
        publish_to_mqtt(MQTT_TOPICS["total_eur"], f"{total_eur:.2f}")

    logging.info("Exodus balance script finished.")

