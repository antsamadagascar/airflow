from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.mysql.hooks.mysql import MySqlHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.task_group import TaskGroup
from datetime import datetime

# Schémas des tables RAW
RAW_TABLE_SCHEMAS = {
    "schema": """
        CREATE SCHEMA IF NOT EXISTS raw;
        SET search_path = raw;
    """,
    'categories_raw': """
                      CREATE TABLE IF NOT EXISTS raw.categories_raw
                      (
                          category_id TEXT,
                          name        TEXT
                      );
                      """,
    'products_raw': """
                    CREATE TABLE IF NOT EXISTS raw.products_raw
                    (
                        product_id  TEXT,
                        name        TEXT,
                        category_id TEXT,
                        price       TEXT
                    );
                    """,
    'clients_raw': """
                   CREATE TABLE IF NOT EXISTS raw.clients_raw
                   (
                       client_id  TEXT,
                       first_name TEXT,
                       last_name  TEXT,
                       email      TEXT,
                       created_at TEXT
                   );
                   """,
    'sales_raw': """
                 CREATE TABLE IF NOT EXISTS raw.sales_raw
                 (
                     sale_id        TEXT,
                     client_id      TEXT,
                     product_id     TEXT,
                     sale_date_time TEXT,
                     quantity       TEXT,
                     total_amount   TEXT
                 );
                 """,
    'inventory_raw': """
                     CREATE TABLE IF NOT EXISTS raw.inventory_raw
                     (
                         product_id        TEXT,
                         stock_quantity    TEXT,
                         reorder_threshold TEXT,
                         updated_at        TEXT
                     );
                     """,
    'payment_history_raw': """
                           CREATE TABLE IF NOT EXISTS raw.payment_history_raw
                           (
                               payment_id   TEXT,
                               sale_id      TEXT,
                               client_id    TEXT,
                               payment_date TEXT,
                               amount       TEXT,
                               method       TEXT,
                               status       TEXT
                           );
                           """
}


# Fonction pour préparer une table PostgreSQL
def prepare_table(hook, table_name):
    hook.run(RAW_TABLE_SCHEMAS[table_name])
    hook.run(f"TRUNCATE TABLE {table_name}")


# Fonction pour transférer une table de MySQL vers PostgreSQL
def transfer_table(source_table):
    def _transfer():
        target_table = f"{source_table}_raw"
        mysql_hook = MySqlHook(mysql_conn_id='mysql_ops')
        postgres_hook = PostgresHook(postgres_conn_id='postgres_raw')

        prepare_table(postgres_hook, target_table)

        records = mysql_hook.get_records(f"SELECT * FROM {source_table}")
        if records:
            postgres_hook.insert_rows(table=target_table, rows=records)

    return _transfer


# Fonction pour charger un fichier CSV dans PostgreSQL
def load_csv():
    postgres_hook = PostgresHook(postgres_conn_id='postgres_raw')
    target_table = 'payment_history_raw'

    prepare_table(postgres_hook, target_table)

    postgres_hook.copy_expert(
        sql=f"COPY {target_table} FROM STDIN WITH CSV HEADER DELIMITER ','",
        filename='/opt/airflow/resource/payment_history.csv'
    )


with DAG(
        dag_id='etl_ops_to_raw',
        start_date=datetime(2025, 4, 27),
        schedule='@daily',
        catchup=False,
        tags={'ecommerce', 'dwh'},  # étiquettes pour filtrage UI
) as dag:
    # Groupe de tâches pour le transfert des tables
    with TaskGroup(group_id='transfer_tables') as transfer_group:
        tables = ['categories', 'products', 'clients', 'sales', 'inventory']
        for table in tables:
            PythonOperator(
                task_id=f'transfer_{table}',
                python_callable=transfer_table(table),
            )

    # Tâche pour charger le fichier CSV
    load_csv_task = PythonOperator(
        task_id='load_csv_payment_history',
        python_callable=load_csv
    )

    # Définir les dépendances
    transfer_group >> load_csv_task
