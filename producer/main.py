import os
import logging
import json
import random
import time
from uuid import uuid4

from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import alpaca_trade_api as tradeapi #Alpaca API

# --- Configuration ---
# This section loads all configuration from environment variables.
# This makes the script flexible and easy to configure in a containerized environment.

# General configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "stock_data")

# Alpaca API configuration for the example producer
APCA_API_KEY_ID = os.environ.get("APCA_API_KEY_ID")
APCA_API_SECRET_KEY = os.environ.get("APCA_API_SECRET_KEY")
APCA_API_BASE_URL = os.environ.get("APCA_API_BASE_URL", "https://paper-api.alpaca.markets") # Use paper trading by default
STOCKS_TO_TRACK = os.environ.get("STOCKS_TO_TRACK", "AAPL,GOOG,AMZN,MSFT").split(',')


# --- Logging Setup ---
# This section sets up structured logging to output JSON objects.
# JSON logs are easier to parse, search, and analyze in a centralized logging system.
class JsonFormatter(logging.Formatter):
    """Custom formatter to output logs in JSON format."""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName
        }
        return json.dumps(log_record)

# Initialize the logger
logger = logging.getLogger("StockProducer")
logger.setLevel(LOG_LEVEL)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)


# --- Avro Schema Handling ---
# The producer is designed to be schema-agnostic. It loads the Avro schema
# from a file path specified by an environment variable.
AVRO_SCHEMA_PATH = os.environ.get("AVRO_SCHEMA_PATH", "/app/schemas/stock_trade.avsc")

def load_avro_schema(schema_path):
    """Loads an Avro schema from the specified file path."""
    try:
        logger.info(f"Loading Avro schema from {schema_path}")
        with open(schema_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Avro schema file not found at: {schema_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading Avro schema: {e}")
        raise


# --- Kafka Producer Setup ---
def create_producer():
    """
    Creates and returns a Kafka SerializingProducer.
    The SerializingProducer automatically handles schema registration
    and Avro serialization of the messages.
    """
    try:
        # Load the Avro schema from the file.
        schema_str = load_avro_schema(AVRO_SCHEMA_PATH)

        # Create a Schema Registry client.
        schema_registry_client = SchemaRegistryClient({'url': SCHEMA_REGISTRY_URL})

        # Create an Avro serializer.
        avro_serializer = AvroSerializer(schema_registry_client, schema_str)

        # Configure the producer.
        producer_conf = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'key.serializer': 'org.apache.kafka.common.serialization.StringSerializer', # Keys are simple strings.
            'value.serializer': avro_serializer # Values are Avro-serialized.
        }
        logger.info(f"Connecting to Kafka with config: {producer_conf}")
        return SerializingProducer(producer_conf)
    except Exception as e:
        logger.error(f"Failed to create Kafka producer: {e}")
        raise

def delivery_report(err, msg):
    """
    Callback function for Kafka producer. It's called once for each message
    produced to indicate its delivery result.
    """
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")


# --- Alpaca WebSocket Handler (Example Data Source) ---
class AlpacaStreamHandler:
    """
    This class handles the real-time trade data coming from the Alpaca WebSocket.
    It's designed to be a callback that processes each trade as it arrives.
    """
    def __init__(self, producer):
        self.producer = producer

    async def __call__(self, trade):
        """
        This method is called for each trade received from the stream.
        It transforms the trade data into our Avro schema format and produces it to Kafka.
        """
        try:
            # Transform the raw trade object into a dictionary matching our Avro schema.
            trade_data = {
                "symbol": trade.symbol,
                "price": float(trade.price),
                "volume": int(trade.size),
                "timestamp": int(trade.timestamp.timestamp() * 1000) # Convert to Unix timestamp in milliseconds
            }

            logger.info(f"Received trade: {trade_data}")

            # Produce the message to Kafka.
            # The key is a UUID to ensure messages are distributed across partitions.
            self.producer.produce(
                topic=KAFKA_TOPIC,
                key=str(uuid4()),
                value=trade_data,
                on_delivery=delivery_report
            )
            # poll() is used to serve delivery reports from previous produce() calls.
            self.producer.poll(0)

        except Exception as e:
            logger.error(f"Error processing trade: {e}")


# --- Mock Data Generator ---
def run_mock_producer(producer):
    """
    Generates and sends mock stock data. This is used if Alpaca API keys are not provided,
    allowing the rest of the pipeline to be tested without a live data feed.
    """
    logger.info("Running in MOCK mode. Generating fake data...")
    while True:
        try:
            # For each stock symbol, create a fake trade.
            for symbol in STOCKS_TO_TRACK:
                trade_data = {
                    "symbol": symbol,
                    "price": round(random.uniform(100, 500), 2),
                    "volume": random.randint(1, 1000),
                    "timestamp": int(time.time() * 1000)
                }
                logger.info(f"Producing mock trade: {trade_data}")
                producer.produce(
                    topic=KAFKA_TOPIC,
                    key=str(uuid4()),
                    value=trade_data,
                    on_delivery=delivery_report
                )
            # Flush any outstanding messages.
            producer.flush()
            time.sleep(2) # produce a batch of data every 2 seconds
        except KeyboardInterrupt:
            logger.info("Mock producer stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in mock producer loop: {e}")
            time.sleep(5)


# --- Main Execution ---
if __name__ == "__main__":
    # Create the Kafka producer.
    producer = create_producer()

    # Check if Alpaca API keys are provided.
    if APCA_API_KEY_ID and APCA_API_SECRET_KEY:
        # If keys are present, connect to the live Alpaca data stream.
        logger.info("Alpaca API keys found. Starting live data producer...")

        # Initialize Alpaca API and WebSocket stream.
        api = tradeapi.REST(APCA_API_KEY_ID, APCA_API_SECRET_KEY, base_url=APCA_API_BASE_URL)
        stream = tradeapi.Stream(APCA_API_KEY_ID, APCA_API_SECRET_KEY, base_url=APCA_API_BASE_URL, data_feed='iex')

        # Create a handler instance and subscribe it to the trade stream for our stocks.
        handler = AlpacaStreamHandler(producer)
        stream.subscribe_trades(handler, *STOCKS_TO_TRACK)

        # Start the stream. This is a blocking call.
        try:
            stream.run()
        except KeyboardInterrupt:
            logger.info("Alpaca stream stopped by user.")
        except Exception as e:
            logger.error(f"Alpaca stream failed: {e}")
        finally:
            # Ensure all messages are sent before exiting.
            producer.flush()

    else:
        # If keys are not found, run the mock data producer.
        logger.warning("Alpaca API keys not found in environment variables (APCA_API_KEY_ID, APCA_API_SECRET_KEY).")
        run_mock_producer(producer)
