#!/usr/bin/env python

import os
import requests
from datetime import datetime
import re
import logging
import urllib3
import json
import traceback

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for more detailed logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def verify_auth(session, base_url, headers):
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

def get_miner_temperatures():
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
        logger.debug(f"Stats response: {json.dumps(stats_data, indent=2)}")
        
        # Get health info for inlet/outlet temperatures
        health_endpoints = [
            'cgi-bin/get_health.cgi',
            'cgi-bin/health.cgi',
            'cgi-bin/get_system_health.cgi',
            'cgi-bin/monitor.cgi',
            'cgi-bin/status.cgi'  # Added another possible endpoint
        ]
        
        health_data = None
        for endpoint in health_endpoints:
            try:
                health_url = f"{base_url}/{endpoint}"
                logger.debug(f"Trying health endpoint: {health_url}")
                health_response = session.get(health_url, headers=headers, verify=False)
                health_response.raise_for_status()
                health_data = health_response.json()
                logger.info(f"Found health data at {endpoint}")
                logger.debug(f"Health data: {json.dumps(health_data, indent=2)}")
                break
            except requests.exceptions.RequestException as e:
                logger.debug(f"Failed to access {endpoint}: {str(e)}")
                continue
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON from {endpoint}: {str(e)}")
                continue
        
        if not stats_data.get('STATS'):
            logger.error("No STATS data found in response")
            return None
            
        stats = stats_data['STATS'][0]
        logger.debug(f"Processing STATS data: {json.dumps(stats, indent=2)}")
        
        # Get ASIC temperatures from stats
        asic_temps = []
        for chain in stats.get('chain', []):
            pcb_temps = [t for t in chain.get('temp_pcb', []) if isinstance(t, (int, float))]
            pic_temps = [t for t in chain.get('temp_pic', []) if isinstance(t, (int, float))]
            logger.debug(f"Chain PCB temps: {pcb_temps}")
            logger.debug(f"Chain PIC temps: {pic_temps}")
            asic_temps.extend(pcb_temps)
            asic_temps.extend(pic_temps)
        
        # Initialize temperature data structure
        temp_data = {
            'asic_temperatures': asic_temps,
            'inlet_temp1': None,
            'inlet_temp2': None,
            'outlet_temp1': None,
            'outlet_temp2': None,
            'timestamp': stats_data.get('STATUS', {}).get('timestamp', 
                                                        int(datetime.now().timestamp())),
            'fan_speeds': [int(speed) if str(speed).isdigit() else 0 
                         for speed in stats.get('fan', [])],
            'hashrate': stats.get('rate_avg', 0),
            'hashrate_unit': stats.get('rate_unit', 'MH/s')
        }
        
        # Try to extract inlet/outlet temperatures from health data
        if health_data:
            health = health_data.get('HEALTH', health_data)
            logger.debug(f"Processing health data: {json.dumps(health, indent=2)}")
            
            # Update with health temperatures if found
            for key in ['inlet_temp1', 'inlet_temp2', 'outlet_temp1', 'outlet_temp2']:
                if key in health:
                    try:
                        temp_data[key] = float(health[key])
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Could not convert {key} to float: {str(e)}")
        
        # Calculate min/max/avg only from valid temperatures
        valid_temps = [t for t in asic_temps if isinstance(t, (int, float))]
        inlet_outlet_temps = [v for k, v in temp_data.items() 
                            if k.endswith('_temp1') or k.endswith('_temp2')
                            and isinstance(v, (int, float))]
        
        all_temps = valid_temps + inlet_outlet_temps
        
        if all_temps:
            temp_data.update({
                'min_temperature': min(all_temps),
                'max_temperature': max(all_temps),
                'avg_temperature': sum(all_temps) / len(all_temps)
            })
            
            return temp_data
        else:
            logger.error("No valid temperature readings found")
            return None
            
    except Exception as e:
        logger.error(f"Error getting temperature data: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    return None

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
        logger.info("\nTemperature Readings:")
        if temps.get('inlet_temp1') is not None:
            logger.info(f"  Inlet Temperature 1: {temps['inlet_temp1']}°C")
        if temps.get('inlet_temp2') is not None:
            logger.info(f"  Inlet Temperature 2: {temps['inlet_temp2']}°C")
        if temps.get('outlet_temp1') is not None:
            logger.info(f"  Outlet Temperature 1: {temps['outlet_temp1']}°C")
        if temps.get('outlet_temp2') is not None:
            logger.info(f"  Outlet Temperature 2: {temps['outlet_temp2']}°C")
        if temps['asic_temperatures']:
            logger.info(f"  ASIC Temperatures: {temps['asic_temperatures']}°C")
        logger.info(f"  Min Temperature: {temps['min_temperature']}°C")
        logger.info(f"  Max Temperature: {temps['max_temperature']}°C")
        logger.info(f"  Average Temperature: {temps['avg_temperature']:.1f}°C")
        logger.info(f"\nFan Speeds: {temps['fan_speeds']} RPM")
        logger.info(f"Hashrate: {temps['hashrate']} {temps['hashrate_unit']}")
        logger.info(f"Timestamp: {datetime.fromtimestamp(temps['timestamp'])}")
    else:
        logger.error("Failed to get temperature readings")
