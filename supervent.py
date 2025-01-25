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
from multiprocessing import Pool, cpu_count
from functools import partial
import multiprocessing.shared_memory
from concurrent.futures import ProcessPoolExecutor
import json as standard_json  # Import standard json module alongside ujson
import ujson  # Keep the fast ujson for general use

# At the top of the file, after imports
shutdown_requested = multiprocessing.Value('i', 0)


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
DEFAULT_OUTPUT_FILE = '-'  # Use '-' to represent stdout instead of sys.stdout directly

def load_config(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

async def main():
    event_count = 0
    start_generation_time = time.time()

    try:
        args = parse_args()
        setup_logging(args)
        logging.info(f"AXIOM_API_TOKEN from env: {os.environ.get('AXIOM_API_TOKEN', 'Not found')}")

        logging.debug("Loading configuration...")
        config = load_config(args.config)
        logging.debug("Configuration loaded successfully.")

        # Create the generator instance early
        generator = EventGenerator(
            config.get('event_frequencies', {}),
            config,
            output_type=args.output,
            batch_size=args.batch_size,
            output_file_path=args.file
        )

        # Set up signal handlers after creating the generator
        signal.signal(signal.SIGINT, generator.signal_handler)
        signal.signal(signal.SIGTERM, generator.signal_handler)

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

        # Calculate total events from config
        total_events = sum(
            sum(vol['count'] for vol in source.get('volume', []))
            for source in config['sources'].values()
        )
        
        # Use larger chunks for better efficiency
        chunk_size = total_events // cpu_count()
        
        # Create time chunks
        time_delta = (end_time - start_time) / cpu_count()
        time_chunks = [
            (start_time + (time_delta * i), 
             start_time + (time_delta * (i + 1)),
             chunk_size)  # Each worker gets a fair share of the total
            for i in range(cpu_count())
        ]

        # Prepare arguments for worker processes
        worker_args = [
            (config.get('event_frequencies', {}), config, args.output, args.batch_size, 
             args.file, time_chunk) 
            for time_chunk in time_chunks
        ]

        # Run event generation in parallel
        with Pool(processes=cpu_count()) as pool:
            try:
                all_events = []
                for chunk_events in pool.imap_unordered(worker_generate_chunk, worker_args):
                    if chunk_events:
                        all_events.extend(chunk_events)
                        if len(all_events) >= args.batch_size:
                            await generator.send_events_to_axiom(all_events)
                            all_events = []
                
                # Send any remaining events
                if all_events:
                    await generator.send_events_to_axiom(all_events)
                    
            except KeyboardInterrupt:
                logging.info("Shutdown requested. Cleaning up...")
            finally:
                if 'pool' in locals():
                    pool.terminate()
                    pool.join()

        # No need for separate generate_events call
        total_time = time.time() - start_generation_time
        logging.info(f"Generated {generator.total_events_sent} events in {total_time:.2f} seconds.")

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

    
def worker_generate_chunk(args):
    event_frequencies, config, output_type, batch_size, output_file_path, time_chunk = args
    
    generator = EventGenerator(
        event_frequencies, 
        config, 
        output_type=output_type, 
        batch_size=batch_size, 
        output_file_path=output_file_path
    )
    
    start_time, end_time, chunk_size = time_chunk
    events = []
    
    try:
        # Calculate events per source based on volume configuration
        total_volume = sum(
            sum(vol['count'] for vol in source_config.get('volume', []))
            for source_config in config['sources'].values()
        )
        
        # Generate events for each source
        for source_name, source_config in config['sources'].items():
            if shutdown_requested.value:
                break
                
            source_volume = sum(vol['count'] for vol in source_config.get('volume', []))
            source_chunk_size = int((source_volume / total_volume) * chunk_size)
            
            event_types = [et for et in source_config.get('event_types', []) 
                          if et.get('create_from_scratch', True)]  # Changed to True
            
            if not event_types:
                continue
                
            for _ in range(source_chunk_size):
                if shutdown_requested.value:
                    break
                    
                event_type = random.choice(event_types)
                event = generator.create_event(
                    source_name=source_name,
                    event_type=event_type['type'],
                    timestamp=generator.random_time_between(start_time, end_time)
                )
                events.append(event)
                
                # Process dependencies immediately for this event
                generator.chain_events(event, events)
                
                if len(events) >= batch_size:
                    return events
    except KeyboardInterrupt:
        return events
    
    return events

class EventGenerator:
    def __init__(self, event_frequencies, config, output_type='axiom', batch_size=DEFAULT_BATCH_SIZE, output_file_path=None):
        self.event_frequencies = event_frequencies
        self.config = config
        self.upload_config = config.get('upload_config', {}).get('axiom', {})
        self.max_concurrent_uploads = self.upload_config.get('max_concurrent_uploads', 8)
        self.connection_pool_size = self.upload_config.get('connection_pool_size', 100)
        self.retry_attempts = self.upload_config.get('retry_attempts', 3)
        self.retry_delay = self.upload_config.get('retry_delay', 1.0)
        self.dependencies = config.get('dependencies', [])
        self.processed_events = set()
        self.total_events_sent = 0 
        self.start_generation_time = None
        self.response_time_min = config['response_time']['min']
        self.response_time_max = config['response_time']['max']
        self.output_type = output_type
        self.batch_size = batch_size
        self.output_file_path = output_file_path
        self.num_workers = os.cpu_count() - 1 or 1
        self.upload_queue_size = self.upload_config.get('upload_queue_size', 1000)
        self.network_interfaces = self.upload_config.get('network_interfaces', 4)
        self.upload_semaphore = asyncio.Semaphore(self.network_interfaces * 8)  # Control concurrent connections per interface

    def generate_chunk(self, time_chunk):
        start_time, end_time, chunk_size = time_chunk
        events = []
        
        # First generate all primary (create_from_scratch) events
        for source_name, source_config in self.config['sources'].items():
            if shutdown_requested.value:
                break
                
            event_types = [et for et in source_config.get('event_types', []) 
                          if et.get('create_from_scratch', True)]  # Default to True
            
            if not event_types:
                continue
                
            for _ in range(chunk_size):
                if shutdown_requested.value:
                    break
                    
                event_type = random.choice(event_types)
                event = self.create_event(
                    source_name=source_name,
                    event_type=event_type['type'],
                    timestamp=self.random_time_between(start_time, end_time)
                )
                events.append(event)
                
                # Process dependencies immediately for this event
                self.chain_events(event, events)
                
                if len(events) >= self.batch_size:
                    return events
        
        return events

    def signal_handler(self, signum, frame):
        """Handle the signal to exit gracefully."""
        with shutdown_requested.get_lock():
            shutdown_requested.value = 1
        total_time = time.time() - self.start_generation_time
        sys.stderr.write(f"\nShutdown requested. Generated {len(self.processed_events)} unique events in {total_time:.2f} seconds.\n")
        sys.stderr.flush()

    async def generate_events(self, start_time, end_time):
        """Parallelize event generation across all cores"""
        logging.debug("Starting event generation...")
        self.start_generation_time = time.time()
        chunk_size = (end_time - start_time) / cpu_count()
        
        with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor, 
                    self.generate_chunk, 
                    (start_time + timedelta(seconds=i * chunk_size), 
                     start_time + timedelta(seconds=(i + 1) * chunk_size))
                )
                for i in range(cpu_count())
            ]
            results = await asyncio.gather(*futures)
        logging.debug("Event generation completed.")

    async def generate_source_events(self, source, event, start_time, end_time):
        gen_start = time.time()
        total_events = 0
        
        # Create multiple upload queues, one per network interface
        queues = [asyncio.Queue(maxsize=self.upload_queue_size) 
                 for _ in range(self.network_interfaces)]
        
        # Performance counters
        upload_times = [0.0] * self.network_interfaces
        upload_counts = [0] * self.network_interfaces
        
        async def upload_with_timing(queue, interface_id):
            nonlocal upload_times, upload_counts
            # Configure TCP connector with interface-specific settings
            connector = aiohttp.TCPConnector(
                limit=self.connection_pool_size // self.network_interfaces,
                force_close=True,
                enable_cleanup_closed=True,
                ssl=False
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                json_serialize=lambda x: standard_json.dumps(x, cls=DateTimeEncoder),
                timeout=aiohttp.ClientTimeout(total=300)
            ) as session:
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    
                    upload_start = time.time()
                    async with self.upload_semaphore:
                        await self.upload_chunk_with_retry(session, source, chunk, interface_id)
                    upload_times[interface_id] += time.time() - upload_start
                    upload_counts[interface_id] += len(chunk)
                    queue.task_done()
        
        # Start upload tasks with timing
        upload_tasks = [
            asyncio.create_task(upload_with_timing(queue, interface_id))
            for interface_id, queue in enumerate(queues)
        ]
        
        # Start generation tasks
        generation_tasks = []
        for volume in event['volume']:
            count = int(volume.get('count', 0))
            total_events += count  # Track total events
            distribution = volume['distribution']
            
            # Split generation across more workers
            chunk_size = count // (self.num_workers * 2)
            for worker_id in range(self.num_workers * 2):
                task = asyncio.create_task(
                    self.generate_events_worker(
                        chunk_size, 
                        distribution, 
                        start_time, 
                        end_time,
                        event['event_types'],
                        source,
                        queues[worker_id % self.network_interfaces]
                    )
                )
                generation_tasks.append(task)
        
        # Wait for generation to complete
        await asyncio.gather(*generation_tasks)
        
        # Signal upload workers to finish
        for queue in queues:
            await queue.put(None)
        
        # Wait for uploads to complete
        await asyncio.gather(*upload_tasks)

        # Enhanced timing logs
        gen_time = time.time() - gen_start
        logging.debug(f"Generation time: {gen_time:.2f}s")
        logging.debug(f"Total events: {total_events}")
        logging.debug(f"Events per second: {total_events/gen_time:.2f}")
        for i in range(self.network_interfaces):
            if upload_counts[i] > 0:
                rate = upload_counts[i] / upload_times[i] if upload_times[i] > 0 else 0
                logging.debug(f"Interface {i}: {upload_counts[i]} events in {upload_times[i]:.2f}s ({rate:.2f} events/s)")
        logging.debug(f"Queue depths: {[q.qsize() for q in queues]}")

    async def generate_events_worker(self, count, distribution, start_time, end_time, 
                                   event_types, source, queue):
        events = []
        for _ in range(count):
            if len(events) >= self.batch_size:
                await queue.put(events)
                events = []
                
            event = self.create_event(
                source_name=source,
                event_type=random.choice(event_types)['type'],
                timestamp=self.random_time_between(start_time, end_time)
            )
            events.append(event)
            
        if events:
            await queue.put(events)

    async def upload_worker(self, queue, source, interface_id):
        # Configure TCP connector with interface-specific settings
        connector = aiohttp.TCPConnector(
            limit=self.connection_pool_size // self.network_interfaces,
            force_close=True,  # Prevent connection pooling issues
            enable_cleanup_closed=True,
            ssl=False  # Axiom uses HTTPS but we'll handle SSL at higher level
        )
        
        async with aiohttp.ClientSession(
            connector=connector,
            json_serialize=lambda x: standard_json.dumps(x, cls=DateTimeEncoder),
            timeout=aiohttp.ClientTimeout(total=300)  # Increased timeout for larger batches
        ) as session:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                
                async with self.upload_semaphore:  # Control concurrent uploads
                    await self.upload_chunk_with_retry(session, source, chunk, interface_id)
                queue.task_done()

    async def upload_chunk_with_retry(self, session, dataset, chunk, interface_id):
        """Retry logic for uploading chunks to Axiom"""
        api_url = f"https://api.axiom.co/v1/datasets/{dataset}/ingest"
        
        # Pre-process events before upload
        processed_chunk = [{
            k: v.isoformat() if isinstance(v, datetime) else v 
            for k, v in event.items()
        } for event in chunk]
        
        headers = {
            "Authorization": f"Bearer {AXIOM_API_TOKEN}",
            "Content-Type": "application/json",
            "X-Interface-ID": str(interface_id)
        }

        for attempt in range(self.retry_attempts):
            try:
                async with session.post(api_url, headers=headers, json=processed_chunk) as response:
                    if response.status == 200:
                        self.total_events_sent += len(chunk)
                        logging.debug(f"Interface {interface_id}: Sent {len(chunk)} events to {dataset}")
                        return
                    elif response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', self.retry_delay * (2 ** attempt)))
                        await asyncio.sleep(retry_after)
                    else:
                        error_text = await response.text()
                        logging.warning(f"Interface {interface_id}: Attempt {attempt + 1} failed: {error_text}")
                        await asyncio.sleep(self.retry_delay * (2 ** attempt))
            except Exception as e:
                logging.warning(f"Interface {interface_id}: Attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise

    def chunk_list(self, lst, n):
        """Yield successive n-sized chunks from lst using numpy."""
        arr = np.array(lst)
        for i in range(0, len(arr), n):
            yield arr[i:i + n].tolist()

    async def send_events_to_postgres(self, events):
            self.clean_event_batch(events)  # Remove fields we do not want to publish in the event, e.g. dataset
            with PG_CONNECTION.cursor() as cur:
                for event in events:
                    cur.execute("""
                        INSERT INTO events (source, timestamp, message, event_type, attributes)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        event['source'],
                        event['_time'],
                        event['message'],
                        standard_json.dumps(event['attributes']),
                    ))
            PG_CONNECTION.commit()
            self.total_events_sent += len(events)  # Increment counter
            logging.debug(f"Successfully sent {len(events)} events to PostgreSQL.")
            events.clear()

    async def send_events_to_file(self, events):
            self.clean_event_batch(events)
            
            if self.output_file_path == '-' or self.output_file_path == sys.stdout:
                # Write directly to stdout
                for event in events:
                    print(standard_json.dumps(event))
            else:
                # Write to specified file
                async with aiofiles.open(self.output_file_path, 'a') as f:
                    for event in events:
                        await f.write(standard_json.dumps(event) + '\n')
            
            self.total_events_sent += len(events)
            if self.output_file_path not in ['-', sys.stdout]:
                logging.debug(f"Successfully wrote {len(events)} events to {self.output_file_path}")
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
        # logging.debug(f"Client IP generation took {end_time - start_time:.6f} seconds")
        return private_ip

    def generate_response_time(self):
        """Generate a random response time between the configured min and max."""
        return random.randint(self.response_time_min, self.response_time_max)

    def clean_event_batch(self, events):
        """Clean a batch of events by removing source_type and converting timestamps."""
        for event in events:
            event.pop('source_type', None)
            event.pop('event_type', None)
            event.pop('dataset', None)
                    
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
            'attributes': details,
            'message': formatted_message
        }

    def format_message(self, message, details):
        """Format message template with event details."""
        formatted_details = {}
        for key, value in details.items():
            if isinstance(value, str) and ' ' in value:
                formatted_details[key] = f'"{value}"'
            else:
                formatted_details[key] = value
        return message.format(**formatted_details)

    def chain_events(self, event, events):
        """Process dependent events based on trigger event."""
        event_key = (event['source_type'], event['attributes']['request_id'])
        if event_key in self.processed_events:
            return
        
        self.processed_events.add(event_key)
        
        # Find and process all dependencies for this event
        for dependency in self.dependencies:
            if (dependency['trigger']['source'] == event['source_type'] and
                dependency['trigger']['event_type'] == event['event_type']):
                
                # Check percentage before generating dependent event
                percentage = dependency['action'].get('percentage', 100)
                if random.random() * 100 <= percentage:
                    dependent_event = self.create_event(
                        source_name=dependency['action']['source'],
                        event_type=dependency['action']['event_type'],
                        parent_event=event
                    )
                    events.append(dependent_event)
                    
                    # Recursively process dependencies
                    self.chain_events(dependent_event, events)

    async def send_events_to_axiom(self, events):
        """Send events to Axiom, grouped by dataset."""
        events_by_source = {}
        for event in events:
            source_type = event.get('source_type')
            if source_type not in events_by_source:
                events_by_source[source_type] = []
            events_by_source[source_type].append(event)

        # Track which interface to use next
        interface_id = 0
        logging.debug(f"Starting with interface_id {interface_id}, total interfaces: {self.network_interfaces}")

        # Process each source's events separately
        for source_type, source_events in events_by_source.items():
            source_config = self.config['sources'].get(source_type, {})
            dataset = source_config['dataset']
            
            # Convert datetime objects to ISO format
            for event in source_events:
                if '_time' in event and isinstance(event['_time'], datetime):
                    event['_time'] = event['_time'].isoformat()

            # Process events in chunks, distributing across interfaces
            for chunk in self.chunk_list(source_events, self.batch_size):
                self.clean_event_batch(chunk)
                api_url = f"https://api.axiom.co/v1/datasets/{dataset}/ingest"
                logging.debug(f"Sending {len(chunk)} events to dataset {dataset} using interface {interface_id}")
                
                connector = aiohttp.TCPConnector(
                    limit=self.connection_pool_size,
                    force_close=True,
                    enable_cleanup_closed=True
                )
                
                async with aiohttp.ClientSession(
                    connector=connector,
                    json_serialize=lambda x: standard_json.dumps(x, cls=DateTimeEncoder)
                ) as session:
                    await self.upload_chunk_with_retry(session, dataset, chunk, interface_id)
                
                # Round-robin through interfaces
                interface_id = (interface_id + 1) % self.network_interfaces
                logging.debug(f"Next interface_id will be {interface_id}")

        events.clear()

class DateTimeEncoder(standard_json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

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

