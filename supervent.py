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

        generator.generate_events(start_time, end_time)
        print("Event generation completed.")
    except Exception as e:
        print("An error occurred:", e)

class EventGenerator:
    def __init__(self, event_frequencies, config):
        self.event_frequencies = event_frequencies
        self.config = config
        self.dependencies = config.get('dependencies', [])
        self.processed_events = set()  # Track processed events to prevent loops

        # Set up signal handling
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle the signal to exit gracefully."""
        print("Exiting gracefully...")
        sys.exit(0)  # Exit the program with a success status

    def generate_events(self, start_time, end_time):
        print("Starting event generation...")
        for source, event in self.config['sources'].items():
            print(f"Generating events for source: {source}")
            self.generate_source_events(source, event)
        print("Event generation completed.")

    def generate_source_events(self, source, event):
        print(f"Generating source events for: {source}")
        parameters = event['volume']
        event_types = event['event_types']
        source_description = event['description']
        print(f"Parameters for {source}: {parameters}")
        for volume in parameters:
            count = volume.get('count', 0)
            distribution = volume['distribution']
            time_period = volume['time_period']
            print(f"Generating {count} events with {distribution} distribution for time period: {time_period}")
            
            # Debug statement before processing time_period
            print(f"About to process time_period: {time_period} (type: {type(time_period)})")  # Debug statement

            # If the time period is a single timestamp, generate events around that time
            if isinstance(time_period, str):
                print(f"Time period is a string: {time_period}")  # Debug statement
                try:
                    start_time = datetime.fromisoformat(time_period.replace('Z', '+00:00'))
                    end_time = start_time  # Same for both if it's a single timestamp
                    print(f"Parsed start_time: {start_time}, end_time: {end_time}")  # Debug statement
                    self.create_events(count, distribution, {'start': start_time, 'end': end_time}, source_description, event_types, source)
                except Exception as e:
                    print(f"Error parsing time period: {e}")  # Debug statement for error handling
            else:
                print(f"Time period is not a string, it is: {type(time_period)}")  # Debug statement
                self.create_events(count, distribution, time_period, source_description, event_types, source)

    def create_events(self, count, distribution, time_period, source_description, event_types, source):
        # Create a list to hold events before sending to Axiom
        events = []  
        start_time, end_time = self.parse_time_period(time_period)  # Parse the time period

        # Calculate the mean and standard deviation for normal distribution
        mean_time = start_time + (end_time - start_time) / 2  # Mean is the midpoint
        std_dev = (end_time - start_time) / 6  # Example: spread events over the range

        for _ in range(count):
            # Generate the event based on the specified distribution
            if distribution == 'normal':
                # Generate a fake timestamp based on a normal distribution
                fake_timestamp = self.generate_normal_time(mean_time, std_dev)
            elif distribution == 'random':
                # Generate a fake timestamp uniformly between start_time and end_time
                fake_timestamp = self.random_time_between(start_time, end_time)
            else:
                raise ValueError(f"Unsupported distribution type: {distribution}")

            # Choose a random event type
            event_type = random.choice(event_types)
            message = event_type['format']
            event_type_name = event_type['type']
            details = event_type.get('details', {})

            # Format the timestamp based on the source type
            if source == "web_server":
                formatted_timestamp = fake_timestamp.strftime("%d/%b/%Y:%H:%M:%S +0000")
            else:
                formatted_timestamp = fake_timestamp.isoformat() + "Z"

            # Update the details with the formatted timestamp
            details['timestamp'] = formatted_timestamp

            # Format the message with the details
            formatted_message = message.format(**details)

            # Generate the event
            event = {
                'source': source,  # Use the original source name
                '_time': fake_timestamp,  # Insert the generated timestamp
                'message': formatted_message,  # Include the formatted message
                'event_type': event_type_name,  # Include the event type name
                'details': details  # Include the details
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
            'message': action['event_type'],
            'event_type': action['event_type'],  # Ensure the event_type field is included
            'details': event.get('details', {}).copy()  # Copy details to avoid modifying the original event
        }
        return dependent_event

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
        """Generate a random datetime based on a normal distribution."""
        # Generate a random time in seconds based on normal distribution
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

if __name__ == "__main__":
    main()
