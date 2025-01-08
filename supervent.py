import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import random
import yaml
import numpy as np
import signal
import sys
import uuid
import time
import argparse
from pathlib import Path
import logging
import asyncio
from itertools import islice
import aiohttp
import psycopg2
from psycopg2.extras import Json
import aiofiles
import math

def setup_logging(args):
    if args.log_level == 'NONE':
        logging.basicConfig(level=logging.CRITICAL + 1)
    else:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            # format='%(asctime)s - %(levelname)s - %(message)s'
            format='%(message)s',
            handlers=[logging.StreamHandler(sys.stdout)] # Log to stdout
        )

# Load environment variables from .env file
load_dotenv(override=True)

DEFAULT_BATCH_SIZE = 100000
DEFAULT_OUTPUT_FILE = sys.stdout

def load_config(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

async def main():
    event_count = 0
    start_generation_time = time.time()
    generator = None  # Initialize generator to prevent UnboundLocalError

    try:
        args = parse_args()
        setup_logging(args)
        logging.info(f"AXIOM_API_TOKEN from env: {os.environ.get('AXIOM_API_TOKEN', 'Not found')}")

        logging.debug("Loading configuration...")
        config = load_config(args.config)
        logging.debug("Configuration loaded successfully.")

        # Configure output based on args
        if args.output == 'axiom':
            global AXIOM_API_TOKEN, AXIOM_API_URL
            AXIOM_API_TOKEN = args.token
            AXIOM_DATASET = args.dataset
            AXIOM_API_URL = f"https://api.axiom.co/v1/datasets/{args.dataset}/ingest"
        elif args.output == 'postgres':
            # Setup PostgreSQL connection
            import psycopg2
            global PG_CONNECTION
            PG_CONNECTION = psycopg2.connect(
                host=args.pg_host,
                port=args.pg_port,
                dbname=args.pg_db,
                user=args.pg_user,
                password=args.pg_password
            )
            # Create events table if it doesn't exist
            with PG_CONNECTION.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {args.pg_table} (
                        id SERIAL PRIMARY KEY,
                        source VARCHAR(255),
                        timestamp TIMESTAMP WITH TIME ZONE,
                        message TEXT,
                        event_type VARCHAR(255),
                        attributes JSONB
                    )
                """)
            PG_CONNECTION.commit()

        start_time = datetime.fromisoformat(config['start_time'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(config['end_time'].replace('Z', '+00:00'))
        logging.debug(f"Start time: {start_time}, End time: {end_time}")

        event_frequencies = config.get('event_frequencies', {})
        logging.debug("Event frequencies loaded:", event_frequencies)

        generator = EventGenerator(event_frequencies, config, output_type=args.output, batch_size=args.batch_size, output_file=args.file)
        logging.debug("Event generator created.")

        signal.signal(signal.SIGINT, generator.signal_handler)
        signal.signal(signal.SIGTERM, generator.signal_handler)

        await generator.generate_events(start_time, end_time)
        event_count += len(generator.processed_events)

        total_time = time.time() - start_generation_time
        if generator:
            logging.info(f"Generated {generator.total_events_sent} events in {total_time:.2f} seconds.")
        else:
            logging.info(f"No events generated in {total_time:.2f} seconds.")

        if args.output == 'postgres':
            PG_CONNECTION.close()

    except Exception as e:
        logging.critical(f"An error occurred: {str(e)}")
        total_time = time.time() - start_generation_time
        if generator:
            logging.info(f"Generated {generator.total_events_sent} events in {total_time:.2f} seconds.")
        else:
            logging.info(f"Failed before generating any events. Elapsed time: {total_time:.2f} seconds.")
        
        if args.output == 'postgres' and 'PG_CONNECTION' in globals():
            PG_CONNECTION.close()
        raise


class EventGenerator:
    def __init__(self, event_frequencies, config, output_type='axiom', batch_size=DEFAULT_BATCH_SIZE, output_file=DEFAULT_OUTPUT_FILE):
        self.event_frequencies = event_frequencies
        self.config = config
        self.dependencies = config.get('dependencies', [])
        self.processed_events = set()
        self.total_events_sent = 0 
        self.start_generation_time = None
        self.response_time_min = config['response_time']['min']
        self.response_time_max = config['response_time']['max']
        self.output_type = output_type
        self.batch_size = batch_size
        self.output_file = output_file


    def signal_handler(self, signum, frame):
        """Handle the signal to exit gracefully."""
        total_time = time.time() - self.start_generation_time
        # Use sys.stderr.write instead of logging to avoid potential stdout conflicts
        sys.stderr.write(f"\nGenerated {len(self.processed_events)} unique events in {total_time:.2f} seconds.\n")
        sys.stderr.flush()
        if self.output_file != sys.stdout:
            try:
                    logging.shutdown()  # Ensure all logging is complete
            except Exception:
                pass
        os._exit(0)

    async def generate_events(self, start_time, end_time):
        logging.debug("Starting event generation...")
        self.start_generation_time = time.time()
        for source, event in self.config['sources'].items():
            logging.debug(f"Generating events for source: {source}")
            await self.generate_source_events(source, event, start_time, end_time)
        logging.debug("Event generation completed.")

    async def generate_source_events(self, source, event, start_time, end_time):
        logging.debug(f"Generating source events for: {source}")
        parameters = event['volume']
        event_types = event['event_types']
        source_description = event['description']
        logging.debug(f"Parameters for {source}: {parameters}")

        for volume in parameters:
            pattern = volume.get('pattern')
            count = int(volume.get('count', 0))
            distribution = volume['distribution']
            logging.debug(f"Generating {count} events with {distribution} distribution for pattern: {pattern}")

            if not isinstance(count, int):
                raise ValueError(f"Expected count to be an integer, got {type(count)} instead.")

            if pattern:
                await self.generate_pattern_events(pattern, count, distribution, start_time, end_time, source_description, event_types, source)
            else:
                time_period = volume['time_period']
                await self.create_events(count, distribution, time_period, source_description, event_types, source)

    async def generate_pattern_events(self, pattern, count, distribution, start_time, end_time, source_description, event_types, source):
        if pattern == "weekday":
            await self.generate_weekday_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "weekend":
            await self.generate_weekend_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "24/7":
            await self.generate_24_7_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "sine_wave":
            await self.generate_sine_wave_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "linear_increase":
            await self.generate_linear_increase_events(count, distribution, start_time, end_time, source_description, event_types, source)
        else:
            raise ValueError(f"Unsupported pattern type: {pattern}")

    async def generate_weekday_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        current_time = start_time
        while current_time < end_time:
            if current_time.weekday() < 5:
                await self.create_events(count // 5, distribution, {'start': current_time.isoformat(), 'end': (current_time + timedelta(days=1)).isoformat()}, source_description, event_types, source)
            current_time += timedelta(days=1)

    async def generate_weekend_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        current_time = start_time
        while current_time < end_time:
            if current_time.weekday() >= 5:
                await self.create_events(count // 2, distribution, {'start': current_time.isoformat(), 'end': (current_time + timedelta(days=1)).isoformat()}, source_description, event_types, source)
            current_time += timedelta(days=1)

    async def generate_24_7_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        total_days = (end_time - start_time).days + 1
        time_period = {
            'start': start_time.isoformat(),  # Convert to ISO format string
            'end': end_time.isoformat()       # Convert to ISO format string
        }
        await self.create_events(count, distribution, time_period, source_description, event_types, source)

    async def generate_sine_wave_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        total_seconds = (end_time - start_time).total_seconds()
        for i in range(count):
            t = i / count * total_seconds
            amplitude = (1 + math.sin(2 * math.pi * t / total_seconds)) / 2
            event_time = start_time + timedelta(seconds=t)
            await self.create_events(int(amplitude * count), distribution, {'start': event_time, 'end': event_time}, source_description, event_types, source)

    async def generate_linear_increase_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        total_seconds = (end_time - start_time).total_seconds()
        for i in range(count):
            t = i / count * total_seconds
            event_time = start_time + timedelta(seconds=t)
            await self.create_events(i + 1, distribution, {'start': event_time, 'end': event_time}, source_description, event_types, source)

    def extract_placeholders(self, format_string):
        """Extract all placeholder names from a format string."""
        import re
        return set(re.findall(r'{([^}]+)}', format_string))

    def chain_events(self, event, events):
        event_key = (
            event['source_type'], 
            event['attributes'].get('request_id'),
            event['event_type']
        )
        if event_key in self.processed_events:
            return

        self.processed_events.add(event_key)
        
        # Process all dependencies for this event
        for dependency in self.dependencies:
            if (dependency['trigger']['source'] == event['source_type'] and
                dependency['trigger']['event_type'] == event['event_type']):
                
                # Generate the dependent event using the unified create_event
                dependent_event = self.create_event(
                    source_name=dependency['action']['source'],
                    event_type=dependency['action']['event_type'],
                    parent_event=event
                )
                events.append(dependent_event)
                
                # Recursively process dependencies for the new event
                self.chain_events(dependent_event, events)

    async def create_events(self, count, distribution, time_period, source_description, event_types, source):
        events = []
        start_time, end_time = self.parse_time_period(time_period)

        for _ in range(count):
            if distribution == 'gaussian':
                fake_timestamp = self.generate_normal_time(
                    start_time + (end_time - start_time) / 2,
                    (end_time - start_time) / 6
                )
            elif distribution == 'random':
                fake_timestamp = self.random_time_between(start_time, end_time)
            else:
                raise ValueError(f"Unsupported distribution type: {distribution}")

            event_type = random.choice(event_types)
            
            if not event_type.get('create_from_scratch', False):
                continue

            # Create the top-level event using the unified create_event
            event = self.create_event(
                source_name=source,
                event_type=event_type['type'],
                parent_event=None,
                timestamp=fake_timestamp
            )
            events.append(event)
            self.chain_events(event, events)

            # Handle batching
            if len(events) >= self.batch_size:
                if self.output_type == 'postgres':
                    await self.send_events_to_postgres(events)
                elif self.output_type == 'file':
                    await self.send_events_to_file(events)
                else:  # default to axiom
                    await self.send_events_to_axiom(events)
                events = []

        # Send remaining events
        if events:
            if self.output_type == 'postgres':
                await self.send_events_to_postgres(events)
            elif self.output_type == 'file':
                await self.send_events_to_file(events)
            else:  # default to axiom
                await self.send_events_to_axiom(events)

    def create_event(self, source_name, event_type, parent_event=None, timestamp=None):
        """Unified event creation function for both top-level and dependent events."""
        source_config = self.config['sources'].get(source_name, {})
        source_description = source_config.get('description', source_name)
        dataset = source_config.get('dataset', os.environ.get('AXIOM_DATASET'))

        # Generate or inherit request_id
        request_id = str(uuid.uuid4()) if parent_event is None else parent_event['attributes']['request_id']
        
        # Use provided timestamp or inherit from parent or use current time
        event_time = timestamp or (parent_event['_time'] if parent_event else datetime.now(timezone.utc))
        
        # Start with basic attributes
        details = {
            'timestamp': event_time.isoformat() + "Z",
            'request_id': request_id
        }

        # Add source-specific attributes based on configuration
        for attr_name, attr_config in source_config.get('attributes', {}).items():
            if attr_config.get('type') == 'choice' and attr_config.get('values'):
                details[attr_name] = random.choice(attr_config['values'])
            elif attr_config.get('type') == 'integer':
                min_val = attr_config.get('min', 0)
                max_val = attr_config.get('max', 100)
                details[attr_name] = random.randint(min_val, max_val)
            elif attr_config.get('type') == 'string':
                if attr_config.get('generator') == 'client_ip':
                    details[attr_name] = self.generate_client_ip()

        # Get the event type configuration and format the message
        event_types = source_config.get('event_types', [])
        event_type_config = next((et for et in event_types if et['type'] == event_type), None)
        
        if not event_type_config:
            raise ValueError(f"Event type {event_type} not found in source {source_name}")

        message_format = event_type_config['format']
        formatted_message = self.format_message(message_format, details)

        return {
            'source': source_description,
            'source_type': source_name,
            'dataset': dataset,
            '_time': event_time,
            'event_type': event_type,
            'attributes': details
        }


    def clean_event_batch(self, events):
        """Clean a batch of events by removing source_type and converting timestamps."""
        for event in events:
            event.pop('source_type', None)  # Remove source_type if it exists
                    



    def format_message(self, message, details):
        formatted_details = {}
        for key, value in details.items():
            if isinstance(value, str) and ' ' in value:
                formatted_details[key] = f'"{value}"'
            else:
                formatted_details[key] = value
        return message.format(**formatted_details)

    def parse_time_period(self, time_period):
        logging.debug(f"Received time period for parsing: {time_period}")
        try:
            if isinstance(time_period, dict):
                if isinstance(time_period['start'], str):
                    start_time = datetime.fromisoformat(time_period['start'].replace('Z', '+00:00'))
                else:
                    start_time = time_period['start']
                
                if isinstance(time_period['end'], str):
                    end_time = datetime.fromisoformat(time_period['end'].replace('Z', '+00:00'))
                else:
                    end_time = time_period['end']
            else:
                raise ValueError(f"Invalid time period format: {type(time_period)}")

            logging.debug(f"Parsed time period: start_time={start_time}, end_time={end_time}")
            return start_time, end_time
        except Exception as e:
            logging.critical(f"Error parsing time period: {e}")
            logging.critical(f"Time period type: {type(time_period)}")
            logging.critical(f"Time period content: {time_period}")
            raise


    async def send_events_to_axiom(self, events):
        # First, group events by source_type (and thus by dataset)
        events_by_source = {}
        for event in events:
            source_type = event.get('source_type')
            if source_type not in events_by_source:
                events_by_source[source_type] = []
            events_by_source[source_type].append(event)

        # Process each source's events separately
        async with aiohttp.ClientSession() as session:
            for source_type, source_events in events_by_source.items():
                # Get source configuration and dataset
                source_config = self.config['sources'].get(source_type, {})
                dataset = source_config.get('dataset', os.environ.get('AXIOM_DATASET'))
                
                # Convert datetime objects to ISO format
                for event in source_events:
                    if '_time' in event and isinstance(event['_time'], datetime):
                        event['_time'] = event['_time'].isoformat()

                # Process events in chunks
                for chunk in self.chunk_list(source_events, self.batch_size):
                    api_url = f"https://api.axiom.co/v1/datasets/{dataset}/ingest"
                    logging.debug(f"Sending events to dataset: {dataset} for source_type: {source_type}")
                    
                    async with session.post(
                        api_url,
                        headers={
                            "Authorization": f"Bearer {AXIOM_API_TOKEN}",
                            "Content-Type": "application/json"
                        },
                        json=chunk
                    ) as response:
                        if response.status != 200:
                            logging.critical(f"Failed to send events to Axiom dataset {dataset}: {await response.text()}")
                        else:
                            self.total_events_sent += len(chunk)
                            logging.debug(f"Successfully sent {len(chunk)} events to Axiom dataset {dataset}")

        events.clear()


    def chunk_list(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]


    async def send_events_to_postgres(self, events):
            with PG_CONNECTION.cursor() as cur:
                for event in events:
                    cur.execute("""
                        INSERT INTO events (source, timestamp, message, event_type, attributes)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        event['source'],
                        event['_time'],
                        event['message'],
                        event['event_type'],
                        json.dumps(event['attributes'])
                    ))
            PG_CONNECTION.commit()
            self.total_events_sent += len(events)  # Increment counter
            logging.debug(f"Successfully sent {len(events)} events to PostgreSQL.")
            events.clear()

    async def send_events_to_file(self, events):
        # Convert datetime objects to ISO format strings
        for event in events:
            if '_time' in event and isinstance(event['_time'], datetime):
                event['_time'] = event['_time'].isoformat()
    
        if self.output_file == sys.stdout:  
            # Write directly to stdout
            for event in events:
                print(json.dumps(event))
        else:
            # Write to specified file
            async with aiofiles.open(self.output_file, 'a') as f:
                for event in events:
                    await f.write(json.dumps(event) + '\n')
        
        self.total_events_sent += len(events)
        if self.output_file != '-':
            logging.debug(f"Successfully wrote {len(events)} events to {self.output_file}")
        events.clear()



    def generate_normal_time(self, mean, std_dev):
        random_seconds = int(np.random.normal(0, std_dev.total_seconds()))
        fake_timestamp = mean + timedelta(seconds=random_seconds)
        return fake_timestamp

    def random_time_between(self, start, end):
        delta = end - start
        random_seconds = random.randint(0, int(delta.total_seconds()))
        return start + timedelta(seconds=random_seconds)

    def generate_client_ip(self):
        start_time = time.time()
        private_ip = random.choice([
            f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}",
            f"172.{random.randint(16, 31)}.{random.randint(0, 255)}.{random.randint(0, 255)}",
            f"192.168.{random.randint(0, 255)}.{random.randint(0, 255)}"
        ])
        end_time = time.time()
        logging.debug(f"Client IP generation took {end_time - start_time:.6f} seconds")
        return private_ip

    def generate_response_time(self):
        """Generate a random response time between the configured min and max."""
        return random.randint(self.response_time_min, self.response_time_max)

def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate realistic log events with configurable patterns and dependencies'
    )
    
    # Config file argument
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config/config.yaml',
        help='Path to configuration YAML file (default: config/config.yaml)'
    )
 
    parser.add_argument('-l', '--log-level', 
        default='none', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE'],
        help="Set the logging level",
        type=str.upper)  # Convert input to uppercase

    parser.add_argument(
        '-b', '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Number of events to send in each batch (default: {DEFAULT_BATCH_SIZE})'
    )

    # Output type selection
    parser.add_argument(
        '-o','--output',
        choices=['axiom', 'postgres', 'file'],
        default='axiom',
        help='Select output destination (default: axiom)'
    )
    
    parser.add_argument(
        '-f', '--file',
        default=DEFAULT_OUTPUT_FILE,
        help=f'Output file path (default: {DEFAULT_OUTPUT_FILE})'
    )

    # Axiom arguments
    axiom_group = parser.add_argument_group('Axiom options')

    axiom_group.add_argument(
        '-d', '--dataset',
        type=str,
        default=os.environ.get('AXIOM_DATASET'),
        help='Axiom dataset name to ingest events'
    )

    axiom_group.add_argument(
        '-t', '--token',
        type=str,
        default=os.environ.get('AXIOM_API_TOKEN'),
        help='Axiom API token (can also be set via AXIOM_API_TOKEN environment variable)'
    )

    # PostgreSQL arguments
    pg_group = parser.add_argument_group('PostgreSQL options')
    pg_group.add_argument(
        '--pg-host',
        type=str,
        default=os.environ.get('POSTGRES_HOST', 'localhost'),
        help='PostgreSQL host (default: localhost)'
    )
    pg_group.add_argument(
        '--pg-port',
        type=int,
        default=int(os.environ.get('POSTGRES_PORT', 5432)),
        help='PostgreSQL port (default: 5432)'
    )
    pg_group.add_argument(
        '--pg-db',
        type=str,
        default=os.environ.get('POSTGRES_DB'),
        help='PostgreSQL database name'
    )
    pg_group.add_argument(
        '--pg-user',
        type=str,
        default=os.environ.get('POSTGRES_USER'),
        help='PostgreSQL username'
    )
    pg_group.add_argument(
        '--pg-password',
        type=str,
        default=os.environ.get('POSTGRES_PASSWORD'),
        help='PostgreSQL password'
    )
    pg_group.add_argument(
        '--pg-table',
        type=str,
        default='events',
        help='PostgreSQL table name (default: events)'
    )

    args = parser.parse_args()

    # Validate config file exists
    if not Path(args.config).is_file():
        parser.error(f"Config file not found: {args.config}")

    # Validate output-specific requirements
    if args.output == 'axiom':
        if not args.dataset:
            parser.error("Axiom dataset name (-d/--dataset) is required when using axiom output")
        if not args.token:
            parser.error("Axiom API token must be provided either via --token argument or AXIOM_TOKEN environment variable")
    elif args.output == 'postgres':
        required_pg_args = {
            'pg_db': 'POSTGRES_DB',
            'pg_user': 'POSTGRES_USER',
            'pg_password': 'POSTGRES_PASSWORD'
        }
        for arg, env_var in required_pg_args.items():
            if not getattr(args, arg.replace('-', '_')):
                parser.error(f"PostgreSQL {arg} must be provided either via argument or {env_var} environment variable")

    return args


if __name__ == '__main__':
    asyncio.run(main())

