# supervent

Synthetic log event generator that mimics the variety and patterns seen on real world infrastuctures, but does not use any real data, anonymized data, or other privacy risks in generation.
This version is a quick proof of concept -- version 0.0. I implemented it twice -- once in Python for popularity, once in Go for performance. Take your pick, or run both at once like I do.

The 1.0 version will be configurable via a JSON file that specifies event sources and the behavior of each.

The 2.0 goal is the configuration of scenarios, such as an attempted breakin or a major outage. The goal is that supervent will figure out what services should send what interrelated events with what timing from which sources in the configuration to simulate the specified episode. It will likely do so via an LLM, but none of the event texts themselves will be written by AI to prevent private data being leaked into the output.

Paul Boutin
boutin@gmail.com 310-600-9134 text

For now supervent sends its events via HTTP into an Axiom dataset, which you can sign up to get free of charge. Supervent gets its destination dataset and API key from a local file, axiom_config.txt
