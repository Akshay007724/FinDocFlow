"""PySpark job: consume linked_documents Kafka topic → write to Iceberg on MinIO."""
from __future__ import annotations

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, explode, lit, current_timestamp
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    BooleanType, ArrayType, FloatType, MapType
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC_LINKED", "linked_documents")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3a://findocflow/warehouse")

PAGE_SCHEMA = StructType([
    StructField("page_num", IntegerType()),
    StructField("text", StringType()),
    StructField("layout_type", StringType()),
    StructField("word_count", IntegerType()),
    StructField("has_tables", BooleanType()),
    StructField("has_images", BooleanType()),
    StructField("width", FloatType()),
    StructField("height", FloatType()),
])

DOC_SCHEMA = StructType([
    StructField("doc_id", StringType()),
    StructField("filename", StringType()),
    StructField("format", StringType()),
    StructField("total_pages", IntegerType()),
    StructField("company", StringType()),
    StructField("filing_year", IntegerType()),
    StructField("pages", ArrayType(PAGE_SCHEMA)),
    StructField("entity_count", IntegerType()),
    StructField("linking_complete", BooleanType()),
])


def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("FinDocFlow-DocumentProcessor")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.findocflow", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.findocflow.type", "hadoop")
        .config("spark.sql.catalog.findocflow.warehouse", ICEBERG_WAREHOUSE)
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .getOrCreate()
    )


def create_tables(spark: SparkSession) -> None:
    spark.sql("""
        CREATE TABLE IF NOT EXISTS findocflow.documents.pages (
            doc_id        STRING,
            filename      STRING,
            format        STRING,
            company       STRING,
            filing_year   INT,
            page_num      INT,
            text          STRING,
            layout_type   STRING,
            word_count    INT,
            has_tables    BOOLEAN,
            has_images    BOOLEAN,
            processed_at  TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (filing_year, layout_type)
    """)

    spark.sql("""
        CREATE TABLE IF NOT EXISTS findocflow.documents.entities (
            doc_id     STRING,
            page_num   INT,
            entity_type STRING,
            entity_text STRING,
            value       STRING,
            period      STRING,
            processed_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (entity_type)
    """)


def run_streaming(spark: SparkSession) -> None:
    raw_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .load()
    )

    docs_df = raw_df.select(
        from_json(col("value").cast("string"), DOC_SCHEMA).alias("doc")
    ).select("doc.*")

    # Explode pages → one row per page
    pages_df = (
        docs_df
        .withColumn("page", explode(col("pages")))
        .select(
            col("doc_id"),
            col("filename"),
            col("format"),
            col("company"),
            col("filing_year"),
            col("page.page_num").alias("page_num"),
            col("page.text").alias("text"),
            col("page.layout_type").alias("layout_type"),
            col("page.word_count").alias("word_count"),
            col("page.has_tables").alias("has_tables"),
            col("page.has_images").alias("has_images"),
            current_timestamp().alias("processed_at"),
        )
    )

    query = (
        pages_df.writeStream
        .format("iceberg")
        .outputMode("append")
        .option("path", "findocflow.documents.pages")
        .option("checkpointLocation", f"{ICEBERG_WAREHOUSE}/_checkpoints/pages")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    spark = build_spark()
    create_tables(spark)
    run_streaming(spark)
