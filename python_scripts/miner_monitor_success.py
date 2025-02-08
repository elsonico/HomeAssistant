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

def analyze_js_file(session, base_url, js_path, headers):
    """Analyze a JS file for API endpoints and temperature-related code"""
    url = f"{base_url}/{js_path}"
    try:
        logger.info(f"Analyzing {js_path}")
        response = session.get(url, headers=headers, verify=False)
        response.raise_for_status()
        
        js_content = response.text
        
        # Look for API endpoints
        api_patterns = [
            r'"/([^"]*\.cgi)"',  # Matches quoted CGI paths
            r"'/([^']*\.cgi)'",  # Matches single-quoted CGI paths
            r'`/([^`]*\.cgi)`',  # Matches template literal CGI paths
            r'url:\s*["\']([^"\']*\.cgi)["\']',  # Matches URL configurations
            r'fetch\(["\']([^"\']*\.cgi)["\']\)',  # Matches fetch calls
            r'axios\.get\(["\']([^"\']*\.cgi)["\']\)',  # Matches axios.get calls
        ]
        
        all_endpoints = set()
        for pattern in api_patterns:
            matches = re.findall(pattern, js_content)
            all_endpoints.update(matches)
        
        if all_endpoints:
            logger.info(f"Found API endpoints in {js_path}:")
            for endpoint in all_endpoints:
                logger.info(f"  - {endpoint}")
        
        # Look for temperature-related code blocks
        temp_patterns = [
            r'function\s+\w*[tT]emp\w*\s*\([^)]*\)\s*{[^}]*}',  # Temperature-related functions
            r'["\']temperature["\']:\s*[^,}]+',  # Temperature JSON keys
            r'["\']temp["\']:\s*[^,}]+',  # Temp JSON keys
            r'/\*.*temperature.*\*/',  # Temperature-related comments
            r'//.*temperature.*$',  # Temperature-related line comments
        ]
        
        for pattern in temp_patterns:
            matches = re.findall(pattern, js_content, re.MULTILINE | re.IGNORECASE)
            if matches:
                logger.info(f"Found temperature-related code in {js_path}:")
                for match in matches:
                    logger.info(f"  {match.strip()}")
        
        return all_endpoints
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to analyze {js_path}: {str(e)}")
        return set()

def get_miner_temperatures():
    username = os.getenv('MINERUSER')
    password = os.getenv('MINERPWD')
    
    if not username or not password:
        logger.error("Missing environment variables: MINERUSER or MINERPWD")
        raise ValueError("Missing MINERUSER or MINERPWD environment variables")

    base_url = "http://192.168.0.161"
    
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': f'{base_url}/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }
    
    session = requests.Session()
    session.auth = (username, password)
    
    # JS files to analyze
    js_files = [
        'assets/index-D6rZwDhh.js',
        'assets/Default-D-TiU5GN.js',
        'assets/Dashboard-hPAYFOsg.js',
        'assets/axios-CgRmDqS1.js',
        'assets/VList-BeX2jaId.js'
    ]
    
    # Collect all unique endpoints from JS files
    all_endpoints = set()
    for js_file in js_files:
        endpoints = analyze_js_file(session, base_url, js_file, headers)
        all_endpoints.update(endpoints)
    
    logger.info("Found these unique endpoints:")
    for endpoint in sorted(all_endpoints):
        logger.info(f"  {endpoint}")
        
        # Try to access each discovered endpoint
        url = f"{base_url}/{endpoint.lstrip('/')}"
        try:
            logger.info(f"Trying endpoint: {url}")
            response = session.get(url, headers=headers, verify=False)
            response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Got JSON response from {url}")
                logger.info(f"Response: {json.dumps(data, indent=2)}")
                
                # Save successful response
                with open(f'response_{endpoint.replace("/", "_")}.json', 'w') as f:
                    json.dump(data, f, indent=2)
                    
            except json.JSONDecodeError:
                logger.warning(f"Response from {url} is not JSON")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to access {url}: {str(e)}")

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
