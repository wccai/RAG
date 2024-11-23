# download ES
# https://www.elastic.co/downloads/elasticsearch

import logging
import time
import numpy as np
import argparse
import os
from pyspark.sql import SparkSession
from pyspark import TaskContext
from util.oss2_client import OSS2Client
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


logger = logging.getLogger("my_logger")
logger.setLevel(logging.INFO)  # Set the logging level
console_handler = logging.StreamHandler()
# Create a formatter and set it for both handlers
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
# Add the handler to the logger
logger.addHandler(console_handler)


# Initialize a SparkSession
spark = (
    SparkSession.builder.master("local[*]")
    .appName("update_search_index_for_embedding")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("INFO")
hadoop_conf = spark._jsc.hadoopConfiguration()
hadoop_conf.set("fs.oss.impl", "org.apache.hadoop.fs.aliyun.oss.AliyunOSSFileSystem")
hadoop_conf.set("fs.oss.accessKeyId", "...")
hadoop_conf.set("fs.oss.accessKeySecret", "...")
hadoop_conf.set("fs.oss.endpoint", "...")
hadoop_conf.set("fs.oss.bucket_name", "...")

oss2client: OSS2Client = OSS2Client()
oss2_bucket_name: str = "..."

# Get passed in arguments
parser = argparse.ArgumentParser()
parser.add_argument(
    "--input_object_path", help="Input Object Path on OSS2", required=True
)
args = parser.parse_args()

# Set up input/output variables
# Input variables
input_object_path: str = args.input_object_path

# Get configure from environment variables
es_host: str = os.getenv("es_host", "...")
es_admin: str = os.getenv("es_admin", "...")
es_pass: str = os.getenv("es_pass", "...")
es_em_index: str = os.getenv("es_em_index", "...")
em_dim: int = int(
    os.getenv("em_dim", 2048)
)  # Elasticsearch supports at most 2048, so that's why we don't use llama 3

# Load embedding from parquet files
df_em = spark.read.parquet(f"oss://{oss2_bucket_name}/{input_object_path}")
logger.info(f"Totally {df_em.count()} embeddings to index")

df_em.show()

# Create or update embedding
es: Elasticsearch = Elasticsearch(
    hosts=es_host,
    basic_auth=(es_admin, es_pass),
)
if not es.indices.exists(index=es_em_index):  # Create new index
    # Define index mapping
    index_mapping = {
        "properties": {
            "em": {
                "type": "dense_vector",
                "dims": em_dim,  # Dimensionality of the vector
                "index": True,
                "similarity": "cosine",
            },
            "chunk": {"type": "text", "index": False},
        }
    }
    # Create the index
    es.indices.create(index=es_em_index, mappings=index_mapping)
es.close()


# Batch indexing is more efficient
def index_batch(
    es: Elasticsearch,
    batch: list,
    max_retry: int,
    total_indexed_cnt: int,
    update_total_indexed_cnt: bool,
    partition_id: int,
) -> int:
    retry: int = 0
    while retry < max_retry:
        try:
            success, failed = bulk(es, batch)
            if len(failed) > 0:
                retry += 1
                print(
                    f"Failed to index {len(failed)} documents for partition {partition_id}, retry {retry}"
                )
            else:
                break
        except Exception as ex:
            retry += 1
            print(f"Index error: {ex} for partition {partition_id}, retry {retry}")
    if update_total_indexed_cnt:
        total_indexed_cnt += len(batch)
    print(f"Indexed {total_indexed_cnt} for partition {partition_id}")
    return total_indexed_cnt


# Insert embedding into the ES index
df_repartitioned = df_em.repartition(3)


def index_em_batch(partition):
    total_indexed_cnt: int = 0
    batch_size: int = 300
    batch: list = []
    max_retry: int = 3

    es_usa_in_partition: Elasticsearch = Elasticsearch(
        hosts=es_host,
        basic_auth=(es_admin, es_pass),
    )

    partition_id: int = TaskContext.get().partitionId()
    count: int = 0
    for row in partition:
        count += 1
        chunk: str = str(row["chunk"])
        em: np.array = (np.array(row["embedding"]) * 100000 + 0.5).astype(int) / 100000
        if total_indexed_cnt == 0:
            print(
                f"Indexing embedding row with chunk: {chunk[:10]}..., em: {em[:5]}..."
            )
        batch.append(
            {
                "_index": es_em_index,
                "_source": {"em": em, "chunk": chunk},
            }
        )

        if len(batch) >= batch_size:
            total_indexed_cnt = index_batch(
                es_usa_in_partition,
                batch,
                max_retry,
                total_indexed_cnt,
                True,
                partition_id,
            )

            batch = []
            time.sleep(1)  # slow down a little bit   # Replica and Sharding
    if len(batch) > 0:
        total_indexed_cnt = index_batch(
            es_usa_in_partition,
            batch,
            max_retry,
            total_indexed_cnt,
            True,
            partition_id,
        )

    es_usa_in_partition.close()
    print(
        f"Indexed {count} embeddings for partition {partition_id}"
    )  # logger.info does not work in for partition function


# Use foreachPartition to index embeddings in each partition
df_repartitioned.foreachPartition(index_em_batch)
