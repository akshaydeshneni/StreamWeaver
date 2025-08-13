import os
import logging
import json

from pyflink.table import EnvironmentSettings, TableEnvironment

# --- Configuration ---
# Load all configuration from environment variables for flexibility.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "stock_data")

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
S3_WAREHOUSE_PATH = os.environ.get("S3_WAREHOUSE_PATH", "s3a://warehouse")

HIVE_METASTORE_URI = os.environ.get("HIVE_METASTORE_URI", "thrift://hive-metastore:9083")

# --- Logging Setup ---
# A simple JSON formatter to produce structured logs.
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName
        }
        return json.dumps(log_record)

logger = logging.getLogger("PyFlinkJob")
logger.setLevel(LOG_LEVEL)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

def main():
    logger.info("Starting PyFlink job for data ingestion...")

    # --- Flink Environment Setup ---
    # Create a TableEnvironment for executing SQL queries.
    # We use streaming mode as we are reading from a continuous Kafka stream.
    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)

    # --- Flink Configuration ---
    # This section sets various Flink configurations. These are critical for
    # running the job reliably and connecting to other services.

    # Checkpointing configuration: Enables fault tolerance by taking periodic snapshots.
    t_env.get_config().get_configuration().set_string("execution.checkpointing.interval", "1min")
    t_env.get_config().get_configuration().set_string("execution.checkpointing.mode", "EXACTLY_ONCE")
    t_env.get_config().get_configuration().set_string("state.backend", "filesystem")
    t_env.get_config().get_configuration().set_string("state.checkpoints.dir", f"{S3_WAREHOUSE_PATH}/checkpoints")

    # S3 configuration: Allows Flink to connect to our S3-compatible storage (MinIO).
    t_env.get_config().get_configuration().set_string("s3.endpoint", S3_ENDPOINT)
    t_env.get_config().get_configuration().set_string("s3.access-key", S3_ACCESS_KEY)
    t_env.get_config().get_configuration().set_string("s3.secret-key", S3_SECRET_KEY)
    t_env.get_config().get_configuration().set_string("s3.path.style.access", "true")

    # Prometheus metrics reporter: Exposes Flink metrics for Prometheus to scrape.
    t_env.get_config().get_configuration().set_string("metrics.reporter.prom.class", "org.apache.flink.metrics.prometheus.PrometheusReporter")
    t_env.get_config().get_configuration().set_string("metrics.reporter.prom.port", "9250-9260")

    # --- Create Catalogs and Tables using SQL DDL ---
    # This is the core of the Flink job, where we define our sources and sinks
    # using Flink's SQL Data Definition Language (DDL).

    # 1. Create Iceberg Catalog
    # A catalog allows Flink to manage metadata about tables, databases, etc.
    # We use a Hive-compatible catalog for Iceberg, which stores metadata in the Hive Metastore.
    iceberg_catalog_sql = f"""
    CREATE CATALOG iceberg_catalog WITH (
        'type'='iceberg',
        'catalog-type'='hive',
        'uri'='{HIVE_METASTORE_URI}',
        'warehouse'='{S3_WAREHOUSE_PATH}/iceberg'
    )
    """
    logger.info(f"Creating Iceberg catalog with SQL:\n{iceberg_catalog_sql}")
    t_env.execute_sql(iceberg_catalog_sql)
    t_env.execute_sql("USE CATALOG iceberg_catalog")
    t_env.execute_sql("CREATE DATABASE IF NOT EXISTS bronze")


    # 2. Create Kafka Source Table
    # This DDL defines a table that reads from our Kafka topic.
    # It specifies the connector type ('kafka'), topic, servers, and format ('avro-confluent').
    # The 'avro-confluent' format automatically uses the Schema Registry to deserialize messages.
    kafka_source_sql = f"""
    CREATE TABLE kafka_stock_source (
        `symbol` STRING,
        `price` DOUBLE,
        `volume` BIGINT,
        `timestamp` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp' -- Extracts the Kafka message timestamp
    ) WITH (
        'connector' = 'kafka',
        'topic' = '{KAFKA_TOPIC}',
        'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP_SERVERS}',
        'properties.group.id' = 'flink-stock-consumer',
        'scan.startup.mode' = 'earliest-offset',
        'value.format' = 'avro-confluent',
        'value.avro-confluent.url' = '{SCHEMA_REGISTRY_URL}'
    )
    """
    logger.info(f"Creating Kafka source table with SQL:\n{kafka_source_sql}")
    t_env.execute_sql(kafka_source_sql)

    # 3. Create Iceberg Sink Table
    # This table will store the raw data in Apache Iceberg format.
    # It's defined within the 'bronze' database of our Iceberg catalog.
    iceberg_sink_sql = """
    CREATE TABLE IF NOT EXISTS iceberg_catalog.bronze.raw_stock_trades (
        `symbol` STRING,
        `price` DOUBLE,
        `volume` BIGINT,
        `event_time` TIMESTAMP_LTZ(3)
    ) WITH (
        'connector'='iceberg'
    )
    """
    logger.info(f"Creating Iceberg sink table with SQL:\n{iceberg_sink_sql}")
    t_env.execute_sql(iceberg_sink_sql)

    # 4. Create Delta Lake Sink Table
    # This table will store the raw data in Delta Lake format.
    # The Delta connector requires specifying the S3 path directly.
    delta_sink_sql = f"""
    CREATE TABLE delta_stock_sink (
        `symbol` STRING,
        `price` DOUBLE,
        `volume` BIGINT,
        `event_time` TIMESTAMP_LTZ(3)
    ) WITH (
        'connector'='delta',
        'table-path'='{S3_WAREHOUSE_PATH}/delta/raw_stock_trades'
    )
    """
    logger.info(f"Creating Delta sink table with SQL:\n{delta_sink_sql}")
    t_env.execute_sql(delta_sink_sql)


    # --- Streaming Data Ingestion Logic ---
    logger.info("Starting data ingestion from Kafka to Iceberg and Delta sinks...")

    # A StatementSet allows us to execute multiple INSERT statements together,
    # ensuring that data is written to both sinks atomically.
    statement_set = t_env.create_statement_set()

    # Define the source table to read from.
    source_table = t_env.from_path("kafka_stock_source")

    # Add the INSERT statements to the set.
    # Flink will handle the data conversion between the source and sink tables.
    statement_set.add_insert("iceberg_catalog.bronze.raw_stock_trades", source_table)
    statement_set.add_insert("delta_stock_sink", source_table)

    # Execute the statement set to start the data flow.
    # This is a blocking call that submits the job to the Flink cluster.
    statement_set.execute()

    logger.info("PyFlink job finished.") # This line will not be reached in a continuous streaming job.

if __name__ == "__main__":
    main()
