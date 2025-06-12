from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime, timedelta
from sqlalchemy import create_engine
import pandas as pd
import datetime as dt

default_args = {
    'start_date': datetime(2025, 5, 1),
    'retries': 0,
    'retry_delay': timedelta(minutes=0),
}

def clean_and_load(table_name, sql_select, target_schema, target_table):
    # Convert numpy types to Python native
    def to_python(val):
        try:
            return val.item()
        except AttributeError:
            return val

    # Fallback time conversion
    def int_to_time(x):
        try:
            hours = int(x) // 10000
            minutes = (int(x) // 100) % 100
            seconds = int(x) % 100
            return dt.time(hours, minutes, seconds)
        except Exception:
            # Encourage the row to survive dropna(subset=[...])
            return dt.time(0, 0, 0)

    hook = PostgresHook(postgres_conn_id='postgres_dwh')
    engine = create_engine(hook.get_uri())
    
    # 1⃣ Lecture des données sources
    df = pd.read_sql(sql_select, con=engine)
    print(f"[{table_name}] before cleaning: {df.shape[0]} rows")
    print(df.dtypes)

    # 2⃣ Dédoublonnage + suppression uniquement si sale_id est manquant
    df = df.drop_duplicates()
    if 'sale_id' in df.columns:
        df = df.dropna(subset=['sale_id'])
    
    # 3⃣ Parsing date_key
    if 'date_key' in df:
        df['date_key'] = pd.to_datetime(
            df['date_key'].astype(str),
            format='%Y%m%d',
            errors='coerce'
        ).dt.date

    # 4⃣ Conversion time_key pour dim_time et fact_sales
    if target_table in ('dim_time', 'fact_sales') and 'time_key' in df.columns:
        df['time_key'] = df['time_key'].apply(int_to_time)

    # 5⃣ Alignement avec le schéma cible
    cols = hook.get_pandas_df(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        parameters=(target_schema, target_table)
    )
    column_types = dict(zip(cols['column_name'], cols['data_type']))
    target_columns = cols['column_name'].tolist()
    df = df[[c for c in df.columns if c in target_columns]]

    # 6⃣ Préparation des lignes à insérer
    rows = [
        tuple(to_python(v) for v in row)
        for row in df.values.tolist()
    ]

    # 7⃣ Insert ou print “no rows”
    if rows:
        hook.insert_rows(
            table=f"{target_schema}.{target_table}",
            rows=rows,
            target_fields=list(df.columns),
            commit_every=1000
        )
        print(f"Inserted {len(rows)} rows into {target_schema}.{target_table}")
    else:
        print(f"No rows to insert into {target_schema}.{target_table}")

def create_dag():
    with DAG(
        dag_id='etl_clean_and_load_dwh',
        default_args=default_args,
        schedule='@daily',
        catchup=False,
        tags={'ecommerce', 'dwh', 'cleaning'},
    ) as dag:

        # 1. Création du schema + tables (init en tout premier)
        initialize_schema = SQLExecuteQueryOperator(
            task_id='initialize_schema',
            sql="""
            CREATE SCHEMA IF NOT EXISTS ecommerce_dwh;
            SET search_path = ecommerce_dwh;
            
            -- Dimension tables
            CREATE TABLE IF NOT EXISTS dim_date (
                date_key    DATE PRIMARY KEY,
                day         SMALLINT NOT NULL,
                month       SMALLINT NOT NULL,
                quarter     SMALLINT NOT NULL,
                year        SMALLINT NOT NULL,
                day_of_week VARCHAR(10) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dim_time (
                time_key TIME PRIMARY KEY,
                hour     SMALLINT NOT NULL,
                minute   SMALLINT NOT NULL,
                second   SMALLINT NOT NULL,
                am_pm    VARCHAR(2) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dim_product (
                product_key   SERIAL PRIMARY KEY,
                product_id    INT NOT NULL UNIQUE,
                product_name  TEXT NOT NULL,
                category_id   INT NOT NULL,
                category_name TEXT NOT NULL,
                price         NUMERIC(10,2) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dim_customer (
                customer_key SERIAL PRIMARY KEY,
                client_id    INT NOT NULL UNIQUE,
                full_name    TEXT NOT NULL,
                email        TEXT NOT NULL,
                signup_date  DATE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dim_payment_method (
                payment_method_key SERIAL PRIMARY KEY,
                method             VARCHAR(50) UNIQUE NOT NULL
            );
            
            -- Fact table
            CREATE TABLE IF NOT EXISTS fact_sales (
                sale_key           SERIAL PRIMARY KEY,
                sale_id            INT NOT NULL UNIQUE,
                date_key           DATE NOT NULL REFERENCES dim_date(date_key),
                time_key           TIME NOT NULL REFERENCES dim_time(time_key),
                product_key        INT NOT NULL REFERENCES dim_product(product_key),
                customer_key       INT NOT NULL REFERENCES dim_customer(customer_key),
                quantity           INT NOT NULL,
                total_amount       NUMERIC(10,2) NOT NULL,
                payment_method_key INT NOT NULL REFERENCES dim_payment_method(payment_method_key)
            );
            
            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_fact_date_key ON fact_sales(date_key);
            CREATE INDEX IF NOT EXISTS idx_fact_time_key ON fact_sales(time_key);
            CREATE INDEX IF NOT EXISTS idx_fact_product_key ON fact_sales(product_key);
            CREATE INDEX IF NOT EXISTS idx_fact_customer_key ON fact_sales(customer_key);
            CREATE INDEX IF NOT EXISTS idx_fact_pm_key ON fact_sales(payment_method_key);
            CREATE INDEX IF NOT EXISTS idx_fact_date_product ON fact_sales(date_key, product_key);
            """,
            conn_id='postgres_dwh',
            autocommit=True
        )

        # 2. Clean & load tasks
        tables = [
            ('dim_date', "SELECT * FROM ecommerce_dwh_star.dim_date"),
            ('dim_time', "SELECT * FROM ecommerce_dwh_star.dim_time"),
            ('dim_product', "SELECT * FROM ecommerce_dwh_star.dim_product"),
            ('dim_customer', "SELECT * FROM ecommerce_dwh_star.dim_customer"),
            ('dim_payment_method', "SELECT * FROM ecommerce_dwh_star.dim_payment_method"),
            ('fact_sales', "SELECT * FROM ecommerce_dwh_star.fact_sales")
        ]
        tasks = {}
        for table_name, sql_query in tables:
            tasks[table_name] = PythonOperator(
                task_id=f'clean_load_{table_name}',
                python_callable=clean_and_load,
                op_kwargs={
                    'table_name': table_name,
                    'sql_select': sql_query,
                    'target_schema': 'ecommerce_dwh',
                    'target_table': table_name
                }
            )

        # 3. Dépendances dimension → fact
        for dim in ['dim_date', 'dim_time', 'dim_product', 'dim_customer', 'dim_payment_method']:
            tasks[dim] >> tasks['fact_sales']

        # 4. Chaînage global
        initialize_schema >> list(tasks.values())

        return dag

dag = create_dag()
