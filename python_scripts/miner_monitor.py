#!/usr/bin/env python

import os
import requests
from datetime import datetime
import logging
import urllib3
import json
import traceback
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
import paho.mqtt.client as mqtt
import yaml

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# MQTT configuration
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = 1883
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]

def parse_chip_temp(temp_str: str) -> Optional[float]:
    """Convert chip temperature from millidegrees to degrees"""
    try:
        return float(temp_str) / 1000
    except (ValueError, TypeError):
        return None

def verify_auth(session: requests.Session, base_url: str, headers: Dict[str, str]) -> bool:
    """Verify authentication credentials"""
    try:
        test_url = f"{base_url}/cgi-bin/summary.cgi"
        response = session.get(test_url, headers=headers, verify=False)
        
        if response.status_code == 401:
            logger.error("Authentication failed: Invalid credentials")
            return False
            
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

def get_miner_temperatures() -> Optional[Dict[str, Any]]:
    """Get miner temperature and performance data"""
    try:
        username = os.getenv('MINERUSER')
        password = os.getenv('MINERPWD')
        
        if not username or not password:
            logger.error("Missing environment variables: MINERUSER or MINERPWD")
            raise ValueError("Missing MINERUSER or MINERPWD environment variables")

        base_url = secrets["miner_url"]
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f'{base_url}/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
        
        session = requests.Session()
        session.auth = (username, password)
        
        if not verify_auth(session, base_url, headers):
            return None

        # Get stats for ASIC temperatures and fan data
        stats_url = f"{base_url}/cgi-bin/stats.cgi"
        logger.debug(f"Requesting stats from: {stats_url}")
        stats_response = session.get(stats_url, headers=headers, verify=False)
        stats_response.raise_for_status()
        stats_data = stats_response.json()
        
        if not stats_data.get('STATS'):
            logger.error("No STATS data found in response")
            return None
            
        stats = stats_data['STATS'][0]
        
        # Find the chain with valid SN
        active_chain = None
        for chain in stats.get('chain', []):
            if chain.get('sn'):  # Found chain with valid SN
                active_chain = chain
                break
        
        if not active_chain:
            logger.error("No active chain found with valid SN")
            return None
            
        logger.info(f"Found active chain with SN: {active_chain['sn']}")
        
        # Parse chip temperatures (they're in millidegrees)
        chip_temps: List[float] = []
        for temp in active_chain.get('temp_chip', []):
            if temp and temp.strip():
                temp_value = parse_chip_temp(temp)
                if temp_value is not None:
                    chip_temps.append(temp_value)
        
        # Get PCB and PIC temperatures
        pcb_temps = [t for t in active_chain.get('temp_pcb', []) if isinstance(t, (int, float))]
        pic_temps = [t for t in active_chain.get('temp_pic', []) if isinstance(t, (int, float))]
        
        # Combine all valid temperatures
        all_temps = chip_temps + pcb_temps + pic_temps
        
        if not all_temps:
            logger.error("No valid temperatures found")
            return None

        # Get hashrate and ideal hashrate
        hashrate = active_chain.get('rate_real', 0)
        hashrate_ideal = active_chain.get('rate_ideal', 0)
        
        # Create temperature data structure
        temp_data = {
            'sn': active_chain['sn'],
            'chip_temps': chip_temps,
            'pcb_temps': pcb_temps,
            'pic_temps': pic_temps,
            'min_temperature': min(all_temps),
            'max_temperature': max(all_temps),
            'avg_temperature': sum(all_temps) / len(all_temps),
            'hashrate': hashrate,
            'hashrate_ideal': hashrate_ideal,
            'hashrate_unit': stats.get('rate_unit', 'MH/s'),
            'chip_state': active_chain.get('chipState', 'unknown'),
            'fan_speeds': [int(speed) if str(speed).isdigit() else 0 
                         for speed in stats.get('fan', [])],
            'timestamp': stats_data.get('STATUS', {}).get('timestamp', 
                                                        int(datetime.now().timestamp()))
        }
        
        return temp_data
            
    except Exception as e:
        logger.error(f"Error getting temperature data: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    return None

def publish_to_mqtt(topic: str, value: Any) -> None:
    """Publish data to MQTT broker"""
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(topic, value)
        client.disconnect()
        logger.debug(f"Published {value} to MQTT topic: {topic}")
    except Exception as e:
        logger.error(f"Error publishing to MQTT: {str(e)}")

def write_ha_sensors(temp_data: Dict[str, Any]) -> None:
    """Write sensor data for Home Assistant and publish to MQTT"""
    try:
        ha_state_path = Path("/config/ha_states")
        ha_state_path.mkdir(parents=True, exist_ok=True)
        
        # Calculate efficiency
        efficiency = (temp_data['hashrate'] / temp_data['hashrate_ideal'] * 100) if temp_data['hashrate_ideal'] > 0 else 0
        
        # Write hashrate and efficiency
        hashrate_data = {
            "state": temp_data['hashrate'],
            "attributes": {
                "unit_of_measurement": temp_data['hashrate_unit'],
                "friendly_name": "Miner Hashrate",
                "ideal_hashrate": temp_data['hashrate_ideal'],
                "efficiency": f"{efficiency:.1f}%",
                "serial_number": temp_data['sn']
            }
        }
        with open(ha_state_path / "sensor.miner_hashrate", 'w') as f:
            json.dump(hashrate_data, f)
        publish_to_mqtt("miner/hashrate", temp_data['hashrate'])
        publish_to_mqtt("miner/hashrate_efficiency", efficiency)
        
        # Write chip temperatures
        temp_names = ['outlet_temp1', 'outlet_temp2', 'inlet_temp1', 'inlet_temp2']
        for i, temp in enumerate(temp_data['chip_temps'][:4]):  # Limit to first 4 temperatures
            temp_data_sensor = {
                "state": temp,
                "attributes": {
                    "unit_of_measurement": "°C",
                    "friendly_name": f"Miner {temp_names[i].replace('_', ' ').title()}",
                    "serial_number": temp_data['sn']
                }
            }
            with open(ha_state_path / f"sensor.miner_{temp_names[i]}", 'w') as f:
                json.dump(temp_data_sensor, f)
            publish_to_mqtt(f"miner/{temp_names[i]}", temp)
        
        # Write fan speeds
        fan_data = {
            "state": temp_data['fan_speeds'][0] if temp_data['fan_speeds'] else 0,
            "attributes": {
                "unit_of_measurement": "RPM",
                "friendly_name": "Miner Fan Speeds",
                "all_fans": temp_data['fan_speeds'],
                "serial_number": temp_data['sn']
            }
        }
        with open(ha_state_path / "sensor.miner_fan_speed", 'w') as f:
            json.dump(fan_data, f)
        publish_to_mqtt("miner/fan_speed", temp_data['fan_speeds'][0] if temp_data['fan_speeds'] else 0)
            
        logger.info("Successfully wrote sensor data for Home Assistant and MQTT")
        
    except Exception as e:
        logger.error(f"Error writing sensor data: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")

def format_temp(temp: float) -> str:
    """Format temperature with one decimal place"""
    return f"{temp:.1f}°C"

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
        # Write data for Home Assistant and publish to MQTT
        write_ha_sensors(temps)
        
        # Log detailed information
        logger.info("\nMiner Information:")
        logger.info(f"Serial Number: {temps['sn']}")
        logger.info("\nTemperature Readings:")
        logger.info(f"  Chip Temperatures: {[format_temp(t) for t in temps['chip_temps']]}")
        logger.info(f"  PCB Temperatures: {temps['pcb_temps']}°C")
        logger.info(f"  PIC Temperatures: {temps['pic_temps']}°C")
        logger.info(f"  Min Temperature: {format_temp(temps['min_temperature'])}")
        logger.info(f"  Max Temperature: {format_temp(temps['max_temperature'])}")
        logger.info(f"  Average Temperature: {format_temp(temps['avg_temperature'])}")
        logger.info(f"\nPerformance:")
        logger.info(f"  Current Hashrate: {temps['hashrate']} {temps['hashrate_unit']}")
        logger.info(f"  Ideal Hashrate: {temps['hashrate_ideal']} {temps['hashrate_unit']}")
        if temps['hashrate_ideal'] > 0:
            efficiency = (temps['hashrate'] / temps['hashrate_ideal'] * 100)
            logger.info(f"  Efficiency: {efficiency:.1f}%")
        logger.info(f"\nSystem Status:")
        logger.info(f"  Chip State: {temps['chip_state']}")
        logger.info(f"  Fan Speeds: {temps['fan_speeds']} RPM")
        logger.info(f"  Timestamp: {datetime.fromtimestamp(temps['timestamp'])}")
    else:
        logger.error("Failed to get temperature readings")
