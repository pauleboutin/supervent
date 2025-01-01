import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import random
import yaml
import numpy as np  # You may need to install this library if you use it for distributions
import signal
import sys
import uuid  # Importing uuid to generate unique IDs
import ipaddress
import time  # Import time for measuring execution time

# Load environment variables from .env file
load_dotenv()
AXIOM_API_TOKEN = os.getenv('AXIOM_API_TOKEN')
AXIOM_API_URL = "https://api.axiom.co/v1/datasets/supervent/ingest"  # Replace with your dataset name

# Load configurations
def load_config(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def main():
    try:
        print("Loading configuration...")
        config = load_config('config/config.yaml')
        print("Configuration loaded successfully.")

        start_time = datetime.fromisoformat(config['start_time'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(config['end_time'].replace('Z', '+00:00'))
        print(f"Start time: {start_time}, End time: {end_time}")

        event_frequencies = config.get('event_frequencies', {})
        print("Event frequencies loaded:", event_frequencies)

        generator = EventGenerator(event_frequencies, config)
        print("Event generator created.")

        # Initialize event counter as an integer
        event_count = 0  # This will count the total number of events generated
        start_generation_time = time.time()  # Start timing

        # Generate events
        generator.generate_events(start_time, end_time)

        # Update event_count based on the number of unique processed events
        event_count += len(generator.processed_events)  # Count unique events

        # Calculate total time taken
        total_time = time.time() - start_generation_time  # This should be a float
        print(f"Generated {event_count} events in {total_time:.2f} seconds.")

    except Exception as e:
        print("An error occurred:", e)
        # Print the number of events generated before the error
        print(f"Generated {event_count} events before error.")

class EventGenerator:
    def __init__(self, event_frequencies, config):
        self.event_frequencies = event_frequencies
        self.config = config
        
        # Load acceptable values from config
        self.users = self.config['acceptable_values']['users']
        self.methods = self.config['acceptable_values']['methods']
        self.paths = self.config['acceptable_values']['paths']
        self.referers = self.config['acceptable_values']['referers']
        self.user_agents = self.config['acceptable_values']['user_agents']
        self.protocols = self.config['acceptable_values']['protocols']
        self.statuses = self.config['acceptable_values']['statuses']
        
        # Load client IP ranges and response time settings
        self.client_ip_ranges = self.config['client_ip_ranges']
        self.response_time_min = self.config['response_time']['min']
        self.response_time_max = self.config['response_time']['max']

        self.dependencies = config.get('dependencies', [])
        self.processed_events = set()  # Initialize processed events counter
        self.start_generation_time = None  # Initialize start time

        # Set up signal handling
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle the signal to exit gracefully."""
        total_time = time.time() - self.start_generation_time  # Calculate total time
        # Use a simple print statement to avoid reentrant calls
        print(f"\nExiting gracefully... Generated {len(self.processed_events)} unique events in {total_time:.2f} seconds.")
        sys.exit(0)  # Exit the program with a success status

    def generate_events(self, start_time, end_time):
        print("Starting event generation...")
        self.start_generation_time = time.time()  # Set start time
        for source, event in self.config['sources'].items():
            print(f"Generating events for source: {source}")
            self.generate_source_events(source, event, start_time, end_time)
        print("Event generation completed.")

    def generate_source_events(self, source, event, start_time, end_time):
        print(f"Generating source events for: {source}")
        parameters = event['volume']
        event_types = event['event_types']
        source_description = event['description']
        print(f"Parameters for {source}: {parameters}")

        for volume in parameters:
            pattern = volume.get('pattern')
            count = int(volume.get('count', 0))  # Ensure count is an integer
            distribution = volume['distribution']
            details = volume['details']
            print(f"Generating {count} events with {distribution} distribution for pattern: {pattern}")

            # Check if count is an integer
            if not isinstance(count, int):
                raise ValueError(f"Expected count to be an integer, got {type(count)} instead.")

            # Generate events based on the pattern
            if pattern:
                self.generate_pattern_events(pattern, count, distribution, start_time, end_time, source_description, event_types, source)
            else:
                time_period = volume['time_period']
                self.create_events(count, distribution, time_period, source_description, event_types, source)

    def generate_pattern_events(self, pattern, count, distribution, start_time, end_time, source_description, event_types, source):
        if pattern == "weekday":
            self.generate_weekday_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "weekend":
            self.generate_weekend_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "24/7":
            self.generate_24_7_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "sine_wave":
            self.generate_sine_wave_events(count, distribution, start_time, end_time, source_description, event_types, source)
        elif pattern == "linear_increase":
            self.generate_linear_increase_events(count, distribution, start_time, end_time, source_description, event_types, source)
        else:
            raise ValueError(f"Unsupported pattern type: {pattern}")

    def generate_weekday_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        # Generate events for weekdays (Monday to Friday)
        current_time = start_time
        while current_time < end_time:
            if current_time.weekday() < 5:  # Monday to Friday
                self.create_events(count // 5, distribution, {'start': current_time.isoformat(), 'end': (current_time + timedelta(days=1)).isoformat()}, source_description, event_types, source)
            current_time += timedelta(days=1)

    def generate_weekend_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        # Generate events for weekends (Saturday and Sunday)
        current_time = start_time
        while current_time < end_time:
            if current_time.weekday() >= 5:  # Saturday and Sunday
                self.create_events(count // 2, distribution, {'start': current_time.isoformat(), 'end': (current_time + timedelta(days=1)).isoformat()}, source_description, event_types, source)
            current_time += timedelta(days=1)

    def generate_24_7_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        # Generate events for 24/7
        total_days = (end_time - start_time).days + 1
        self.create_events(count // total_days, distribution, {'start': start_time, 'end': end_time}, source_description, event_types, source)

    def generate_sine_wave_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        # Generate events based on a sine wave pattern
        total_seconds = (end_time - start_time).total_seconds()
        for i in range(count):
            t = i / count * total_seconds
            amplitude = (1 + math.sin(2 * math.pi * t / total_seconds)) / 2
            event_time = start_time + timedelta(seconds=t)
            self.create_events(int(amplitude * count), distribution, {'start': event_time, 'end': event_time}, source_description, event_types, source)

    def generate_linear_increase_events(self, count, distribution, start_time, end_time, source_description, event_types, source):
        # Generate events based on a linear increase pattern
        total_seconds = (end_time - start_time).total_seconds()
        for i in range(count):
            t = i / count * total_seconds
            event_time = start_time + timedelta(seconds=t)
            self.create_events(i + 1, distribution, {'start': event_time, 'end': event_time}, source_description, event_types, source)

    def create_events(self, count, distribution, time_period, source_description, event_types, source):
        # Load acceptable values from config
        paths = self.config['acceptable_values']['paths']
        path_status_mapping = self.config['path_status_mapping']  # Load path status mapping from config

        # Create a list to hold events before sending to Axiom
        events = []  
        start_time, end_time = self.parse_time_period(time_period)  # Parse the time period

        # Calculate the mean and standard deviation for gaussian distribution
        mean_time = start_time + (end_time - start_time) / 2  # Mean is the midpoint
        std_dev = (end_time - start_time) / 6  # Example: spread events over the range

        for _ in range(count):
            # Generate a unique request ID
            request_id = str(uuid.uuid4())

            # Randomly select a path from the acceptable paths
            selected_path = random.choice(paths)

            # Determine the status code based on the selected path
            status_code = path_status_mapping.get(selected_path, 200)  # Default to 200 if not found

            # Randomly select other values as before
            selected_user = random.choice(self.users)
            selected_method = random.choice(self.methods)
            selected_referer = random.choice(self.referers)
            selected_user_agent = random.choice(self.user_agents)
            selected_protocol = random.choice(self.protocols)
            selected_status = random.choice(self.statuses)

            # Generate the event based on the specified distribution
            if distribution == 'gaussian':
                fake_timestamp = self.generate_normal_time(mean_time, std_dev)
            elif distribution == 'random':
                fake_timestamp = self.random_time_between(start_time, end_time)
            else:
                raise ValueError(f"Unsupported distribution type: {distribution}")

            # Choose a random event type
            event_type = random.choice(event_types)
            
            # Check if create_from_scratch is true
            if not event_type.get('create_from_scratch', False):
                continue  # Skip event creation if create_from_scratch is not true

            message = event_type['format']
            event_type_name = event_type['type']
            details = event_type.get('details', {})

            # Format the timestamp based on the source type
            if source == "web_server":
                formatted_timestamp = fake_timestamp.strftime("%d/%b/%Y:%H:%M:%S +0000")
            else:
                formatted_timestamp = fake_timestamp.isoformat() + "Z"

            # Update the details with the formatted timestamp and request_id
            details['timestamp'] = formatted_timestamp
            details['request_id'] = request_id  # Include the request_id in the details

            # Ensure consistency in event details
            details['path'] = details.get('path', '')  # Ensure path is included
            details['method'] = details.get('method', '')  # Ensure method is included
            details['client_ip'] = details.get('client_ip', '')  # Ensure client_ip is included
            details['user'] = details.get('user', '')  # Ensure user is included

            # Use the description for the source in the message
            source_description = self.config['sources'][source]['description']  # Get the description
            details['source'] = source_description  # Update details with the description

            # Format the message with the details
            formatted_message = self.format_message(message, details)
            formatted_message += f" (request_id: {request_id})"  # Append the request_id to the message

            # Reintroduce client IP generation
            client_ip = self.generate_client_ip()  # Keep client IP generation
            response_time = self.generate_response_time()  # Uncommented for testing

            # Update details with selected values
            details['user'] = selected_user
            details['method'] = selected_method
            details['path'] = selected_path
            details['referer'] = selected_referer
            details['user_agent'] = selected_user_agent
            details['protocol'] = selected_protocol
            details['status'] = selected_status
            details['client_ip'] = client_ip  # Set the generated client IP
            details['response_time'] = response_time  # Set the generated response time

            # Generate the event
            event = {
                'source': source,
                '_time': fake_timestamp,
                'message': formatted_message,
                'event_type': event_type_name,
                'attributes': details
            }
            events.append(event)

            # Recursively check for dependencies
            self.chain_events(event, events)

            # Send events in batches of 200
            if len(events) >= 200:
                self.send_events_to_axiom(events)

        # Send any remaining events that didn't make a full batch
        if events:
            self.send_events_to_axiom(events)

    def chain_events(self, event, events):
        """Chain events based on the dependencies specified in the configuration."""
        event_key = (event['source'], event['_time'], event['event_type'])
        if event_key in self.processed_events:
            return  # Skip already processed events to prevent loops

        self.processed_events.add(event_key)  # Mark the event as processed

        print(f"Checking dependencies for event: {event}")  # Debug statement
        for dependency in self.dependencies:
            trigger = dependency['trigger']
            action = dependency['action']
            print(f"Checking dependency: {dependency}")  # Debug statement
            print(f"Comparing event source: {event['source']} with trigger source: {trigger['source']}")  # Debug statement
            print(f"Comparing event type: {event['event_type']} with trigger type: {trigger['event_type']}")  # Debug statement
            if event['source'] == trigger['source'] and event['event_type'] == trigger['event_type']:
                print(f"Dependent event found for trigger: {trigger}")  # Debug statement

                if 'message' in trigger:
                    print(f"Comparing event message: {event['message']} with trigger message: {trigger['message']}")  # Debug statement
                    if event['message'] != trigger['message']:
                        print(f"Message does not match for trigger: {trigger}")  # Debug statement
                        continue
                # Create the dependent event
                dependent_event = self.create_event(action, event)
                print(f"Generating dependent event: {dependent_event}")  # Debug statement
                events.append(dependent_event)
                print(f"Dependent event appended: {dependent_event}")  # Debug statement

                # Recursively check for dependencies of the dependent event
                self.chain_events(dependent_event, events)
            else:
                print(f"No match for dependency: {dependency}")  # Debug statement
                print(f"Event source: {event['source']} != Trigger source: {trigger['source']} or Event type: {event['event_type']} != Trigger type: {trigger['event_type']}")  # Debug statement

    def create_event(self, action, event):
        """Create a dependent event based on the action and the original event."""
        dependent_event = {
            'source': action['source'],
            '_time': event['_time'],
            'message': self.format_message(action['event_type'], event.get('attributes', {}).copy()),  # Format the message with attributes
            'event_type': action['event_type'],  # Ensure the event_type field is included
            'attributes': event.get('attributes', {}).copy()  # Copy attributes to avoid modifying the original event
        }
        return dependent_event

    def format_message(self, message, details):
        """Format the message with the details, removing quotes around parameter names and values unless there is a space."""
        formatted_details = {}
        for key, value in details.items():
            if isinstance(value, str) and ' ' in value:
                formatted_details[key] = f'"{value}"'
            else:
                formatted_details[key] = value
        return message.format(**formatted_details)

    def parse_time_period(self, time_period):
        print(f"Received time period for parsing: {time_period}")  # Debug statement
        if isinstance(time_period, dict):
            # Expecting a dictionary with 'start' and 'end' keys
            start_time = datetime.fromisoformat(time_period['start'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(time_period['end'].replace('Z', '+00:00'))
        else:
            raise ValueError("Invalid time period format")

        print(f"Parsed time period: start_time={start_time}, end_time={end_time}")  # Debug statement
        return start_time, end_time

    def random_time(self, start_time, end_time):
        # Generate a random time between start_time and end_time
        return start_time + (end_time - start_time) * random.random()

    def normal_random_time(self, mean, std_dev):
        # Generate a time based on a normal distribution
        # mean is a datetime object, std_dev is in seconds
        mean_timestamp = mean.timestamp()  # Convert to timestamp
        random_offset = np.random.normal(0, std_dev)  # Generate a random offset
        fake_timestamp = mean_timestamp + random_offset  # Add the offset to the mean timestamp
        return datetime.fromtimestamp(fake_timestamp)  # Convert back to datetime

    def store_events(self, events):
        for event in events:
            print(f"Storing event: {event}")  # Debug statement to confirm storage
        # Here you would typically send the events to your data store

    def get_event_frequency(self, source_name, event_type):
        # Retrieve the frequency for the specified event type from the event_frequencies config
        if source_name in self.event_frequencies['normal_traffic']:
            if event_type in self.event_frequencies['normal_traffic'][source_name]:
                frequency_str = self.event_frequencies['normal_traffic'][source_name][event_type]['frequency']
                # Parse the frequency string to get the integer value
                if "minute" in frequency_str:
                    return int(frequency_str.split()[1])  # Extract the number of minutes
                elif "second" in frequency_str:
                    return int(frequency_str.split()[1]) / 60  # Convert seconds to minutes
                elif "hour" in frequency_str:
                    return int(frequency_str.split()[1]) * 60  # Convert hours to minutes
        return None

    def send_events_to_axiom(self, events):
        # Convert datetime objects to ISO 8601 strings
        for event in events:
            if '_time' in event and isinstance(event['_time'], datetime):
                event['_time'] = event['_time'].isoformat()  # Convert to string

        # Now send the events to Axiom
        response = requests.post(AXIOM_API_URL, headers={
            "Authorization": f"Bearer {AXIOM_API_TOKEN}",
            "Content-Type": "application/json"
        }, json=events)
        
        if response.status_code != 200:
            print(f"Failed to send events to Axiom: {response.text}")
        else:
            print(f"Successfully sent {len(events)} events to Axiom.")

        # Clear the events list after sending
        events.clear()  # This will zero out the events queue

    def simulate_error_rate(self, service, error_rate):
        # Logic to simulate error rates for health checks
        if error_rate == "high":
            # Implement logic to increase the likelihood of errors during health checks
            pass  # Replace with actual implementation

    def generate_normal_time(self, mean, std_dev):
        """Generate a random datetime based on a gaussian distribution."""
        # Generate a random time in seconds based on gaussian distribution
        random_seconds = int(np.random.normal(0, std_dev.total_seconds()))
        
        # Create a new datetime by adding the random seconds as a timedelta
        fake_timestamp = mean + timedelta(seconds=random_seconds)

        # Ensure the generated time is within the start and end bounds
        return fake_timestamp

    def random_time_between(self, start, end):
        """Generate a random datetime between two datetime objects."""
        delta = end - start
        random_seconds = random.randint(0, int(delta.total_seconds()))
        return start + timedelta(seconds=random_seconds)

    def generate_client_ip(self):
        """Generate a random client IP address from the configured private ranges."""
        start_time = time.time()  # Start timing
        private_ip = random.choice([
            f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}",
            f"172.{random.randint(16, 31)}.{random.randint(0, 255)}.{random.randint(0, 255)}",
            f"192.168.{random.randint(0, 255)}.{random.randint(0, 255)}"
        ])
        end_time = time.time()  # End timing
        print(f"Client IP generation took {end_time - start_time:.6f} seconds")  # Print the time taken
        return private_ip

    def generate_response_time(self):
        """Generate a random response time between the configured min and max."""
        return random.randint(self.response_time_min, self.response_time_max)  # Response time in milliseconds

if __name__ == "__main__":
    main()
