# Generic Real-Time Data Pipeline Framework

This project provides a complete, reusable, end-to-end framework for building real-time data pipelines. The entire environment is containerized using Docker and orchestrated with Airflow. It comes with a working example of a stock trade data pipeline to demonstrate its capabilities.

## Architecture and Data Flow

The framework uses a modern, decoupled architecture. Here are text-based diagrams illustrating the flow.

### High-Level Service Architecture

```
+-----------------+      +----------------+      +-----------------+
|   Producer      |----->|     Kafka      |----->|      Flink      |
| (Python Script) |      | (MESSAGING)    |      | (PROCESSING)    |
+-----------------+      +----------------+      +-----------------+
                           |       ^
                           |       |
                 +------------------+
                 | Schema Registry  |
                 | (SCHEMA MGMT)    |
                 +------------------+
                                                     |
                                                     v
+-----------------+      +----------------+      +-----------------+
|    Superset     |<-----|      Trino     |<-----|      MinIO      |
| (VISUALIZATION) |      | (QUERY ENGINE) |      | (DATA LAKE)     |
+-----------------+      +----------------+      +-----------------+
        ^                      ^                       ^
        |                      |                       |
+-----------------+      +----------------+      +-----------------+
|     Grafana     |<-----|   Prometheus   |      |       dbt       |
|  (MONITORING)   |      |   (METRICS)    |      | (TRANSFORMATION)|
+-----------------+      +----------------+      +-----------------+
        ^                                                |
        |                                                |
        +------------------------------------------------+
        |                     Airflow                      |
        |                  (ORCHESTRATION)                 |
        +--------------------------------------------------+
```

### Medallion Data Flow

The pipeline processes data according to the Medallion Architecture.

```
                  +----------------+
                  |  Raw Data Feed |
                  | (e.g., Alpaca) |
                  +----------------+
                          |
                          v
+-----------+     +----------------+     +----------------+
| Producer  |---->|     Kafka      |---->|      Flink     |
+-----------+     +----------------+     +----------------+
                                                 |
                                                 v
                  +--------------------------------------+
                  |          BRONZE LAYER (RAW)          |
                  | (MinIO: Iceberg & Delta Lake Tables) |
                  +--------------------------------------+
                                                 | (dbt runs)
                                                 v
                  +--------------------------------------+
                  |         SILVER LAYER (CLEANED)       |
                  |     (dbt model -> new Trino table)   |
                  +--------------------------------------+
                                                 | (dbt runs)
                                                 v
                  +--------------------------------------+
                  |      GOLD LAYER (AGGREGATED/BI)      |
                  |     (dbt model -> new Trino table)   |
                  +--------------------------------------+
```

> For a much more detailed explanation of the technology choices, design principles, and a deep dive into each component, please see the [**Technical Architecture Document**](./TECHNICAL_ARCHITECTURE.md).

## How to Run the Pipeline Locally (Stock Market Example)

This guide explains how to run the included stock market data pipeline example on your local machine.

### Step 1: Prerequisites

*   **Docker and Docker Compose:** Ensure you have the latest versions installed.
*   **Resources:** At least 8GB of RAM is recommended, as the environment runs over 15 services.

### Step 2: Configuration (One-Time Setup)

Before the first launch, a few components must be configured.

#### Flink Connector JARs (Required)

The Flink job requires several connector JAR files to communicate with other services. You must download these and make them available to Flink.

1.  **Download the JARs:** You will need to download the following JARs for **Flink 1.17.1**. The easiest way is to search for them on Maven Central (`https://search.maven.org/`).
    *   `flink-sql-connector-kafka-1.17.1.jar`
    *   `iceberg-flink-runtime-1.17-1.2.1.jar`
    *   `delta-flink-2.4.0.jar`
    *   `hadoop-aws-3.3.2.jar`
    *   `aws-java-sdk-bundle-1.11.1026.jar`
2.  **Add JARs to Dockerfile:**
    *   Open the `flink_job/Dockerfile`.
    *   Uncomment the `ADD` commands and replace the placeholder URLs with the actual download links you found.

#### Alpaca API Keys (Optional)

The `docker-compose.yml` file is pre-configured with the API keys you provided. If you want to switch to mock data, simply comment out or remove the `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` environment variables from the `producer` service.

### Step 3: Launch the Environment

Once configured, start the entire pipeline with a single command from the project root:

```bash
docker-compose up -d
```

This command will:
1.  Build the custom Docker images for the producer, Flink, and dbt services.
2.  Start all ~15 services in the background.
3.  The producer will immediately start sending data to Kafka.
4.  The Airflow services will initialize.

**To check the status of the services:** `docker-compose ps`
**To view logs from all services:** `docker-compose logs -f`

## Orchestration with Airflow

The batch processing part of this pipeline is orchestrated by Airflow.

### Accessing the Airflow UI

*   **URL:** `http://localhost:8083`
*   **Login:** `airflow` / `airflow`

### Understanding the `stock_data_pipeline` DAG

You will find a DAG named `stock_data_pipeline`. This DAG is responsible for creating the Bronze, Silver, and Gold tables.

*   **Schedule:** It is set to run daily but is paused by default.
*   **Tasks:**
    1.  `submit_flink_job`: This task submits the PyFlink script to the Flink cluster. The Flink job will run indefinitely, consuming data from Kafka and writing to the Bronze tables. *Note: For a production system, you might run this as a long-running service instead of an Airflow task.*
    2.  `run_dbt_models`: This task executes `dbt run`, which transforms the raw Bronze data into the Silver and Gold layers. It runs only after the Flink job has been submitted successfully.

### How to Run the Pipeline Manually

1.  Go to the Airflow UI.
2.  Un-pause the `stock_data_pipeline` DAG.
3.  Click the "Play" button to trigger a new DAG run.

## How to Deploy to a Production Environment

Deploying this framework to a production environment (e.g., AWS, GCP, Azure) requires moving from Docker Compose to a more robust orchestration system like Kubernetes.

### Key Principles for Production Deployment

1.  **Use Managed Services:** Instead of running databases like PostgreSQL and Kafka in containers, use managed cloud services (e.g., Amazon RDS for PostgreSQL, Amazon MSK for Kafka, Amazon S3 for the data lake). This improves reliability, scalability, and maintainability.
2.  **Container Registry:** Build your custom Docker images (`producer`, `flink`, `dbt`) and push them to a container registry (e.g., Amazon ECR, Google Container Registry, Docker Hub).
3.  **Kubernetes for Orchestration:**
    *   Deploy Airflow, Flink, Trino, and your custom services to a Kubernetes cluster.
    *   Use **Helm charts** to manage these deployments. There are official or community-maintained Helm charts for most of these services.
4.  **Configuration and Secrets Management:**
    *   Externalize all configuration (hostnames, ports, etc.) into Kubernetes ConfigMaps.
    *   Store all sensitive information (API keys, database passwords) in Kubernetes Secrets or a dedicated secret manager like HashiCorp Vault or AWS Secrets Manager. **Do not store secrets in your `docker-compose.yml` or source code.**
5.  **CI/CD for Automation:** Set up a CI/CD pipeline (e.g., using GitHub Actions, Jenkins, or GitLab CI) to automatically build and deploy your services when you make changes to the code.

### Example Deployment Workflow (on AWS)

1.  **Infrastructure:**
    *   Provision an S3 bucket for your data lake.
    *   Provision an Amazon MSK cluster (Kafka).
    *   Provision two Amazon RDS for PostgreSQL instances (one for Airflow, one for the Hive Metastore).
    *   Provision an Amazon EKS cluster (Kubernetes).
2.  **Containerization:**
    *   Update your `producer`, `flink`, and `dbt` images to read all configuration from environment variables.
    *   Build and push these images to Amazon ECR.
3.  **Deployment:**
    *   Use the official Helm chart for Airflow to deploy it to EKS. Configure it to use your RDS instance and to pull your DAGs from a Git repository.
    *   Use the official Helm chart for Flink to deploy it to EKS.
    *   Create Kubernetes deployments for your producer and dbt services, ensuring they use the correct images from ECR and are configured with the appropriate ConfigMaps and Secrets.

## Accessing the Services

*   **Airflow UI:** `http://localhost:8083`
*   **Grafana:** `http://localhost:3000`
*   **Superset:** `http://localhost:8088`
*   **MinIO Console:** `http://localhost:9001`
*   **Flink UI:** `http://localhost:8082`
