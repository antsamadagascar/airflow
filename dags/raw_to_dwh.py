from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.utils.task_group import TaskGroup
from datetime import datetime, timedelta

default_args = {
    'start_date': datetime(2025, 4, 30),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# DDL de création du schéma et des tables DWH
DWH_DDL = {
    "schema": """
        CREATE SCHEMA IF NOT EXISTS ecommerce_dwh_star;
        SET search_path = ecommerce_dwh_star;
    """,
    "dim_date": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.dim_date (
            date_key        INT,
            day             INT,
            month           INT,
            quarter         INT,
            year            INT,
            day_of_week     VARCHAR(10),
            day_of_week_num INT
        );
    """,
    "dim_time": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.dim_time (
            time_key INT,
            hour     INT,
            minute   INT,
            second   INT,
            am_pm    VARCHAR(2)
        );
    """,
    "dim_product": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.dim_product (
            product_key   INT,
            product_id    INT,
            product_name  TEXT,
            category_id   INT,
            category_name TEXT,
            price         NUMERIC(10,2)
        );
    """,
    "dim_customer": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.dim_customer (
            customer_key INT,
            client_id    INT,
            full_name    TEXT,
            email        TEXT,
            signup_date  DATE
        );
    """,
    "dim_payment_method": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.dim_payment_method (
            payment_method_key INT,
            method             VARCHAR(50)
        );
    """,
    "fact_sales": """
        CREATE TABLE IF NOT EXISTS ecommerce_dwh_star.fact_sales (
            sale_key           INT,
            sale_id            INT,
            date_key           INT,
            time_key           INT,
            product_key        INT,
            customer_key       INT,
            quantity           INT,
            total_amount       NUMERIC(10,2),
            payment_method_key INT
        );
    """
}

with DAG(
    dag_id='etl_raw_to_dwh',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
    tags={'ecommerce', 'dwh'},
) as dag:

    # 1) Préparation du schéma et des tables de destination
    with TaskGroup('prepare_dwh') as prepare_dwh:
        for table_id, ddl in DWH_DDL.items():
            SQLExecuteQueryOperator(
                task_id=f'create_{table_id}',
                sql=ddl,
                conn_id='postgres_dwh',
                autocommit=True
            )

    # 2) Appel de la procédure maître une fois les tables prêtes
    with TaskGroup('load_dwh') as load_dwh:
        etl_master = SQLExecuteQueryOperator(
            task_id='run_etl_master',
            sql='CALL etl_master()',
            conn_id='postgres_dwh',
            autocommit=True
        )

    # Ordonnancement : d’abord préparation, puis chargement
    prepare_dwh >> load_dwh
