from __future__ import annotations

import pendulum

from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

# This is the definition of the Airflow DAG (Directed Acyclic Graph)
# which orchestrates our data pipeline.
with DAG(
    dag_id="stock_data_pipeline",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    schedule="@daily",
    tags=["stock-pipeline"],
    doc_md="""
    ### Stock Data Pipeline

    This DAG orchestrates the batch processing part of the data pipeline.
    It triggers the Flink job to ingest data and then triggers the dbt job
    to transform the data into the Silver and Gold layers.
    """,
) as dag:
    # This task is responsible for submitting the PyFlink job to the Flink cluster.
    # We use the BashOperator to execute a `docker exec` command, which runs
    # the `flink run` command inside the running `jobmanager` container.
    # The `-d` flag runs the job in detached mode, so the command returns immediately
    # and the Flink job runs in the background.
    submit_flink_job = BashOperator(
        task_id="submit_flink_job",
        bash_command=(
            "docker exec jobmanager "
            "flink run -d -py /home/flink/main.py" # Note: Path inside the Flink container
        ),
    )

    # This task runs the dbt models to transform the data in the data lake.
    # It also uses `docker exec` to run the `dbt run` command inside the `dbt` container.
    # This task will only run after the `submit_flink_job` task has completed successfully.
    run_dbt_models = BashOperator(
        task_id="run_dbt_models",
        bash_command="docker exec dbt dbt run",
    )

    # This line defines the dependency between the tasks.
    # The `>>` operator means that `submit_flink_job` must run before `run_dbt_models`.
    submit_flink_job >> run_dbt_models
