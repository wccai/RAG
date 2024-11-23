import logging
import argparse
from pyspark.sql.dataframe import DataFrame
from pyspark.sql.types import (
    StructType,
    StructField,
    ArrayType,
    FloatType,
    StringType,
)
from pyspark.sql import SparkSession
from llama_index.embeddings.ollama import OllamaEmbedding
from util.oss2_client import OSS2Client


logger = logging.getLogger("my_logger")
logger.setLevel(logging.INFO)  # Set the logging level
console_handler = logging.StreamHandler()
# Create a formatter and set it for both handlers
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
# Add the handler to the logger
logger.addHandler(console_handler)

# need to set the following environment variables:
# Initialize a SparkSession
spark = SparkSession.builder.master("local[*]").appName("get_embedding").getOrCreate()
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
parser.add_argument("--exec_date", help="Execution Date", required=True)
parser.add_argument(
    "--input_object_path", help="Input Object Path on OSS2", required=True
)
parser.add_argument(
    "--output_object_path", help="Output Object Path on OSS2", required=True
)
args = parser.parse_args()

# Set up input/output variables
exec_date: str = args.exec_date
input_object_path: str = args.input_object_path
output_object_path: str = args.output_object_path
part_cnt: int = 0
ollama_embedding = OllamaEmbedding(model_name="gemma:2b")

# Read Reddit data from cloud
df_spark: DataFrame = spark.read.parquet(
    f"oss://{oss2_bucket_name}/{input_object_path}"
)
df_spark.show()

df_spark_game_hardware = df_spark.filter(
    (df_spark.text.contains("game")) & (df_spark.text.contains("hardware"))
)
logger.info(f"df_game_hardware count: {df_spark_game_hardware.count()}")
df_spark_game_hardware.show()


def split_text_into_chunks(text, chunk_size=512):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


# Function to process each partition (batch) with llm
def process_batch(iterator):
    texts = [row.text for row in iterator]
    all_chunks = []
    for long_text in texts:
        chunks = split_text_into_chunks(long_text[:5120], chunk_size=512)
        all_chunks.extend(chunks)

    embeddings = ollama_embedding.get_text_embedding_batch(
        all_chunks, show_progress=False
    )  # Get embeddings for the batch
    for chunk, em in zip(all_chunks, embeddings):
        em = [float(each) for each in em]
        yield chunk, em


# Apply the batch processing to the Spark DataFrame
embeddings_rdd = df_spark_game_hardware.rdd.mapPartitions(process_batch)

# Convert the RDD back to a DataFrame with embeddings
df_schema = StructType(
    [
        StructField("chunk", StringType(), False),
        StructField("embedding", ArrayType(FloatType()), True),
    ]
)
embeddings_df: DataFrame = spark.createDataFrame(embeddings_rdd, df_schema)
embeddings_df.show(truncate=False, vertical=True)
embeddings_df.write.option("compression", "zstd").mode("overwrite").parquet(
    f"oss://{oss2_bucket_name}/{output_object_path}"
)
