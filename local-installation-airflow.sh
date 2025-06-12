python3 -m venv airflow_env

source ./airflow_env/bin/activate

pip install --upgrade pip

export AIRFLOW_VERSION=3.0.0
PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
export PYTHON_VERSION
export CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
export no_proxy='*'
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

uv pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"

pip install apache-airflow-providers-mysql apache-airflow-providers-postgres apache-airflow-providers-common-sql

## For macOs only ##################
brew install mysql-client pkg-config
export PKG_CONFIG_PATH="/opt/homebrew/opt/mysql-client/lib/pkgconfig:$PKG_CONFIG_PATH"
export LDFLAGS="-L/opt/homebrew/opt/mysql-client/lib"
export CPPFLAGS="-I/opt/homebrew/opt/mysql-client/include"
export PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"
###################################

pip install mysqlclient


pip install mysqlclient

# Start AirFlow on localhost:8080
#airflow standalone

