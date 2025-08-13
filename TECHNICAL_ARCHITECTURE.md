# Technical Architecture Document: Generic Real-Time Data Pipeline Framework

## 1. Introduction & Vision

### 1.1. Purpose

This document provides a comprehensive technical overview of the Generic Real-Time Data Pipeline Framework. It is intended for developers, architects, and data engineers who will use, maintain, or extend the framework. The goal is to provide a deep understanding of not just the *what*, but also the *why* behind the architectural decisions and technology choices.

### 1.2. Vision

The vision for this project is to provide a robust, scalable, and reusable foundation for building end-to-end data pipelines. Traditional pipelines are often monolithic and purpose-built, making them difficult to adapt. This framework is designed with modularity and generality in mind, allowing developers to ingest data from any source, process it in real-time, and serve it for analytics with minimal boilerplate and a clear, maintainable structure.

## 2. Core Architectural Principles

The design of this framework is guided by several key principles of modern data engineering.

### 2.1. Decoupling with a Central Bus (Kafka)

At the heart of the architecture is Apache Kafka, which acts as a central, persistent message bus. This is a critical design choice that decouples data producers from data consumers.

*   **Why it matters:** Producers (like our data ingestion script) don't need to know anything about the consumers (like our Flink job). They simply write data to a Kafka topic. This means we can add new consumers, take consumers offline for maintenance, or replay data without affecting the producers. This resilience is essential for a robust system.

### 2.2. Scalability

Every component is chosen with scalability in mind.

*   **Kafka, Flink, and Trino** are all designed to run as distributed systems. In a production environment, you can scale them out by adding more nodes (or pods in Kubernetes) to handle increased load.
*   The use of a **data lake (MinIO/S3)** with open table formats allows for virtually infinite storage scaling.

### 2.3. Schema Enforcement (Schema Registry)

Data quality issues are a major challenge in data pipelines. We address this at the source by using the **Confluent Schema Registry**.

*   **Why it matters:** The Schema Registry ensures that all data written to Kafka conforms to a predefined Avro schema. Any data that doesn't match the schema is rejected *before* it enters the pipeline. This prevents data quality problems from propagating downstream and breaking the Flink job or dbt models. It also provides a clear data contract for all services.

### 2.4. The Data Lakehouse & Open Table Formats (Iceberg/Delta)

We don't just dump raw files into our data lake. We use **Apache Iceberg** and **Delta Lake**, which are open table formats. This turns our data lake into a "Lakehouse".

*   **Why it matters:** These formats bring database-like features (ACID transactions, schema evolution, time travel) to our data lake files.
    *   **ACID Transactions:** Ensures that reads and writes are atomic and consistent, preventing data corruption.
    *   **Schema Evolution:** Allows us to safely add or remove columns from our tables without breaking downstream consumers.
    *   **Time Travel:** Allows us to query the state of a table at a specific point in time, which is invaluable for debugging and auditing.

### 2.5. Infrastructure as Code (Docker Compose)

The entire local development environment is defined in a single `docker-compose.yml` file.

*   **Why it matters:** This provides a reproducible, one-command setup for any developer. It eliminates "it works on my machine" problems and ensures everyone is working with the same environment and service versions. For production, this "Infrastructure as Code" principle would be extended using tools like Terraform and Kubernetes manifests.

## 3. Deep Dive into Components

### 3.1. Kafka & Confluent Schema Registry

*   **What they are:** Kafka is a distributed streaming platform. Schema Registry is a service that stores and validates data schemas.
*   **Role in Pipeline:** Kafka is the central nervous system, providing a buffer for real-time data. Schema Registry ensures all data flowing through Kafka is structured and valid.
*   **Why Avro?** We use Avro as our schema format because it is a compact binary format, supports rich data structures, and has excellent support for schema evolution, which is crucial for long-term projects.

### 3.2. Apache Flink

*   **What it is:** A powerful, stateful stream processing framework.
*   **Role in Pipeline:** Flink's job is to read data from Kafka, perform any necessary initial processing, and write it to the Bronze layer of our data lake in both Iceberg and Delta formats.
*   **Why Flink?** Flink is chosen for its high performance, low latency, and robust support for stateful processing and exactly-once semantics, which are critical for reliable data ingestion. The use of the Table API and SQL makes the logic declarative and easy to understand.

### 3.3. MinIO, Iceberg & Delta Lake (The Data Lake)

*   **What they are:** MinIO is an S3-compatible object storage service. Iceberg and Delta Lake are open table formats.
*   **Role in Pipeline:** MinIO provides the physical storage for our data lake. Iceberg and Delta organize the data within MinIO, making it reliable and queryable.

### 3.4. Trino (The Query Engine)

*   **What it is:** A distributed SQL query engine designed for high-performance, ad-hoc analytics on large datasets.
*   **Role in Pipeline:** Trino allows us to query the data in our MinIO data lake directly using standard SQL. It can read from both Iceberg and Delta Lake tables, as well as many other data sources. It's the bridge between our data lake and our BI tools.

### 3.5. dbt (Data Build Tool)

*   **What it is:** A data transformation tool that enables you to build and manage data models with simple SQL `SELECT` statements.
*   **Role in Pipeline:** dbt is used to implement the Silver and Gold layers of our Medallion Architecture. It reads from the raw Bronze tables, applies business logic, cleaning, and aggregation, and materializes these as new tables in the data lake.
*   **Why dbt?** dbt brings software engineering best practices (like version control, testing, and documentation) to the analytics workflow, making it much more robust and maintainable than a collection of ad-hoc SQL scripts.

### 3.6. Apache Airflow

*   **What it is:** A platform for programmatically authoring, scheduling, and monitoring workflows.
*   **Role in Pipeline:** Airflow orchestrates our batch-oriented tasks. In our case, it triggers the Flink job and then the dbt transformation job.
*   **Why Airflow?** While Flink and the producer are always-on streaming components, the dbt transformations are typically run on a schedule (e.g., once a day). Airflow is the industry standard for managing these scheduled dependencies.

### 3.7. Prometheus, Grafana & Superset (Observability & Visualization)

*   **What they are:** Prometheus is a metrics collection database. Grafana is a dashboarding tool. Superset is a business intelligence (BI) and data visualization tool.
*   **Role in Pipeline:** Prometheus scrapes metrics from Flink, Grafana visualizes these metrics to show the health of our pipeline, and Superset connects to Trino to allow users to explore the final, clean Gold-layer data and build their own charts and dashboards.

## 4. Local Development Workflow

The `docker-compose.yml` file is the entry point for local development.

1.  **Starting the environment:** `docker-compose up -d` starts all services.
2.  **Making code changes:**
    *   The `producer`, `dbt`, and `airflow/dags` directories are mounted as volumes into their respective containers. This means you can edit the Python and SQL files on your local machine, and the changes will be reflected inside the containers automatically.
    *   For the Flink job, you will need to restart the Flink cluster (`docker-compose restart jobmanager taskmanager`) to pick up changes in `flink_job/main.py` because the job is submitted at startup. A better approach for active development is to `docker exec` into the `jobmanager` container and submit the job manually with `flink run`.
3.  **Debugging:** Use `docker-compose logs -f <service_name>` to view the logs for a specific service (e.g., `docker-compose logs -f producer`).

## 5. Path to Production

The provided Docker Compose setup is for local development only. Deploying to production requires a more robust and scalable setup, typically on a cloud provider using Kubernetes. The `README.md` provides a high-level guide, but the core principle is to replace the single-node services in our `docker-compose.yml` with their scalable, managed, or distributed equivalents.
