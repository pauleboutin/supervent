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
            return
        print("sending batch")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, headers=headers, json=self.batch) as response:
                if response.status != 200:
                    print(f"Failed to send batch: {response.status}")
                else:
                    print("Batch sent successfully")

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

# Load configuration from config.json
def load_config(file_path):
    with open(file_path, 'r') as file:
        config = json.load(file)
    return config

# Generate a random event based on the source configuration
def generate_event(source_config):
    event = {"source": source_config["vendor"]}
    for field, details in source_config['fields'].items():
        if details['type'] == 'datetime':
            if source_config['timestamp_format'] == 'UTC':
                event[field] = datetime.utcnow().strftime(details.get('format', '%Y-%m-%dT%H:%M:%SZ'))
            elif source_config['timestamp_format'] == 'ISO':
                event[field] = datetime.now().isoformat()
            elif source_config['timestamp_format'] == 'Unix':
                event[field] = int(time.time())
            elif source_config['timestamp_format'] == 'RFC3339':
                event[field] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                event[field] = datetime.now().strftime(source_config['timestamp_format'])
        elif details['type'] == 'string':
            if 'allowed_values' in details:
                if 'weights' in details:
                    event[field] = random.choices(details['allowed_values'], weights=details['weights'])[0]
                else:
                    event[field] = random.choice(details['allowed_values'])
            else:
                if details.get('format') == 'ip':
                    event[field] = generate_random_ip_address()
                else:
                    event[field] = uuid.uuid4().hex
        elif details['type'] == 'int':
            if 'allowed_values' in details:
                if 'weights' in details:
                    event[field] = random.choices(details['allowed_values'], weights=details['weights'])[0]
                else:
                    event[field] = random.choice(details['allowed_values'])
            elif 'distribution' in details:
                if details['distribution'] == 'uniform':
                    event[field] = random.randint(details['constraints']['min'], details['constraints']['max'])
                elif details['distribution'] == 'normal':
                    mean = details.get('mean', 0)
                    stddev = details.get('stddev', 1)
                    event[field] = int(np.random.normal(mean, stddev))
                elif details['distribution'] == 'exponential':
                    lam = details.get('lambda', 1)
                    event[field] = int(np.random.exponential(1/lam))
                elif details['distribution'] == 'zipfian':
                    s = details.get('s', 1.07)
                    event[field] = int(np.random.zipf(s))
                elif details['distribution'] == 'long_tail':
                    alpha = details.get('alpha', 1.5)
                    event[field] = int(np.random.pareto(alpha))
                elif details['distribution'] == 'random':
                    event[field] = random.randint(details['constraints']['min'], details['constraints']['max'])
            else:
                min_val = int(details.get('constraints', {}).get('min', 0))
                max_val = int(details.get('constraints', {}).get('max', 100))
                event[field] = random.randint(min_val, max_val)
        # Add more types and distributions as needed
    print(event)  # Debug statement to print the complete event
    return event

# Generate a random IP address
def generate_random_ip_address():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"

# Signal handler to gracefully exit on ^C or kill signal
def signal_handler(signal, frame):
    print("Received interrupt signal, sending remaining events...")
    if len(event_generator.batch) > 0:
        asyncio.create_task(event_generator.send_batch())
    sys.exit(0)

# Main function to generate events
async def main():
    parser = argparse.ArgumentParser(description='Generate and send events.')
    parser.add_argument('--config', type=str, default='config.json', help='Path to the configuration file')
    parser.add_argument('--axiom_dataset', type=str, required=True, help='Axiom dataset name')
    parser.add_argument('--axiom_api_key', type=str, required=True, help='Axiom API key')
    parser.add_argument('--batch_size', type=int, default=DEFAULT_BATCH_SIZE, help='Batch size for HTTP requests')
    parser.add_argument('--postgres_host', type=str, help='PostgreSQL host')
    parser.add_argument('--postgres_port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--postgres_db', type=str, help='PostgreSQL database name')
    parser.add_argument('--postgres_user', type=str, help='PostgreSQL user')
    parser.add_argument('--postgres_password', type=str, help='PostgreSQL password')
    args = parser.parse_args()

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

    # Set up signal handling to gracefully exit on ^C or kill signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Generate events in a round-robin fashion indefinitely
    while True:
        for source in config['sources']:
            event = generate_event(source)
            await event_generator.emit(event)

if __name__ == "__main__":
    asyncio.run(main())