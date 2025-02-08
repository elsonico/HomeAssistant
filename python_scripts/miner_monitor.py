import os
import requests
from datetime import datetime
import re

def get_miner_temperatures():
    # Get credentials from environment variables
    username = os.getenv('MINERUSER')
    password = os.getenv('MINERPWD')
    
    if not username or not password:
        raise ValueError("Missing MINERUSER or MINERPWD environment variables")

    # URL for the log endpoint
    url = "https://miner.auroranrunner.com/#/Log"
    
    try:
        # Make request with basic authentication
        response = requests.get(url, auth=(username, password))
        response.raise_for_status()  # Raise exception for bad status codes
        
        # Get the log content
        log_content = response.text
        
        # Regular expression to find temperature readings
        temp_pattern = r"health: min = (\d+\.\d+) Degree centigrade, max = (\d+\.\d+) Degree centigrade"
        
        # Find the latest temperature reading
        matches = re.findall(temp_pattern, log_content)
        if matches:
            # Get the last (most recent) match
            min_temp, max_temp = matches[-1]
            return {
                'min_temperature': float(min_temp),
                'max_temperature': float(max_temp),
                'timestamp': datetime.now().isoformat()
            }
        else:
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching log: {e}")
        return None

if __name__ == "__main__":
    temps = get_miner_temperatures()
    if temps:
        print(f"Min Temperature: {temps['min_temperature']}°C")
        print(f"Max Temperature: {temps['max_temperature']}°C")
        print(f"Timestamp: {temps['timestamp']}")
    else:
        print("Failed to get temperature readings")
