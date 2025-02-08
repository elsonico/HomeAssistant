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

    # URL for the log endpoint - using the API endpoint instead of the web page
    base_url = "https://miner.auroranrunner.com"
    log_url = f"{base_url}/api/log"  # This is a guess at the API endpoint
    
    logger.info(f"Attempting to fetch data from: {log_url}")
    
    try:
        # Make request with basic authentication
        response = requests.get(log_url, auth=(username, password))
        response.raise_for_status()
        
        # Get the log content
        log_content = response.text
        
        # Dump response details and content to file
        with open('miner_response.log', 'w') as f:
            f.write(f"Response Status Code: {response.status_code}\n")
            f.write(f"Response Headers:\n{dict(response.headers)}\n")
            f.write("\nResponse Content:\n")
            f.write(log_content)
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response content type: {response.headers.get('content-type', 'unknown')}")
        logger.info(f"Response length: {len(log_content)} characters")
        logger.info(f"First 200 characters of response: {log_content[:200]}")
        
        # Regular expression to find temperature readings
        temp_pattern = r"health: min = (\d+\.\d+) Degree centigrade, max = (\d+\.\d+) Degree centigrade"
        
        matches = re.findall(temp_pattern, log_content)
        if matches:
            min_temp, max_temp = matches[-1]
            logger.info(f"Found temperature readings - Min: {min_temp}°C, Max: {max_temp}°C")
            return {
                'min_temperature': float(min_temp),
                'max_temperature': float(max_temp),
                'timestamp': datetime.now().isoformat()
            }
        else:
            logger.warning("No temperature readings found in the log content")
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
