# supervent

Synthetic log event generator that does not use any real data, anonymized data, or other privacy risks in generation.
This version is a quick proof of concept -- version 0.0. There are Python and Go versions that do the same thing. Take your pick.

The 1.0 version will be configurable via a JSON file that specifies event sources and the behavior of each.

The 2.0 goal is the configuration of scenarios, such as an attempted breakin or a major outage. The goal is that supervent will figure out what services should sent what events when to simulate a specified episode. It will like do so via an LLM, but none of the event texts themselves will be written by AI to prevent private data being leaked into the output.

boutin@gmail.com 310-600-9134

For now supervent sends its events via HTTP into an Axiom dataset, which you can sign up to get free of charge. Supervent gets its destination dataset and API key from a local file, axiom_config.txt
