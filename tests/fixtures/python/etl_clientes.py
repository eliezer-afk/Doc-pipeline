"""ETL de clientes: extrae desde Postgres, transforma y carga en BigQuery."""

import pandas as pd
from google.cloud import bigquery
import psycopg2


def extract_customers(conn_string: str) -> pd.DataFrame:
    """Extrae clientes activos desde Postgres."""
    conn = psycopg2.connect(conn_string)
    df = pd.read_sql("SELECT * FROM customers WHERE active = true", conn)
    conn.close()
    return df


def transform_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza emails y agrega columna de segmento."""
    df["email"] = df["email"].str.lower().str.strip()
    df["segment"] = df["total_spend"].apply(
        lambda x: "premium" if x > 10000 else "standard"
    )
    return df


def load_to_bigquery(df: pd.DataFrame, table: str) -> None:
    """Carga el DataFrame en BigQuery."""
    client = bigquery.Client()
    job = client.load_table_from_dataframe(df, table)
    job.result()


def run():
    df = extract_customers("postgresql://user:pass@host/db")
    df = transform_customers(df)
    load_to_bigquery(df, "proyecto.dataset.clientes")


if __name__ == "__main__":
    run()
