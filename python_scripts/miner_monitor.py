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
import time

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
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

logger = logging.getLogger("miner_monitor")

def load_secrets():
    try:
        with open("/config/python_scripts/secrets.yaml", "r") as file:
            secrets = yaml.safe_load(file)
            if 'miner_ip' not in secrets:
                logging.error("miner_ip not found in secrets.yaml")
                return None
            return secrets
    except Exception as e:
        logging.error("Error loading secrets: %s", e)
        return None

secrets = load_secrets()
if not secrets:
    exit(1)

# MQTT broker details
MQTT_BROKER = secrets["mqtt_broker"]
MQTT_PORT = 1883
MQTT_USERNAME = secrets["mqtt_username"]
MQTT_PASSWORD = secrets["mqtt_password"]
MINER_IP = secrets["miner_ip"]

# MQTT topics for miner data
MQTT_TOPICS = {
    "hashrate": "miner/hashrate",
    "outlet_temp1": "miner/outlet_temp1",
    "outlet_temp2": "miner/outlet_temp2",
    "inlet_temp1": "miner/inlet_temp1",
    "inlet_temp2": "miner/inlet_temp2",
    "fan_speed": "miner/fan_speed"
}

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

def write_ha_sensors(temp_data: Dict[str, Any]) -> None:
    """Write sensor data for Home Assistant"""
    try:
        ha_state_path = Path("/config/ha_states")
        ha_state_path.mkdir(parents=True, exist_ok=True)
        
        # Write hashrate
        hashrate_data = {
            "state": temp_data['hashrate'],
            "attributes": {
                "unit_of_measurement": temp_data['hashrate_unit'],
                "friendly_name": "Miner Hashrate",
                "ideal_hashrate": temp_data['hashrate_ideal'],
                "efficiency": f"{(temp_data['hashrate'] / temp_data['hashrate_ideal'] * 100):.1f}%",
                "serial_number": temp_data.get('sn', 'unknown')
            }
        }
        with open(ha_state_path / "sensor.miner_hashrate", 'w') as f:
            json.dump(hashrate_data, f)
        
        # Write temperatures
        # Parse temperatures, handling both string and float inputs
        chip_temps = []
        for temp in temp_data['chip_temps']:
            if isinstance(temp, str):
                chip_temps.append(float(temp.replace('°C', '')))
            else:
                chip_temps.append(float(temp))
                
        temp_names = ['outlet_temp1', 'outlet_temp2', 'inlet_temp1', 'inlet_temp2']
        
        for i, temp in enumerate(chip_temps):
            sensor_data = {
                "state": temp,
                "attributes": {
                    "unit_of_measurement": "°C",
                    "friendly_name": f"Miner {temp_names[i].replace('_', ' ').title()}",
                    "serial_number": temp_data.get('sn', 'unknown')
                }
            }
            with open(ha_state_path / f"sensor.miner_{temp_names[i]}", 'w') as f:
                json.dump(sensor_data, f)
        
        # Write fan speeds
        fan_data = {
            "state": temp_data['fan_speeds'][0] if temp_data['fan_speeds'] else 0,
            "attributes": {
                "unit_of_measurement": "RPM",
                "friendly_name": "Miner Fan Speeds",
                "all_fans": temp_data['fan_speeds'],
                "serial_number": temp_data.get('sn', 'unknown')
            }
        }
        with open(ha_state_path / "sensor.miner_fan_speed", 'w') as f:
            json.dump(fan_data, f)
            
        logger.info("Successfully wrote sensor data for Home Assistant")
        
    except Exception as e:
        logger.error(f"Error writing Home Assistant sensor data: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")

def format_temp(temp: float) -> str:
    """Format temperature with one decimal place"""
    return f"{temp:.1f}°C"

def get_miner_data():
    try:
        logging.info("Requesting data from miner at %s", MINER_IP)
        response = requests.get(f"http://{MINER_IP}/api/status")
        if response.status_code == 200:
            data = response.json()
            
            # Print raw data to console
            logging.info("Raw miner data:")
            logging.info(json.dumps(data, indent=2))
            
            processed_data = {
                "hashrate": {
                    "state": data["hashrate"],
                    "attributes": {
                        "unit_of_measurement": "MH/s",
                        "friendly_name": "Miner Hashrate",
                        "ideal_hashrate": 2160,
                        "efficiency": f"{(data['hashrate'] / 2160 * 100):.1f}%",
                        "serial_number": data.get("serial_number", "unknown")
                    }
                },
                "outlet_temp1": {
                    "state": data["temps"]["outlet1"],
                    "attributes": {
                        "unit_of_measurement": "°C",
                        "friendly_name": "Miner Outlet Temperature 1",
                        "serial_number": data.get("serial_number", "unknown")
                    }
                },
                "outlet_temp2": {
                    "state": data["temps"]["outlet2"],
                    "attributes": {
                        "unit_of_measurement": "°C",
                        "friendly_name": "Miner Outlet Temperature 2",
                        "serial_number": data.get("serial_number", "unknown")
                    }
                },
                "inlet_temp1": {
                    "state": data["temps"]["inlet1"],
                    "attributes": {
                        "unit_of_measurement": "°C",
                        "friendly_name": "Miner Inlet Temperature 1",
                        "serial_number": data.get("serial_number", "unknown")
                    }
                },
                "inlet_temp2": {
                    "state": data["temps"]["inlet2"],
                    "attributes": {
                        "unit_of_measurement": "°C",
                        "friendly_name": "Miner Inlet Temperature 2",
                        "serial_number": data.get("serial_number", "unknown")
                    }
                },
                "fan_speed": {
                    "state": data["fan_speed"]["average"],
                    "attributes": {
                        "unit_of_measurement": "RPM",
                        "friendly_name": "Miner Fan Speed",
                        "all_fans": data["fan_speed"]["all_fans"],
                        "serial_number": data.get("serial_number", "unknown")
                    }
                }
            }
            
            # Print processed data to console
            logging.info("\nProcessed sensor data:")
            for sensor, data in processed_data.items():
                logging.info("%s: %s %s", 
                           data["attributes"]["friendly_name"],
                           data["state"],
                           data["attributes"]["unit_of_measurement"])
                if sensor == "hashrate":
                    logging.info("Efficiency: %s", data["attributes"]["efficiency"])
                elif sensor == "fan_speed":
                    logging.info("All fans: %s", data["attributes"]["all_fans"])
            
            return processed_data
        else:
            logging.error("Error getting miner data: %s", response.status_code)
            return None
    except Exception as e:
        logging.error("Exception while getting miner data: %s", e)
        return None

def publish_to_mqtt(topic, message):
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(topic, json.dumps(message))
        logging.info("Published to MQTT topic %s", topic)
        client.disconnect()
    except Exception as e:
        logging.error("An error occurred while publishing to MQTT: %s", e)

if __name__ == "__main__":
    logging.info("Starting miner monitoring script")
    miner_data = get_miner_data()
    
    if miner_data:
        # Publish all sensor data to MQTT
        for sensor, data in miner_data.items():
            publish_to_mqtt(MQTT_TOPICS[sensor], data)
    
    logging.info("Miner monitoring script finished")
