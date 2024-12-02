#!/home/tav/.pyenv/shims/python3
import boto3
import requests
import os
import logging
import yaml

def load_secrets():
    with open("/config/python_scripts/secrets.yaml", "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Domain-ZONEID mapping
domains = {
    "auroranrunner.com": secrets["auroranrunner_zone_id"],
    "ampiainen.net": secrets["ampiainen_zone_id"],
    "vaattanen.com": secrets["vaattanen_zone_id"],
    "nordicbakeshop.com": secrets["nordicbakeshop_zone_id"],
    "cosmosbaby.net": secrets["cosmosbaby_net_zone_id"],
    "cosmosbaby.network": secrets["cosmosbaby_network_zone_id"]
}

# Logging configuration
LOG_MSG_FORMAT = ('%(asctime)s,%(msecs)03d %(levelname)s [%(filename)s:%(lineno)d] - %(message)s')
LOG_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'
log_dir = "/config/ipv64"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "ipv_ha.log")

logger = logging.getLogger("ipv4_update")
logger.setLevel(logging.INFO)

# File handler for logging to file
logHandler = logging.FileHandler(log_file)
logHandler.setFormatter(logging.Formatter(LOG_MSG_FORMAT, LOG_DATE_FORMAT))
logger.addHandler(logHandler)

# Stream handler for logging to stdout
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(logging.Formatter(LOG_MSG_FORMAT, LOG_DATE_FORMAT))
logger.addHandler(streamHandler)

# AWS Route 53 client
route53_client = boto3.client("route53")

def get_external_ipv4():
    """Fetches the external IPv4 address from an online service."""
    try:
        response = requests.get("https://api64.ipify.org")
        response.raise_for_status()
        external_ip = response.text.strip()
        logger.info(f"Current external IP: {external_ip}")
        return external_ip
    except requests.RequestException as e:
        logger.error(f"Error retrieving external IPv4 address: {e}")
        return None

def update_dns_record(zone_id, record_name, new_ip):
    """Updates the DNS for the given record name with the new IP on AWS Route 53."""
    try:
        response = route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Comment": f"Auto-update IP for {record_name}",
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": record_name,
                            "Type": "A",
                            "TTL": 300,
                            "ResourceRecords": [{"Value": new_ip}]
                        }
                    }
                ]
            }
        )
        logger.info(f"Updated A record for {record_name} with IP: {new_ip}")
    except Exception as e:
        logger.error(f"Error updating A record for {record_name}: {e}")

def main():
    ipv4_address = get_external_ipv4()
    if not ipv4_address:
        logger.error("Could not determine external IP. Exiting.")
        return

    # Update the A record for each domain
    for domain, zone_id in domains.items():
        logger.info(f"Updating DNS for {domain}")
        update_dns_record(zone_id, domain, ipv4_address)

if __name__ == "__main__":
    main()

