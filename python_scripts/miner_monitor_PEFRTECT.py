#!/usr/bin/env python

import os
import requests
from datetime import datetime
import logging
import urllib3
import json
import traceback
from typing import Optional, Dict, Any, List, Union

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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

def format_temp(temp: float) -> str:
    """Format temperature with one decimal place"""
    return f"{temp:.1f}°C"

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
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
