# supervent

Synthetic log event generator that does not use any real data, anonymized data, or other privacy risks in generation.
This version is a quick proof of concept. The 1.0 version will be configurable via a JSON file that specifies event sources and the behavior of each.
The 2.0 goal is the configuration of scenarios for which supervent will figure out what services should sent what events when. *That* is likely an LLM project, but none of the events themselves will be written by an LLM, again to prevent private data leaks.
boutin@gmail.com 310-600-9134

Right now supervent loads into axiom, reading those settings from a local file axiom_config.txt
