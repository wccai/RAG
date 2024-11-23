import os
import airflow
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from util.oss2_client import OSS2Client
from datetime import timedelta, datetime
from airflow import DAG


# Get configure from environment variables
get_embedding_schedule = os.getenv(
    "get_embedding_schedule", "0 5 * * *"
).replace(  # set up schedule with cronjob style string https://crontab.guru
    "_", " "
)
print(f"Running schedule for batch embedding: {get_embedding_schedule}")

# Set up local variables
oss2client: OSS2Client = OSS2Client()
exec_date: str = (datetime.now().date()).strftime("%Y-%m-%d")
# need to check the file path
reddit_data_object_path: str = "llm/reddit_answers_long.parquet"
em_object_path: str = f"llm/{exec_date}/llm_em.parquet"

default_args = {
    "owner": "airflow",
    "execution_timeout": timedelta(
        minutes=360
    ),  # Set the default execution timeout for all tasks
    "timezone": "Asia/Shanghai",  # Set your desired time zone here
}

dag = DAG(
    dag_id="get_embedding_daily",
    default_args=default_args,
    start_date=airflow.utils.dates.days_ago(1),
    schedule_interval=get_embedding_schedule,
    max_active_runs=1,
    catchup=False,
)

# for local testing only
task_get_embedding = SparkSubmitOperator(
    task_id="get_embedding",
    application="airflow/dags/get_embedding.py",
    conn_id="spark_default",
    conf={
        "spark.master": "local[*]",  # Specify local mode with all available cores
        "spark.driver.memory": "4g", # specify driver memory, default is not enough 
        "spark.executor.memory": "8g",
        "spark.executor.instances": "2",
        "spark.app.name": "get_embedding",
    },
    jars="airflow/dags/jars/*.jar",
    py_files="airflow/dags/util/oss2_client.py",
    application_args=[
        "--exec_date",
        exec_date,
        "--input_object_path",
        reddit_data_object_path,
        "--output_object_path",
        em_object_path,
    ],
    dag=dag,
)

task_update_search_index_for_embedding = SparkSubmitOperator(
    task_id="update_search_index_for_embedding",
    application="airflow/dags/update_search_index_for_embedding.py",
    conn_id="spark_default",
    conf={
        "spark.master": "local[*]",  # Specify local mode with all available cores
        "spark.driver.memory": "2g",
        "spark.executor.memory": "2g",
        "spark.executor.instances": "2",
        "spark.app.name": "update_search_index_for_embedding",
    },
    jars="airflow/dags/jars/*.jar",
    py_files="airflow/dags/util/oss2_client.py",
    application_args=[
        "--input_object_path",
        em_object_path,
    ],
    dag=dag,
)

task_get_embedding >> task_update_search_index_for_embedding
