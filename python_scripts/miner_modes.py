#!/usr/bin/env python
import subprocess
import sys
import os

def run_curl_command(curl_cmd):
    """Execute a curl command and return the output."""
    try:
        result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing curl command: {e}")
        sys.exit(1)

def main():
    # Check if NODE_ENDPOINT environment variable is set
    node_endpoint = os.getenv('NODE_ENDPOINT')
    if not node_endpoint:
        print("Error: NODE_ENDPOINT environment variable is not set")
        sys.exit(1)

    # Define curl commands for each mode
    curl_commands = {
        'normalmode': f'/usr/bin/curl -s -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" -d "{{\\"workmode\\":\\"0\\"}}" {node_endpoint}/cgi-bin/luci/setworkmode.cgi',
        'overclockmode': f'/usr/bin/curl -s -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" -d "{{\\"workmode\\":\\"101\\"}}" {node_endpoint}/cgi-bin/luci/setworkmode.cgi',
        'powersavemode': f'/usr/bin/curl -s -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" -d "{{\\"workmode\\":\\"-100\\"}}" {node_endpoint}/cgi-bin/luci/setworkmode.cgi',
        'getmode': f'/usr/bin/curl -s {node_endpoint}/cgi-bin/luci/getworkmode.cgi'
    }

    # Parse command-line arguments
    args = sys.argv[1:]

    # Check for valid number of arguments (exactly one flag)
    if len(args) != 1:
        print("Error: Exactly one mode flag must be provided (--normalmode, --overclockmode, --powersavemode, or --getmode)")
        sys.exit(1)

    # Map argument to command
    arg = args[0]
    if arg == '--getmode':
        print(run_curl_command(curl_commands['getmode']))
    elif arg == '--normalmode':
        print(run_curl_command(curl_commands['normalmode']))
    elif arg == '--overclockmode':
        print(run_curl_command(curl_commands['overclockmode']))
    elif arg == '--powersavemode':
        print(run_curl_command(curl_commands['powersavemode']))
    else:
        print(f"Error: Invalid argument {arg}. Use --normalmode, --overclockmode, --powersavemode, or --getmode")
        sys.exit(1)

if __name__ == "__main__":
    main()
