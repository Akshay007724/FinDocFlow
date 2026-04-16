"""PySpark batch job: aggregate entity metrics from Iceberg for analytics."""
from __future__ import annotations

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, avg, max as spark_max, min as spark_min

ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3a://findocflow/warehouse")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")


def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("FinDocFlow-EntityAggregator")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.findocflow", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.findocflow.type", "hadoop")
        .config("spark.sql.catalog.findocflow.warehouse", ICEBERG_WAREHOUSE)
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .getOrCreate()
    )


def run(spark: SparkSession) -> None:
    pages = spark.table("findocflow.documents.pages")
    entities = spark.table("findocflow.documents.entities")

    # Pages per layout type
    layout_stats = (
        pages.groupBy("layout_type", "filing_year")
        .agg(
            count("*").alias("page_count"),
            avg("word_count").alias("avg_word_count"),
        )
        .orderBy("filing_year", "layout_type")
    )
    layout_stats.writeTo("findocflow.analytics.layout_stats").createOrReplace()

    # Entity counts per company per year
    entity_stats = (
        entities.join(
            pages.select("doc_id", "company", "filing_year").distinct(),
            on="doc_id",
        )
        .groupBy("company", "filing_year", "entity_type")
        .agg(count("*").alias("entity_count"))
        .orderBy("company", "filing_year")
    )
    entity_stats.writeTo("findocflow.analytics.entity_stats").createOrReplace()

    print(f"Entity aggregation complete: {entity_stats.count()} rows written")


if __name__ == "__main__":
    spark = build_spark()
    run(spark)
    spark.stop()
