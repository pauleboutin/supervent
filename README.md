# supervent

A synthetic log generator that produces high volumes of realistic log events. Event formats are configured in config.json to mimic various sources. 

There is a Python version and a Go version. They do the same thing. 

Usage
Python version:
python supervent.py [--config filename.json] 

Go version:
supervent [--config filename.json]

The default configuration file is config.json
For now, supervent sends events to an Axiom dataset configured in axiom_config.yaml

This is Phase I of the project. For now I am focused on creating realistic events. I am not an expert at event formats. Corrections and additions are welcome, whether submitted as config file entries or sent to me to deal with myself.

Phase II will add behavioral config & control to make each source behave as desired, and to orchestrate patterns across the entire simulated network. Normal traffic will be a defined pattern. You'll be able to overlay pattern configurations to inject scenarios. Phase II will almost surely involve use of an LLM to do the complex, nuanced control of sources. It's important, though, that there's a hard line between control and event-writing. There'll be no way for an AI to accidentally leak personal or company-confidential training data into the event stream. 

Disclosure
I am a 50% part-time consultant to Axiom (axiom.co), for whom I write customer stories and edit blog posts and other short texts as part of their marketing efforts. This is my own spare-time project.

Paul Boutin
boutin@gmail.com
