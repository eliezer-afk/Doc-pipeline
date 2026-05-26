"""DAG de ejemplo: ingesta diaria de ventas desde API a BigQuery."""

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.google.cloud.transfers.http_to_gcs import SimpleHttpOperator


def extract_sales():
    """Extrae ventas desde la API REST."""
    pass


def transform_data():
    """Limpia y transforma los datos de ventas."""
    pass


with DAG(
    dag_id="ventas_diarias_ingesta",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    description="Ingesta diaria de ventas desde API externa a BigQuery",
    catchup=False,
) as dag:

    extract = PythonOperator(
        task_id="extract_sales",
        python_callable=extract_sales,
    )

    transform = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    load = BashOperator(
        task_id="load_to_bq",
        bash_command="bq load --source_format=NEWLINE_DELIMITED_JSON dataset.ventas gs://bucket/ventas/*.json",
    )

    extract >> transform >> load
