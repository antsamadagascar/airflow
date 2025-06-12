curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.0/docker-compose.yaml'

# Add the resource folder on volumes section in the YAML
#  volumes:
#    ...
#    - ${AIRFLOW_PROJ_DIR:-.}/resource:/opt/airflow/resource

mkdir ./dags ./logs ./config ./plugins ./resource

docker compose up airflow-init
docker compose up -d
# Default User : airflow/airflow


# Other commands 
docker compose down
docker compose restart


# Copy the csv flat file to Docker if needed 
docker exec -it airflow-worker mkdir -p /opt/airflow/resource

# Change the file path here ...
docker cp /home/aina-ny-antsa/Documents/FIANARANA/Semestre6/Mr NAINA/AirFLow/DWH/1-ecommerce_oltp/payment_history.csv airflow-worker:/opt/airflow/resource/payment_history.csv