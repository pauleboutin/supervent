# supervent

A synthetic log generator that produces high volumes of realistic log events. The goal is to use AI to drive realistic event data generation at scale and across services — with zero privacy issues — for test and demo purposes.


Event formats for various sources (an app server, Akamai, etc) are configured in config.json. Behavior of these configured sources will be controlled by defining scenarios (even "normal traffic" is just another scenario) that can be overlaid to simulate real-world patterns, e.g. an outage, Black Friday, a suspicious user, etc. For now, supervent just round-robins through its sources, and adds an extra key-value pair of the form "source: Cisco ASA Firewall" to each event because it's still in testing.

There is a Python version and a Go version. They do the same thing. 

# Roadmap
This is Phase I of the project. For now I am focused on creating realistic events. I am not an expert at event formats. Corrections and additions are welcome, whether submitted as config file entries or sent to me to deal with myself.

Phase II will add behavioral config & control to make each source behave as desired, and to orchestrate patterns across the entire simulated network. Scenarios will be prompts to an LLM that generates the behavioral configurations for the sources with which supervent has been configured. To be 100% clear, all event texts will be generated from scratch by supervent code. There'll be no way for an AI to accidentally leak personal or company-confidential info from its training data into the event stream.

# Disclosure
I am a 50% part-time consultant to Axiom (axiom.co), for whom I write marketing stuff. This is my own free-time project.

Paul Boutin
boutin@gmail.com

# Usage

## Command-Line Arguments

- **--config**: Specifies the path to the configuration file. If not provided, it defaults to sources.json.
- **--axiom-dataset**: Specifies the Axiom dataset name. This parameter is required.
- **--axiom-api-key**: Specifies the Axiom API key. This parameter is required.
- **--batch-size**: Specifies the batch size for HTTP requests. If not provided, it defaults to `100`.
- **--postgres-host**: Specifies the PostgreSQL host. This parameter is optional.
- **--postgres-port**: Specifies the PostgreSQL port. If not provided, it defaults to `5432`.
- **--postgres-db**: Specifies the PostgreSQL database name. This parameter is optional.
- **--postgres-user**: Specifies the PostgreSQL user. This parameter is optional.
- **--postgres-password**: Specifies the PostgreSQL password. This parameter is optional.
- **--log-level**: Specifies the level of logging messages to output. This parameter is optional. If not provided, it defaults to `INFO`.


- **--config**
  - **Description**: Path to the configuration file.
  - **Type**: String
  - **Default**: config.json
  - **Example**: `--config /path/to/sources.json`

- **--axiom-dataset**
  - **Description**: Axiom dataset name.
  - **Type**: String
  - **Required**: Yes
  - **Example**: `--dataset supervent`

- **--axiom-api-key**
  - **Description**: Axiom API key.
  - **Type**: String
  - **Required**: Yes
  - **Example**: `--api-key xaat-0e268974-2001-4c1f-a747-619dac5257f1`

- **--batch-size**
  - **Description**: Batch size for HTTP requests.
  - **Type**: Integer
  - **Default**: `100`
  - **Example**: `--batch-size 50`

- **--postgres-host**
  - **Description**: PostgreSQL host.
  - **Type**: String
  - **Example**: `--postgres-host localhost`

- **--postgres-port**
  - **Description**: PostgreSQL port.
  - **Type**: Integer
  - **Default**: `5432`
  - **Example**: `--postgres-port 5432`

- **--postgres-db**
  - **Description**: PostgreSQL database name.
  - **Type**: String
  - **Example**: `--postgres-db supervent-db`

- **--postgres-user**
  - **Description**: PostgreSQL user.
  - **Type**: String
  - **Example**: `--postgres-user dbuser`

- **--postgres-password**
  - **Description**: PostgreSQL password.
  - **Type**: String
  - **Example**: `--postgres-password dbpassword`
 
- **--log-level**
  - **Description**: Level of logging messages to output -- DEBUG,INFO,WARNING,ERROR,CRITICAL,NONE
  - **Type**: String
  - **Default**: INFO
  - **Example**: `--log-level DEBUG`

### Example Usage

**To send Supervent events to an Axiom dataset**

Go version
```sh
./supervent --config /path/to/config.json --axiom-dataset supervent --axiom-api-key xaat-0e268974-2001-4c1f-a747-619dactt57f1
```
Python version
```sh
python ./supervent.py --config /path/to/config.json --axiom-dataset supervent --axiom-api-key xaat-0e268974-2001-4c1f-a747-619dactt57f1
```

**To send to a PostgreSQL database**

Go version
```sh
./supervent --config /path/to/config.json  --postgres-host localhost --postgres-port 5432 --postgres-db supervent_db --postgres-user dbuser --postgres_password dbpassword
```
Python version
```sh
python ./supervent.py --config /path/to/config.json  --postgres_host localhost --postgres_port 5432 --postgres_db supervent_db --postgres-user dbuser --postgres-password dbpassword
```

## Source Configuration Parameters 
For config.json or other config file

- **source**
  - **Description**: Specifies a unique ID for the source of the events.
  - **Type**: String
  - **Example Values**: `"source03"`

- **description**
  - **Description**: A string that describes the source of the event for testing and debugging.
  - **Type**: String
  - **Example Values**: `"Windows Server"`

- **timestamp_format**
  - **Description**: Specifies the format of the timestamp.
  - **Type**: String
  - **Supported Values**: `UTC`, `ISO`, `Unix`, `RFC3339`
  - **Example Values**: `"UTC"`

- **fields**
  - **Description**: Specifies the fields for the events.
  - **Type**: Object
  - **Example Values**:
    ```json
    {
      "action": {
        "type": "string",
        "allowed_values": ["ALLOW", "DENY"],
        "weights": [0.7, 0.3]
      },
      "response_time": {
        "type": "int",
        "constraints": {
          "min": 1,
          "max": 1000
        },
        "distribution": "normal",
        "mean": 500,
        "stddev": 100
      }
    }
    ```

#### Field Parameters

- **type**
  - **Description**: Specifies the type of the field.
  - **Type**: String
  - **Supported Values**: `string`, `int`, `datetime`
  - **Example Values**: `"string"`

- **allowed_values**
  - **Description**: Specifies the allowed values for the field.
  - **Type**: List of strings
  - **Example Values**: `["ALLOW", "DENY"]`

- **weights**
  - **Description**: Specifies the relative frequency of values in the `allowed_values` list. There must be as many weights as there are allowed_values in the two lists, otherwise weights are ignored.
  - **Type**: List of floats
  - **Example Values**: `[0.7, 0.3]`

- **constraints**
  - **Description**: Specifies the constraints for the field.
  - **Type**: Object
  - **Example Values**:
    ```json
    {
      "min": 1,
      "max": 1000
    }
    ```

- **distribution**
  - **Description**: Specifies the distribution to use for generating integer values.
  - **Type**: String
  - **Supported Values**: `uniform`, `normal`, `exponential`, `zipfian`, `long_tail`, `random`
  - **Example Values**: `"normal"`

- **mean**
  - **Description**: Specifies the mean value for the `normal` distribution.
  - **Type**: Float
  - **Example Values**: `500`

- **stddev**
  - **Description**: Specifies the standard deviation for the `normal` distribution.
  - **Type**: Float
  - **Example Values**: `100`

- **lambda**
  - **Description**: Specifies the rate parameter for the `exponential` distribution.
  - **Type**: Float
  - **Example Values**: `0.005`

- **s**
  - **Description**: Specifies the parameter for the `zipfian` distribution.
  - **Type**: Float
  - **Example Values**: `1.2`

- **alpha**
  - **Description**: Specifies the parameter for the `long_tail` distribution.
  - **Type**: Float
  - **Example Values**: `2.0`

- **format**
  - **Description**: Specifies the format for the `datetime` field.
  - **Type**: String
  - **Example Values**: `"%Y-%m-%dT%H:%M:%SZ"`

- **messages**
  - **Description**: Specifies the formats for the `message` field. This is to enable old-school non-key/value syslog messages. The `messages` field specifies the formats for the event text's `message` field. It is a list of strings, where each string can contain placeholders that will be replaced with actual values when generating events.
  - **Type**: List of strings
  - **Example Values**:
    ```json
    "messages": [
      "{src_ip} - - [{timestamp}] \"{method} {url} {protocol}\" {status_code} {response_size} \"{referrer}\" \"{user_agent}\""
    ]
    ```
- **region** (not supported in Go version yet. I'm looking for a Faker-like package for Go that supports locales.)
  - **Description**: Specifies the regions (locales) to use for generating usernames.
  - **Type**: Array of Strings
  - **Example Values**: `["en_US", "zh_CN", "es_ES", "hi_IN", "ar_EG", "pt_BR"]`

- **count**
  - **Description**: Specifies the total number of usernames to generate for the group.
  - **Type**: Integer
  - **Example Values**: `1000`

- **group**
  - **Description**: Specifies the group name to which the usernames belong.
  - **Type**: String
  - **Example Values**: `"global_users"`

    
### Example Messages Configuration
  
  Here is a full example configuration snippet for `Apache HTTP Server` that includes the `messages` field:
  
  ```json
  {
    "vendor": "Apache HTTP Server",
    "timestamp_format": "Unix",
    "fields": {
      "src_ip": {
        "type": "string",
        "format": "ip"
      },
      "timestamp": {
        "type": "datetime",
        "format": "%d/%b/%Y:%H:%M:%S %z"
      },
      "method": {
        "type": "string",
        "allowed_values": ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"],
        "weights": [0.5, 0.2, 0.05, 0.05, 0.05, 0.05, 0.1]
      },
      "url": {
        "type": "string",
        "allowed_values": [
          "/index.html", "/login", "/nonexistent.html", "/dashboard", "/admin",
          "/api/v1/resource", "/api/v1/resource/123", "/contact", "/", "/home",
          "/submit-form", "/user/profile", "/search?q=test", "/logout", "/blog",
          "/api/v1/resource/456", "/about", "/register", "/privacy", "/sitemap.xml",
          "/robots.txt", "/comments"
        ],
        "weights": [0.3, 0.05, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.3, 0.02, 0.01, 0.01, 0.01, 0.01, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]
      },
      "protocol": {
        "type": "string",
        "allowed_values": ["HTTP/1.0", "HTTP/1.1", "HTTP/2.0"],
        "weights": [0.1, 0.8, 0.1]
      },
      "status_code": {
        "type": "int",
        "allowed_values": [200, 201, 204, 302, 304, 401, 403, 404, 500],
        "weights": [0.7, 0.05, 0.05, 0.05, 0.05, 0.02, 0.02, 0.05, 0.01]
      },
      "response_size": {
        "type": "int",
        "constraints": {
          "min": 0,
          "max": 5000
        }
      },
      "referrer": {
        "type": "string",
        "allowed_values": ["-", "http://example.com", "http://example.com/form", "http://example.com/profile", "http://example.com/blog"],
        "weights": [0.7, 0.1, 0.05, 0.05, 0.1]
      },
      "user_agent": {
        "type": "string",
        "allowed_values": [
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
          "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36",
          "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:68.0) Gecko/20100101 Firefox/68.0",
          "curl/7.68.0",
          "PostmanRuntime/7.26.8"
        ],
        "weights": [0.4, 0.2, 0.1, 0.1, 0.1, 0.1]
      },
      "message": {
        "type": "string",
        "messages": [
          "{src_ip} - - [{timestamp}] \"{method} {url} {protocol}\" {status_code} {response_size} \"{referrer}\" \"{user_agent}\""
        ]
      }
    }
  }
  ```


### Username Groups

The `username_groups` section defines different groups of usernames. Each group specifies the regions and the number of usernames to generate. Here is an example configuration: This example would great 1000 usernames typically found in China, Spain, US, UK, Egypt and Portugal, and a separate group of 500 names solely in India. The Fictional app would generate events whosse user: field rotates among 20 of the 1000 names in global_users.

```json
{
  "username_groups": {
    "global_users": {
      "regions": ["en_US", "zh_CN", "es_ES", "hi_IN", "ar_EG", "pt_BR"],
      "count": 1000
    },
    "outsourced_partner": {
      "regions": ["en_IN"],
      "count": 500
    }
  },
 "sources": [
    {
      "vendor": "Fictional app",
      "fields": {
        "user": {
          "type": "string",
          "group": "global_users",
          "count": 20
        }
      }
    }
]
}
```

- **Regions**: Each group can specify one or more regions. The `faker` library uses these regions to generate names that are representative of the specified locales.
- **Count**: The `count` field specifies the total number of usernames to generate for the group.
- **Distribution**: The usernames are distributed evenly across the specified regions. If the count is not perfectly divisible by the number of regions, the remaining usernames are distributed randomly among the regions.


