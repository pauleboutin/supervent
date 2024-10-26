import json
import random
import time
from datetime import datetime, timezone
import uuid
import asyncio
import aiohttp
import math
import argparse
import signal
import sys
import numpy as np
import psycopg2
from faker import Faker
import logging

DEFAULT_BATCH_SIZE = 100

class EventGenerator:
    def __init__(self, dataset, api_key, batch_size=DEFAULT_BATCH_SIZE, postgres_config=None):
        self.dataset = dataset
        self.api_key = api_key
        self.url = f"https://api.axiom.co/v1/datasets/{dataset}/ingest"
        self.batch_size = batch_size
        self.batch = []
        self.postgres_conn = None

        if postgres_config:
            self.postgres_conn = psycopg2.connect(
                host=postgres_config['host'],
                port=postgres_config['port'],
                dbname=postgres_config['dbname'],
                user=postgres_config['user'],
                password=postgres_config['password']
            )
            logging.debug("PostgreSQL connection established")

    async def emit(self, record):
        # Strip "custom." prefix from keys
        stripped_record = {k.replace("custom_", ""): v for k, v in record.items()}
        # Add a timestamp to the record
        stripped_record['_time'] = datetime.now(timezone.utc).isoformat()

        self.batch.append(stripped_record)
        if len(self.batch) >= self.batch_size:
            await self.send_batch()

    async def send_batch(self):
        if not self.batch:
            logging.debug("Batch is empty, nothing to send")
            return
        # print("sending batch")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, headers=headers, json=self.batch) as response:
                if response.status != 200:
                    logging.error(f"Error occurred while sending the batch, status code: {response.status}")
                else:
                    logging.debug("Batch sent successfully")

        if self.postgres_conn:
            self.send_to_postgres(self.batch)

        self.batch = []

    def send_to_postgres(self, batch):
        cursor = self.postgres_conn.cursor()
        for record in batch:
            columns = record.keys()
            values = [record[column] for column in columns]
            insert_statement = f"INSERT INTO {self.dataset} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(values))})"
            cursor.execute(insert_statement, values)
        self.postgres_conn.commit()
        cursor.close()

# Load configuration from sources.json
def load_config(file_path):
    try:
        with open(file_path, 'r') as file:
            config = json.load(file)
        logging.debug("Configuration loaded successfully")
        return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        sys.exit(1)

# Generate usernames based on the specified groups
def generate_usernames(groups_config):
    usernames = {}
    for group_name, group_details in groups_config.items():
        regions = group_details.get('regions', ['en_US'])  # Default to 'en_US' if no region is specified
        count = group_details['count']
        usernames[group_name] = []

        # Distribute the count evenly across the regions
        names_per_region = count // len(regions)
        extra_names = count % len(regions)

        for region in regions:
            Faker.seed(0)  # Ensure reproducibility
            fake = Faker(region)
            for _ in range(names_per_region):
                usernames[group_name].append(fake.name())

        # Add extra names to make up the total count
        for _ in range(extra_names):
            Faker.seed(0)  # Ensure reproducibility
            fake = Faker(random.choice(regions))
            usernames[group_name].append(fake.name())

    logging.debug(f"Generated Usernames: {usernames}")
    return usernames

# Generate a random event based on the source configuration
def generate_event(source_config, usernames):
    event = {"Generated-by": source_config["name"]}
    if "description" in source_config:
        event["description"] = source_config["description"]
    for field, details in source_config['fields'].items():
        if details['type'] == 'datetime':
            event[field] = datetime.now(timezone.utc).strftime(details.get('format', '%Y-%m-%dT%H:%M:%SZ'))
        elif details['type'] == 'string':
            if 'group' in details:
                group_name = details['group']
                count = details['count']
                event[field] = random.choice(usernames[group_name][:count])
            elif 'allowed_values' in details:
                event[field] = random.choices(details['allowed_values'], weights=details.get('weights', None))[0]
            elif details.get('format') == 'ip':
                event[field] = generate_random_ip_address()
            elif details.get('format') == 'uuid':
                event[field] = str(uuid.uuid4())
            else:
                event[field] = uuid.uuid4().hex
        elif details['type'] == 'int':
            if 'allowed_values' in details:
                event[field] = random.choices(details['allowed_values'], weights=details.get('weights', None))[0]
            else:
                min_val = details['constraints']['min']
                max_val = details['constraints']['max']
                event[field] = random.randint(min_val, max_val)
        # Add more types and distributions as needed

    # Handle message field with placeholders
    if 'message' in source_config['fields']:
        message_template = random.choices(source_config['fields']['message']['messages'], weights=source_config['fields']['message'].get('weights', None))[0]
        event['message'] = replace_placeholders(message_template, event)

    logging.debug(event)  # Debug statement to print the complete event
    return event

# Generate a random IP address
def generate_random_ip_address():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"

# Replace placeholders in the message template with actual values
def replace_placeholders(format, values):
    for key, value in values.items():
        placeholder = f"{{{key}}}"
        format = format.replace(placeholder, str(value))
    return format

# Signal handler to gracefully exit on ^C or kill signal
def signal_handler(signal, frame):
    logging.info("Received interrupt signal, sending remaining events...")
    if len(event_generator.batch) > 0:
        asyncio.create_task(event_generator.send_batch())
    sys.exit(0)

# Main function to generate events
async def main():
    parser = argparse.ArgumentParser(description='Generate and send events.')
    parser.add_argument('--config', type=str, default='sources.json', help='Path to the configuration file')
    parser.add_argument('--axiom_dataset', type=str, required=True, help='Axiom dataset name')
    parser.add_argument('--axiom_api_key', type=str, required=True, help='Axiom API key')
    parser.add_argument('--batch_size', type=int, default=DEFAULT_BATCH_SIZE, help='Batch size for HTTP requests')
    parser.add_argument('--postgres_host', type=str, help='PostgreSQL host')
    parser.add_argument('--postgres_port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--postgres_db', type=str, help='PostgreSQL database name')
    parser.add_argument('--postgres_user', type=str, help='PostgreSQL user')
    parser.add_argument('--postgres_password', type=str, help='PostgreSQL password')
    parser.add_argument('--log_level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE'],
                        help="Set the logging level")
    args = parser.parse_args()

    if args.log_level == 'NONE':
        logging.basicConfig(level=logging.CRITICAL + 1)  # Disable logging
    else:
        logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info("Starting Event Generator")

    # print("Arguments parsed successfully")

    config = load_config(args.config)
    dataset = args.axiom_dataset
    api_key = args.axiom_api_key
    batch_size = args.batch_size

    postgres_config = None
    if args.postgres_host and args.postgres_db and args.postgres_user and args.postgres_password:
        postgres_config = {
            'host': args.postgres_host,
            'port': args.postgres_port,
            'dbname': args.postgres_db,
            'user': args.postgres_user,
            'password': args.postgres_password
        }

    global event_generator
    event_generator = EventGenerator(dataset=dataset, api_key=api_key, batch_size=batch_size, postgres_config=postgres_config)

    # Generate usernames based on the specified groups
    usernames = generate_usernames(config.get('username_groups', {}))

    # Set up signal handling to gracefully exit on ^C or kill signal
    from functools import partial
    signal.signal(signal.SIGINT, partial(signal_handler))
    signal.signal(signal.SIGTERM, partial(signal_handler))

    logging.debug("Starting event generation")

    # Generate events in a round-robin fashion indefinitely
    while True:
        for source in config['sources']:
            event = generate_event(source, usernames)
            await event_generator.emit(event)
        # await asyncio.sleep(1)  # Add a small delay to avoid tight loop

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Exception occurred: {e}")