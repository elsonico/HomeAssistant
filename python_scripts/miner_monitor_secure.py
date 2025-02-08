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


def verify_auth(session, base_url, headers):
    """Verify authentication credentials"""
    try:
        # Try to access a known endpoint that requires authentication
        test_url = f"{base_url}/cgi-bin/summary.cgi"
        response = session.get(test_url, headers=headers, verify=False)

        # Check if we got a 401 Unauthorized response
        if response.status_code == 401:
            logger.error("Authentication failed: Invalid credentials")
            return False

        # Check if we got a valid JSON response
        try:
            data = response.json()
            if 'STATUS' in data and data['STATUS'].get('STATUS') == 'S':
                logger.info("Authentication successful")
                return True
        except json.JSONDecodeError:
            pass

        logger.error("Authentication failed: Invalid response")
        return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Authentication check failed: {str(e)}")
        return False

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

    # Verify authentication before proceeding
    if not verify_auth(session, base_url, headers):
        return None

    try:
        # Get stats for temperature and fan data
        stats_url = f"{base_url}/cgi-bin/stats.cgi"
        stats_response = session.get(stats_url, headers=headers, verify=False)
        stats_response.raise_for_status()
        stats_data = stats_response.json()

        # Get system info for power data
        sysinfo_url = f"{base_url}/cgi-bin/get_system_info.cgi"
        sysinfo_response = session.get(sysinfo_url, headers=headers, verify=False)
        sysinfo_response.raise_for_status()
        sysinfo_data = sysinfo_response.json()

        if 'STATS' in stats_data and stats_data['STATS']:
            stats = stats_data['STATS'][0]

            # Get all temperatures from all chains
            all_temps = []
            for chain in stats.get('chain', []):
                # Only include numeric temperature values
                all_temps.extend([t for t in chain.get('temp_pcb', []) if isinstance(t, (int, float))])
                all_temps.extend([t for t in chain.get('temp_pic', []) if isinstance(t, (int, float))])

            if all_temps:
                # Get timestamp from STATUS
                timestamp = stats_data.get('STATUS', {}).get('timestamp',
                                                           int(datetime.now().timestamp()))

                # Get fan speeds and ensure they're numeric
                fan_speeds = [int(speed) if str(speed).isdigit() else 0
                            for speed in stats.get('fan', [])]

                return {
                    'min_temperature': min(all_temps),
                    'max_temperature': max(all_temps),
                    'avg_temperature': sum(all_temps) / len(all_temps),
                    'all_temperatures': all_temps,
                    'timestamp': timestamp,
                    'fan_speeds': fan_speeds,
                    'hashrate': stats.get('rate_avg', 0),
                    'hashrate_unit': stats.get('rate_unit', 'MH/s'),
                    'system_info': {
                        'type': sysinfo_data.get('minertype', ''),
                        'firmware': sysinfo_data.get('system_filesystem_version', ''),
                        'algorithm': sysinfo_data.get('Algorithm', '')
                    }
                }

    except requests.exceptions.RequestException as e:
        logger.error(f"Error accessing miner API: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")

    return None

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
        logger.info("System Information:")
        logger.info(f"  Miner Type: {temps['system_info']['type']}")
        logger.info(f"  Firmware: {temps['system_info']['firmware']}")
        logger.info(f"  Algorithm: {temps['system_info']['algorithm']}")
        logger.info("\nTemperature Readings:")
        logger.info(f"  Min Temperature: {temps['min_temperature']}°C")
        logger.info(f"  Max Temperature: {temps['max_temperature']}°C")
        logger.info(f"  Average Temperature: {temps['avg_temperature']:.1f}°C")
        logger.info(f"\nFan Speeds: {temps['fan_speeds']} RPM")
        logger.info(f"Hashrate: {temps['hashrate']} {temps['hashrate_unit']}")
        logger.info(f"Timestamp: {datetime.fromtimestamp(temps['timestamp'])}")
    else:
        logger.error("Failed to get temperature readings")
