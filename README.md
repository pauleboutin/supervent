# Realistic Log Generator

A configurable, pattern-aware log generator that creates interconnected events across multiple system components. Designed to simulate realistic application ecosystems for testing, development, and training purposes.

The current implementation, branch 3.0, generates syntactically correct but semantically meaningless events. It's one thing to generate syntactically valid logs, but quite another to generate logs that tell a coherent story about system behavior. Real system events have important patterns and correlations that this simplified version doesn't capture, such as:

- Business hours patterns vs off-hours
- Realistic error cascades
- Performance degradation patterns
- Related sequences of operations (login → view profile → update settings)
- Geographic and time-zone based access patterns
- Realistic response times based on operation type
- Correlated database operations (SELECT before UPDATE)
- Load-based response time variations
- Session-based user behaviors
- Cache hit/miss patterns
- Fields with very high cardinality

We ("we" is me and several LLM collaborators) are patiently but steadily adding support for these aspects of log simulation and expect to be done by the end of January 2025.



## Features

- **Configurable Event Sources**: Define custom log sources (web servers, application servers, databases, etc.) through YAML configuration
- **Event Dependencies**: Model realistic cause-and-effect relationships between events across different system components
- **Request Correlation**: Track related events through request IDs across the entire system
- **Flexible Output**: Generate events in standardized formats suitable for common log aggregation tools
- **Time-Based Generation**: Create events with realistic temporal distributions and patterns

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure your event sources and patterns in config.yaml:
```yaml
sources:
  web_server:
    description: "Web server logs"
    attributes:
      # Define attributes and their possible values
    event_types:
      # Define event types and their formats
    
dependencies:
  # Define event chains across sources
```
3. Run the generator:

### Prerequisites
- Python 3.8 or higher
- Required packages: install using `pip install -r requirements.txt`
- Configuration file (see `config/config.yaml` for example)

### Basic Usage

```bash
# Send events to Axiom
python supervent.py -c config/config.yaml --output axiom -d your_dataset -t your_token

# Send events to PostgreSQL
python supervent.py -c config/config.yaml --output postgres \
    --pg-host localhost \
    --pg-db your_database \
    --pg-user your_user \
    --pg-password your_password
```

#### Command Line Options
- -c, --config        Path to configuration YAML file (default: config/config.yaml)
- --output           Choose output destination: 'axiom' or 'postgres'

#### Axiom options:
- -d, --dataset      Axiom dataset name
- -t, --token        Axiom API token (can also use AXIOM_TOKEN environment variable)

#### PostgreSQL options:
--pg-host          PostgreSQL host (default: localhost)
--pg-port          PostgreSQL port (default: 5432)
--pg-db            PostgreSQL database name
--pg-user          PostgreSQL username
--pg-password      PostgreSQL password
--pg-table         PostgreSQL table name (default: events)

#### Environment Variables
- AXIOM_TOKEN: Your Axiom API token
- POSTGRES_HOST: PostgreSQL host
- POSTGRES_PORT: PostgreSQL port
- POSTGRES_DB: PostgreSQL database name
- POSTGRES_USER: PostgreSQL username
- POSTGRES_PASSWORD: PostgreSQL password

#### Example
```Bash
# Using environment variables
export AXIOM_TOKEN=your_token
python supervent.py -c config/config.yaml --output axiom -d your_dataset

# Or direct command line
python supervent.py -c config/config.yaml --output axiom -d your_dataset -t your_token
The generator will create events based on your configuration file, including dependent events through configured event chains. Progress and completion information will be displayed in the console.
```

## Performance Tuning

For maximum throughput:

1. Use webaccess.yaml config for single-source testing
2. Set batch_size to 1000000 for optimal HTTP efficiency
3. Ensure network interfaces match available ENIs (15 for c6gn.16xlarge)
4. Monitor with:
   ```bash
   python supervent.py -c config/webaccess.yaml -l debug
   ```


