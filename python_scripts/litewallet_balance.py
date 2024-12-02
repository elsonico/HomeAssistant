#!/home/tav/.pyenv/shims/python3
import requests
import logging
import paho.mqtt.client as mqtt
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# MQTT Broker Configuration
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = secrets["mqtt_port"]
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]
MQTT_TOPICS = {
    "ltc_balance": "litewallet/balance_ltc",
    "total_usd": "litewallet/balance_total_usd",
    "total_cad": "litewallet/balance_total_cad",
    "total_eur": "litewallet/balance_total_eur"
}
LTC_WALLET_ADDRESS = secrets["litecoin_ltc_address"]

# API Endpoints
LTC_API_URL = "https://api.blockcypher.com/v1/ltc/main/addrs/{}/balance"

# Function to get LTC balance
def get_balance(api_url, address):
    url = api_url.format(address)
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        balance_satoshis = data.get('balance', 0)
        return balance_satoshis / 1e8  # Convert satoshis to LTC
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error occurred while fetching balance for {address}: {http_err}")
    except Exception as err:
        logging.error(f"An error occurred while fetching balance for {address}: {err}")
    return None

# Function to fetch LTC price in USD using CoinMarketCap
def get_crypto_price():
    api_key = secrets["coinmarketcap_api_key"]  # Replace with your API key
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key,
    }
    params = {"symbol": "LTC", "convert": "USD"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data["data"]["LTC"]["quote"]["USD"]["price"]
    except Exception as e:
        logging.error(f"An error occurred while fetching LTC price: {e}")
        return None

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
    # Replace with your Litewallet LTC address
    ltc_address = LTC_WALLET_ADDRESS

    # Fetch LTC balance
    ltc_balance = get_balance(LTC_API_URL, ltc_address)

    # Fetch LTC price and conversion rates
    ltc_price_usd = get_crypto_price()
    usd_to_cad, usd_to_eur = get_conversion_rates()

    # Calculate balances in different currencies
    total_usd = total_cad = total_eur = 0
    if ltc_balance is not None and ltc_price_usd is not None:
        total_usd = ltc_balance * ltc_price_usd
    if usd_to_cad is not None:
        total_cad = total_usd * usd_to_cad
    if usd_to_eur is not None:
        total_eur = total_usd * usd_to_eur

    # Publish balances to MQTT
    if ltc_balance is not None:
        publish_to_mqtt(MQTT_TOPICS["ltc_balance"], f"{ltc_balance:.8f}")
    if total_usd > 0:
        publish_to_mqtt(MQTT_TOPICS["total_usd"], f"{total_usd:.2f}")
    if total_cad > 0:
        publish_to_mqtt(MQTT_TOPICS["total_cad"], f"{total_cad:.2f}")
    if total_eur > 0:
        publish_to_mqtt(MQTT_TOPICS["total_eur"], f"{total_eur:.2f}")

    logging.info("Litewallet balance script finished.")

