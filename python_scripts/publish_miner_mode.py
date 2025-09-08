#!/usr/bin/env python

import subprocess
import json
import yaml
import paho.mqtt.client as mqtt
import sys
import os

def load_secrets():
    secrets_path = "/config/python_scripts/secrets.yaml"
    with open(secrets_path, "r") as file:
        return yaml.safe_load(file)

def get_miner_mode():
    """Get current miner mode using the miner_modes.py script"""
    try:
        # Run the miner_modes.py script
        result = subprocess.run(["/config/python_scripts/miner_modes.py", "--getmode"], 
                              capture_output=True, text=True, check=True)
        
        # Parse the JSON output
        mode_data = json.loads(result.stdout.strip())
        return mode_data["mode"]
    except subprocess.CalledProcessError as e:
        print(f"Error running miner_modes.py: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def mode_to_text(mode_code):
    """Convert mode code to human-readable text"""
    mode_map = {
        0: "Normal",
        101: "Overclock", 
        -100: "Power Save"
    }
    return mode_map.get(mode_code, f"Unknown ({mode_code})")

def publish_to_mqtt(mode_code):
    """Publish miner mode to MQTT broker"""
    try:
        secrets = load_secrets()
        
        # MQTT settings
        MQTT_BROKER = secrets["mqtt_broker"]
        MQTT_PORT = 1883
        MQTT_USERNAME = secrets["mqtt_username"]
        MQTT_PASSWORD = secrets["mqtt_password"]
        
        # Create MQTT client
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
        # Connect to broker
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # Publish mode code and text
        client.publish("miner/workmode", mode_code)
        client.publish("miner/workmode_text", mode_to_text(mode_code))
        
        # Disconnect
        client.disconnect()
        
        print(f"Published mode {mode_code} ({mode_to_text(mode_code)}) to MQTT")
        return True
        
    except Exception as e:
        print(f"Error publishing to MQTT: {e}")
        return False

def main():
    # Get current miner mode
    mode = get_miner_mode()
    
    if mode is not None:
        # Publish to MQTT
        if publish_to_mqtt(mode):
            print(f"Successfully published miner mode: {mode}")
        else:
            print("Failed to publish to MQTT")
            sys.exit(1)
    else:
        print("Failed to get miner mode")
        sys.exit(1)

if __name__ == "__main__":
    main()
