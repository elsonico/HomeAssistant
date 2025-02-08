#!/usr/bin/env python

import os
import requests
from datetime import datetime
import re
import logging
import urllib3
import json

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_miner_temperatures():
    username = os.getenv('MINERUSER')
    password = os.getenv('MINERPWD')

    if not username or not password:
        logger.error("Missing environment variables: MINERUSER or MINERPWD")
        raise ValueError("Missing MINERUSER or MINERPWD environment variables")

    base_url = "http://192.168.0.161"

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': f'{base_url}/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }

    session = requests.Session()
    session.auth = (username, password)

    # Get stats for temperature data
    url = f"{base_url}/cgi-bin/stats.cgi"
    try:
        response = session.get(url, headers=headers, verify=False)
        response.raise_for_status()
        data = response.json()

        if 'STATS' in data and data['STATS']:
            stats = data['STATS'][0]

            # Get all temperatures from all chains
            all_temps = []
            for chain in stats.get('chain', []):
                all_temps.extend([t for t in chain.get('temp_pcb', []) if isinstance(t, (int, float))])
                all_temps.extend([t for t in chain.get('temp_pic', []) if isinstance(t, (int, float))])

            if all_temps:
                # Get timestamp from STATUS
                timestamp = data.get('STATUS', {}).get('timestamp',
                                                     int(datetime.now().timestamp()))

                return {
                    'min_temperature': min(all_temps),
                    'max_temperature': max(all_temps),
                    'avg_temperature': sum(all_temps) / len(all_temps),
                    'all_temperatures': all_temps,
                    'timestamp': timestamp,
                    'fan_speeds': stats.get('fan', []),
                    'hashrate': stats.get('rate_avg', 0),
                    'hashrate_unit': stats.get('rate_unit', 'MH/s')
                }

    except Exception as e:
        logger.error(f"Error getting temperature data: {str(e)}")

    return None

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
        logger.info(f"Min Temperature: {temps['min_temperature']}°C")
        logger.info(f"Max Temperature: {temps['max_temperature']}°C")
        logger.info(f"Average Temperature: {temps['avg_temperature']:.1f}°C")
        logger.info(f"All Temperatures: {temps['all_temperatures']}°C")
        logger.info(f"Fan Speeds: {temps['fan_speeds']} RPM")
        logger.info(f"Hashrate: {temps['hashrate']} {temps['hashrate_unit']}")
        logger.info(f"Timestamp: {datetime.fromtimestamp(temps['timestamp'])}")
    else:
        logger.error("Failed to get temperature readings")
