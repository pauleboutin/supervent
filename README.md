# supervent

A synthetic log generator that produces high volumes of realistic log events. Event formats for various sources (an app server, Akamai, etc) are configured in config.json to mimic various sources. Behavior of configured sources will be controlled by defining scenarios (even "normal traffic" is just another scenario) that can be overlaid to simulate real-world patterns, e.g. an outage, Black Friday, a suspicious user, etc.

There is a Python version and a Go version. They do the same thing. 

# Usage
Python version:

python supervent.py [--config filename.json] 

Go version:

supervent [--config filename.json]

The default configuration file is config.json.

For now, supervent sends events to an Axiom dataset configured in axiom_config.yaml

# Roadmap
This is Phase I of the project. For now I am focused on creating realistic events. I am not an expert at event formats. Corrections and additions are welcome, whether submitted as config file entries or sent to me to deal with myself.

Phase II will add behavioral config & control to make each source behave as desired, and to orchestrate patterns across the entire simulated network. Scenarios will be prompts to an LLM that generates the behavioral configurations for the sources with which supervent has been configured. To be 100% clear, all event texts will be generated from scratch by supervent code. There'll be no way for an AI to accidentally leak personal or company-confidential info from its training data into the event stream.

# Disclosure
I am a 50% part-time consultant to Axiom (axiom.co), for whom I write marketing stuff. This is my own free-time project.

Paul Boutin
boutin@gmail.com
