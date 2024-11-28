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

class EventGenerator:
    def __init__(self, sources_config, scenario_config):
        self.sources = sources_config['sources']
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
            frequency_minutes = self.get_frequency_in_minutes(details['frequency'])
            if (current_time.minute % frequency_minutes) == 0:  # Check if it's time to generate this event
                
                # Create the event using the event format from the configuration
                event = {
                    "timestamp": current_time.isoformat() + "Z",
                    "severity_text": "INFO",  # Default severity text
                    "severity_number": 9,      # Default severity number
                    "attributes": {
                        "event_type": event_type,
                    },
                    "body": f"{event_type} event generated"
                }

                # Populate attributes based on the event format
                for attr, attr_type in source['event_format']['attributes'].items():
                    if attr in source['allowed_values']:
                        # If there are allowed values, choose one randomly
                        event["attributes"][attr] = random.choice(source['allowed_values'][attr])
                    else:
                        # Generate a random value based on the attribute type
                        if "integer" in attr_type:
                            event["attributes"][attr] = random.randint(1, 1000)  # Example for integers
                        elif "string" in attr_type:
                            event["attributes"][attr] = f"example_{random.randint(1, 100)}"  # Example for strings
                        # Add more types as needed based on your configuration

                self.event_batch.append(event)  # Add event to the batch
                print(f"Sending event to Axiom: {json.dumps(event)}")  # Log to console

                # Send the batch if it reaches 200 events
                if len(self.event_batch) >= 200:
                    self.send_events_to_axiom(self.event_batch)

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

    def get_frequency_in_minutes(self, frequency):
        if "every" in frequency:
            parts = frequency.split(" ")
            return int(parts[1])  # Return the number of minutes
        return 1  # Default to 1 minute if not specified

def load_config(file_path):
    with open(file_path) as f:
        return json.load(f)

def main():
    sources_config = load_config('config/sources/3tier.json')
    scenario_config = load_config('config/scenarios/normal_traffic.json')

    generator = EventGenerator(sources_config, scenario_config)
    generator.generate_events()

if __name__ == "__main__":
    main()
