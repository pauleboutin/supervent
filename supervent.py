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

        # Set up signal handling
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle the signal to exit gracefully."""
        print("Exiting gracefully...")
        sys.exit(0)  # Exit the program with a success status

    def generate_events(self, start_time, end_time):
        print("Starting event generation...")
        for event in self.config['events']:
            event_type = event['type']
            print(f"Generating events for type: {event_type}")
            self.generate_source_events(event_type)
        print("Event generation completed.")

    def generate_source_events(self, event_type):
        print(f"Generating source events for: {event_type}")
        for event in self.config['events']:
            if event['type'] == event_type:
                parameters = event['parameters']
                print(f"Parameters for {event_type}: {parameters}")
                for volume in parameters['volume']:
                    count = volume['count']
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
                            self.create_events(count, distribution, {'start': start_time, 'end': end_time}, event_type)
                        except Exception as e:
                            print(f"Error parsing time period: {e}")  # Debug statement for error handling
                    else:
                        print(f"Time period is not a string, it is: {type(time_period)}")  # Debug statement
                        self.create_events(count, distribution, time_period, event_type)

    def create_events(self, count, distribution, time_period, event_type):
        # Create a list to hold events before sending to Axiom
        events = []  
        start_time, end_time = self.parse_time_period(time_period)  # Parse the time period

        # Calculate the mean and standard deviation for normal distribution
        mean_time = start_time + (end_time - start_time) / 2  # Mean is the midpoint
        std_dev = (end_time - start_time) / 6  # Example: spread events over the range

        for _ in range(count):
            # Generate the event based on the specified distribution
            if distribution == 'normal':
                # Generate a random timestamp based on a normal distribution
                random_timestamp = self.generate_normal_time(mean_time, std_dev)
            elif distribution == 'random':
                # Generate a random timestamp uniformly between start_time and end_time
                random_timestamp = self.random_time_between(start_time, end_time)
            else:
                raise ValueError(f"Unsupported distribution type: {distribution}")

            # Generate the event
            event = {
                'event_type': event_type,  # Use the event_type parameter
                '_time': random_timestamp,  # Insert the generated timestamp
                'details': f'Generated {event_type} event based on {distribution} distribution.'
            }
            events.append(event)

            # Send events in batches of 200
            if len(events) >= 200:
                self.send_events_to_axiom(events)

        # Send any remaining events that didn't make a full batch
        if events:
            self.send_events_to_axiom(events)

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
        random_timestamp = mean_timestamp + random_offset  # Add the offset to the mean timestamp
        return datetime.fromtimestamp(random_timestamp)  # Convert back to datetime

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
        random_time = mean + timedelta(seconds=random_seconds)

        # Ensure the generated time is within the start and end bounds
        return random_time

    def random_time_between(self, start, end):
        """Generate a random datetime between two datetime objects."""
        delta = end - start
        random_seconds = random.randint(0, int(delta.total_seconds()))
        return start + timedelta(seconds=random_seconds)

if __name__ == "__main__":
    main()
