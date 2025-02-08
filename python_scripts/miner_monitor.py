#!/usr/bin/env python

import os
import requests
from datetime import datetime
import re
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_miner_temperatures():
    # Get credentials from environment variables
    username = os.getenv('MINERUSER')
    password = os.getenv('MINERPWD')
    
    if not username or not password:
        logger.error("Missing environment variables: MINERUSER or MINERPWD")
        raise ValueError("Missing MINERUSER or MINERPWD environment variables")

    # URL for the log endpoint
    url = "https://miner.auroranrunner.com/#/Log"
    logger.info(f"Attempting to fetch data from: {url}")
    
    try:
        # Make request with basic authentication
        logger.debug(f"Making request with user: {username}")
        response = requests.get(url, auth=(username, password))
        response.raise_for_status()  # Raise exception for bad status codes
        
        # Get the log content
        log_content = response.text
        logger.debug(f"Received response length: {len(log_content)} characters")
        
        # Regular expression to find temperature readings
        temp_pattern = r"health: min = (\d+\.\d+) Degree centigrade, max = (\d+\.\d+) Degree centigrade"
        
        # Find the latest temperature reading
        matches = re.findall(temp_pattern, log_content)
        if matches:
            # Get the last (most recent) match
            min_temp, max_temp = matches[-1]
            logger.info(f"Found temperature readings - Min: {min_temp}°C, Max: {max_temp}°C")
            return {
                'min_temperature': float(min_temp),
                'max_temperature': float(max_temp),
                'timestamp': datetime.now().isoformat()
            }
        else:
            logger.warning("No temperature readings found in the log content")
            logger.debug(f"Log content: {log_content[:500]}...")  # First 500 chars for debugging
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    logger.info("Starting miner temperature monitoring")
    temps = get_miner_temperatures()
    if temps:
        logger.info(f"Min Temperature: {temps['min_temperature']}°C")
        logger.info(f"Max Temperature: {temps['max_temperature']}°C")
        logger.info(f"Timestamp: {temps['timestamp']}")
    else:
        logger.error("Failed to get temperature readings")
