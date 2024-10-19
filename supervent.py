import uuid
import random
import time
import numpy as np
import datetime
import aiohttp
import asyncio

# Generate 20,000 unique user IDs within the range 101 to 3,546,353
user_ids = np.linspace(101, 3546353, 20000, dtype=int)

# Apply Zipf's law to generate a base frequency distribution
zipf_distribution = np.random.zipf(1.5, 20000)

# Normalize the Zipf distribution to the range of user IDs
zipf_distribution = (zipf_distribution - zipf_distribution.min()) / (zipf_distribution.max() - zipf_distribution.min())
zipf_distribution = zipf_distribution * (user_ids.max() - user_ids.min()) + user_ids.min()

# Adjust the distribution to reflect the desired characteristics
# Early long-time employees (low user_id values) appear frequently
# New customers (high user_id values) shop more frequently
adjusted_distribution = np.zeros_like(user_ids, dtype=float)
for i, user_id in enumerate(user_ids):
    if user_id < 1000:
        adjusted_distribution[i] = zipf_distribution[i] * 10  # Early employees appear more frequently
    else:
        adjusted_distribution[i] = zipf_distribution[i] * (1 + (user_id / user_ids.max()))  # New customers shop more

# Normalize the adjusted distribution
adjusted_distribution = adjusted_distribution / adjusted_distribution.sum()

# Define Linux architectures and their weights
linux_architectures = [
    "x86_64", "i686", "arm64", "ppc64le", "s390x", "i386", "ia64", "alpha", 
    "mips", "mipsel", "sparc64", "sh4", "sh4eb", "hppa", "hppa64", "rm68k"
]
linux_arch_weights = [
    60, 20, 10, 5, 3, 2, 0.5, 0.3, 0.2, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1
]

# State variables for clustering events
burst_mode = None
burst_count = 0

# Set default batch size
DEFAULT_BATCH_SIZE = 200

# Function to read the Axiom configuration from a file
def read_axiom_config(file_path):
    config = {}
    with open(file_path, 'r') as file:
        for line in file:
            key, value = line.strip().split('=', 1)
            config[key] = value
    return config

# Read the Axiom configuration from the file
config = read_axiom_config("axiom_config.txt")
AXIOM_DATASET = config["AXIOM_DATASET"]
AXIOM_API_KEY = config["AXIOM_API_KEY"]

# Function to read sample data from a file
def read_sample_data(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file]

# Read sample data from Splunk's eventgen repository,
# to avoid using anyone's pesonal data by accident
hostnames = read_sample_data("../eventgen/samples/hostname.sample")
ip_addresses = read_sample_data("../eventgen/samples/ip_address.sample")
mac_addresses = read_sample_data("../eventgen/samples/mac_address.sample")
oracle_usernames = read_sample_data("../eventgen/samples/oracleUserNames.sample")
oracle_actions = read_sample_data("../eventgen/samples/oracle11.action.sample")

# Adjust weights to match the number of elements in each sample data list
hostnames_weights = [60] * len(hostnames)
ip_addresses_weights = [60] * len(ip_addresses)
mac_addresses_weights = [60] * len(mac_addresses)
oracle_usernames_weights = [60] * len(oracle_usernames)
oracle_actions_weights = [60] * len(oracle_actions)

# Define Great Plains actions
gp_actions = ["login", "search", "view_product", "add_to_cart", "purchase", "logout"]

# Precompute random choices
precomputed_hostnames = [random.choice(hostnames) for _ in range(1000)]
precomputed_ip_addresses = [random.choice(ip_addresses) for _ in range(1000)]
precomputed_mac_addresses = [random.choice(mac_addresses) for _ in range(1000)]
precomputed_oracle_usernames = [random.choice(oracle_usernames) for _ in range(1000)]
precomputed_oracle_actions = [random.choice(oracle_actions) for _ in range(1000)]
precomputed_gp_actions = [random.choice(gp_actions) for _ in range(1000)]

# Define customer journey actions and their weights
customer_journey_actions = ["search", "view_product", "add_to_cart", "purchase"]
customer_journey_weights = [40, 30, 20, 5]

# Define user agents and their weights
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/16.16299",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SAMSUNG SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/12.0 Chrome/79.0.3945.136 Mobile Safari/537.36"
]
user_agent_weights = [30, 15, 10, 15, 5, 20, 15, 5]

# Axiom logging handler with batching
class AxiomHandler:
    def __init__(self, dataset, api_key, batch_size=DEFAULT_BATCH_SIZE):
        self.dataset = dataset
        self.api_key = api_key
        self.url = f"https://api.axiom.co/v1/datasets/{dataset}/ingest"
        self.batch_size = batch_size
        self.batch = []

    async def emit(self, record):
        # Strip "custom." prefix from keys
        stripped_record = {k.replace("custom_", ""): v for k, v in record.items()}
        # Add a timestamp to the record
        stripped_record['_time'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.batch.append(stripped_record)
        if len(self.batch) >= self.batch_size:
            await self.send_batch()

    async def send_batch(self):
        if not self.batch:
            return
        print("sending batch")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, json=self.batch, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to send batch: {response.status}")
                self.batch = []

    async def close(self):
        await self.send_batch()

import datetime
import random
import numpy as np
import uuid

# Assuming other necessary imports and global variables are defined

# Define service names and weights
service_names = [
    "auth-service", "search-service", "payment-service", "user-service",
    "inventory-service", "order-service", "oracle-service", "gp-service"
]
service_name_weights = [10, 10, 10, 40, 10, 10, 5, 5]

# Custom log record factory to include various attributes
def record_factory():
    global burst_mode, burst_count  # Declare global variables
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    unix_timestamp = timestamp.timestamp()
    iso_timestamp = timestamp.isoformat()
    record = {
        "user_id": int(np.random.choice(user_ids, p=adjusted_distribution)),  # Convert to native int
        "level": random.choices(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], weights=[10, 50, 20, 15, 5])[0],
        "protocol": random.choices(["HTTP", "HTTPS", "FTP", "SSH"], weights=[50, 40, 5, 5])[0],
        "source_port": random.randint(1024, 65535),
        "dest_port": random.choice([80, 443, 21, 22]),
        "packet_size": random.randint(64, 1500),
        "duration": round(random.uniform(0.1, 10.0), 2),
        "bytes_xferd": random.randint(100, 1000000),
        "source_ip": random.choice(precomputed_ip_addresses),
        "dest_ip": random.choice(precomputed_ip_addresses),
        "http_stat": generate_http_status_code()
    }
    if random.randint(1, 10) == 1:
        record["trace_id"] = str(uuid.uuid4())
        record["span_id"] = str(uuid.uuid4())
    if random.choice([True, False]):
        record["service_name"] = random.choices(service_names, weights=service_name_weights)[0]
    if random.choice([True, False]):
        record["custom_host_name"] = random.choice(precomputed_hostnames)
    if random.choice([True, False]):
        record["http_method"] = random.choice(["GET", "POST", "PUT", "DELETE"])
        record["http_url"] = random.choice(["/api/v1/resource", "/api/v1/resource/1", "/api/v1/resource/2", "/api/v1/login", "/api/v1/logout", "/api/v1/search", "/api/v1/purchase"])

    # Add Oracle and GP fields based on event type
    if record.get("service_name") == "oracle-service":
        record["oracle_username"] = random.choice(precomputed_oracle_usernames)
        record["oracle_action"] = random.choice(precomputed_oracle_actions)
    if record.get("service_name") == "gp-service":
        record["gp_action"] = random.choice(precomputed_gp_actions)

    # Add customer journey actions for user-service
    if record.get("service_name") == "user-service":
        action = random.choices(customer_journey_actions, weights=customer_journey_weights)[0]
        record["action"] = action
        if action == "search":
            record["search_term"] = random.choice(["shoes", "laptop", "phone", "book", "clothes"])
        elif action == "view_product":
            record["product_id"] = random.randint(1, 10000)
        elif action == "add_to_cart":
            record["product_id"] = random.randint(1, 10000)
            record["quantity"] = random.randint(1, 5)
        elif action == "purchase":
            record["order_id"] = str(uuid.uuid4())
            record["total_amount"] = round(random.uniform(10.0, 100.0), 2)
        # Use ISO 8601 format for customer events
        record["timestamp"] = iso_timestamp
    else:
        # Use Unix timestamp for non-customer events
        record["timestamp"] = unix_timestamp
    print(record["timestamp"])
    return record
    
    
    # Define consumer brand names and weights
    brand_names = ["Apple", "Samsung", "Sony", "Nike", "Adidas", "Microsoft", "Google", "Amazon"]
    brand_name_weights = [100, 50, 33, 25, 20, 17, 14, 12]
    return record

# Function to generate HTTP status codes with clustering
def generate_http_status_code():
    global burst_mode, burst_count
    if burst_mode is None or burst_count <= 0:
        burst_mode = random.choices(
            ["200", "301", "404", "500"],
            weights=[300, 5, 4, 1]
        )[0]
        burst_count = random.randint(1, 10)
    burst_count -= 1
    return burst_mode

# Function to generate non-customer traffic events
def generate_non_customer_traffic_event():
    return {
        "hostname": random.choices(hostnames, weights=hostnames_weights)[0],
        "ip_addr": random.choices(ip_addresses, weights=ip_addresses_weights)[0],
        "mac_addr": random.choices(mac_addresses, weights=mac_addresses_weights)[0],
        "protocol": random.choices(["HTTP", "HTTPS", "FTP", "SSH"], weights=[50, 40, 5, 5])[0],
        "source_port": random.randint(1024, 65535),
        "dest_port": random.choice([80, 443, 21, 22]),
        "packet_size": random.randint(64, 1500),
        "duration": round(random.uniform(0.1, 10.0), 2),
        "bytes_xferd": random.randint(100, 1000000),
        "source_ip": random.choice(ip_addresses),
        "dest_ip": random.choice(ip_addresses),
        "http_stat": generate_http_status_code(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

# Example usage
async def main():
    handler = AxiomHandler(dataset=AXIOM_DATASET, api_key=AXIOM_API_KEY, batch_size=DEFAULT_BATCH_SIZE)
    try:
        while True:  # Run indefinitely
            if random.random() < 0.5:  # 50% chance to generate user journey event
                record = record_factory()
            else:
                record = generate_non_customer_traffic_event()
            await handler.emit(record)
            #await asyncio.sleep(1)  # Simulate some delay between events
    except KeyboardInterrupt:
        print("Process interrupted. Sending remaining batch...")
        await handler.close()

# Run the example
asyncio.run(main())