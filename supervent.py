import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

# Load environment variables from .env file
load_dotenv()
AXIOM_API_TOKEN = os.getenv('AXIOM_API_TOKEN')
AXIOM_API_URL = "https://api.axiom.co/v1/datasets/supervent/ingest"  # Replace with your dataset name

# Load configurations
def load_config(file_path):
    with open(file_path) as f:
        return json.load(f)

def merge_configs(base_config, overlay_config):
    # Merge logic for health checks and traffic patterns
    for key, value in overlay_config.items():
        if key in base_config:
            # Override existing values
            base_config[key].update(value)
        else:
            # Add new keys from overlay
            base_config[key] = value
    return base_config

# Load the default configuration
normal_traffic_config = load_config('config/scenarios/normal_traffic.json')

# Load overlay configurations specified by the user
overlay_files = ['config/scenarios/database_problem.json', 'config/scenarios/surge_traffic.json']
for overlay_file in overlay_files:
    overlay_config = load_config(overlay_file)
    normal_traffic_config = merge_configs(normal_traffic_config, overlay_config)

# Proceed with event generation using the merged configuration

class EventGenerator:
    def __init__(self, sources_config, event_frequencies, scenario_config):
        self.sources = sources_config['sources']
        self.event_frequencies = event_frequencies
        self.scenario = scenario_config['scenario']
        self.start_time = datetime.fromisoformat(self.scenario['time_period']['start_time'].replace("Z", "+00:00"))
        self.end_time = datetime.fromisoformat(self.scenario['time_period']['end_time'].replace("Z", "+00:00"))
        self.event_batch = []  # List to hold events for batching

    def generate_events(self):
        current_time = self.start_time
        while current_time <= self.end_time:
            for source_name, source in self.sources.items():
                self.generate_source_events(source_name, source, current_time)
            current_time += timedelta(minutes=1)  # Increment time for the next event

        # Send any remaining events in the batch after the loop
        if self.event_batch:
            self.send_events_to_axiom(self.event_batch)

    def generate_source_events(self, source_name, source, current_time):
        for event_type, details in source['event_types'].items():
            frequency_str = self.get_event_frequency(source_name, event_type)
            frequency_minutes = self.parse_frequency(frequency_str)
            if frequency_minutes and (current_time.minute % frequency_minutes) == 0:  # Check if it's time to generate this event
                
                # Create the event using only the attributes from the configuration
                event = {
                    "_time": current_time.isoformat() + "Z",  # Add the artificial timestamp
                    "attributes": {}
                }

                # Populate attributes based on the event format
                for attr, attr_type in source['event_format']['attributes'].items():
                    if attr in source['allowed_values']:
                        event["attributes"][attr] = random.choice(source['allowed_values'][attr])
                    else:
                        if "integer" in attr_type:
                            event["attributes"][attr] = random.randint(1, 1000)  # Example for integers
                        elif "string" in attr_type:
                            event["attributes"][attr] = f"example_{random.randint(1, 100)}"  # Example for strings

                # Ensure all attributes are included based on the configuration
                for attr in source['event_format']['attributes']:
                    if attr not in event["attributes"]:
                        if attr in source['allowed_values']:
                            event["attributes"][attr] = random.choice(source['allowed_values'][attr])

                self.event_batch.append(event)  # Add event to the batch
                print(f"Sending event to Axiom: {json.dumps(event)}")  # Log to console

                # Check for follow-up events
                if 'followed_by' in details:
                    for follow_up_event in details['followed_by']:
                        self.generate_follow_up_event(source_name, follow_up_event, current_time)

                # Send the batch if it reaches 200 events
                if len(self.event_batch) >= 200:
                    self.send_events_to_axiom(self.event_batch)

    def generate_follow_up_event(self, source_name, event_type, current_time):
        source = self.sources[source_name]
        frequency = self.get_event_frequency(source_name, event_type)
        if frequency and (current_time.minute % frequency) == 0:
            # Create the follow-up event
            follow_up_event = {
                "attributes": {}
            }

            # Populate attributes based on the event format
            for attr, attr_type in source['event_format']['attributes'].items():
                if attr in source['allowed_values']:
                    follow_up_event["attributes"][attr] = random.choice(source['allowed_values'][attr])
                else:
                    if "integer" in attr_type:
                        follow_up_event["attributes"][attr] = random.randint(1, 1000)  # Example for integers
                    elif "string" in attr_type:
                        follow_up_event["attributes"][attr] = f"example_{random.randint(1, 100)}"  # Example for strings

            self.event_batch.append(follow_up_event)  # Add follow-up event to the batch
            print(f"Sending follow-up event to Axiom: {json.dumps(follow_up_event)}")  # Log to console

    def get_event_frequency(self, source_name, event_type):
        # Retrieve the frequency for the specified event type from the event_frequencies config
        if source_name in self.event_frequencies['normal_traffic']:
            if event_type in self.event_frequencies['normal_traffic'][source_name]:
                frequency_str = self.event_frequencies['normal_traffic'][source_name][event_type]['frequency']
                print(f"Retrieved frequency for {event_type} in {source_name}: {frequency_str}")  # Debugging statement
                return frequency_str
        print(f"No frequency found for {event_type} in {source_name}")  # Debugging statement
        return None

    def send_events_to_axiom(self, events):
        headers = {
            "Authorization": f"Bearer {AXIOM_API_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(AXIOM_API_URL, headers=headers, json=events)
        if response.status_code == 200:
            print(f"Successfully sent {len(events)} events to Axiom.")
        else:
            print(f"Failed to send events to Axiom: {response.status_code} - {response.text}")
        self.event_batch.clear()  # Clear the batch after sending

    def parse_frequency(self, frequency_str):
        if frequency_str is None:
            print("Frequency string is None")  # Debugging statement
            return None
        # Parse the frequency string to get the integer value in minutes
        if "minute" in frequency_str:
            return int(frequency_str.split()[1])  # Extract the number of minutes
        elif "second" in frequency_str:
            return int(frequency_str.split()[1]) / 60  # Convert seconds to minutes
        elif "hour" in frequency_str:
            return int(frequency_str.split()[1]) * 60  # Convert hours to minutes
        return None

def main():
    # Load the main configuration and event frequencies
    sources_config = load_config('config/sources/3tier.json')
    event_frequencies = load_config('config/scenarios/event_frequencies.json')
    scenario_config = load_config('config/scenarios/normal_traffic.json')

    # Ensure that sources_config is defined before this line
    generator = EventGenerator(sources_config, event_frequencies, scenario_config)
    generator.generate_events()

if __name__ == "__main__":
    main()
