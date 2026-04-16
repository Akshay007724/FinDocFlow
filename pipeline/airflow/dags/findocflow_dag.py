"""Airflow DAG: daily SEC EDGAR → FinDocFlow pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.http.operators.http import SimpleHttpOperator

default_args = {
    "owner": "findocflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

INGESTION_HOST = "ingestion"
INGESTION_PORT = 8001

SEC_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "WMT",
]
SEC_BASE_URL = "https://data.sec.gov/submissions"


def fetch_sec_urls(**context) -> list[str]:
    """Fetch latest 10-K filing URLs from SEC EDGAR for configured tickers."""
    import httpx
    import json

    urls = []
    for ticker in SEC_TICKERS:
        try:
            # CIK lookup
            lookup_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2023-01-01&forms=10-K"
            resp = httpx.get(lookup_url, timeout=10, headers={"User-Agent": "FinDocFlow research@findocflow.ai"})
            data = resp.json()
            for hit in data.get("hits", {}).get("hits", [])[:2]:
                filing_url = hit.get("_source", {}).get("file_date")
                if filing_url:
                    urls.append(filing_url)
        except Exception as e:
            print(f"Failed to fetch {ticker}: {e}")

    context["ti"].xcom_push(key="sec_urls", value=urls)
    return urls


def batch_ingest(**context) -> None:
    """Call ingestion service batch endpoint with fetched URLs."""
    import httpx

    urls = context["ti"].xcom_pull(key="sec_urls", task_ids="fetch_sec_urls")
    if not urls:
        print("No URLs to ingest")
        return

    filing_year = datetime.now().year - 1  # last fiscal year

    resp = httpx.post(
        f"http://{INGESTION_HOST}:{INGESTION_PORT}/ingest/batch",
        json={"urls": urls, "filing_year": filing_year},
        timeout=300,
    )
    resp.raise_for_status()
    job = resp.json()
    print(f"Batch job created: {job['job_id']}")
    context["ti"].xcom_push(key="batch_job_id", value=job["job_id"])


def wait_for_ingestion(**context) -> None:
    """Poll ingestion job status until done or failed."""
    import httpx
    import time

    job_id = context["ti"].xcom_pull(key="batch_job_id", task_ids="batch_ingest")
    if not job_id:
        return

    for _ in range(60):  # max 5 minutes
        resp = httpx.get(
            f"http://{INGESTION_HOST}:{INGESTION_PORT}/ingest/status/{job_id}",
            timeout=10,
        )
        status = resp.json()
        print(f"Job {job_id}: {status['status']} ({status['progress']}%)")
        if status["status"] in ("done", "failed"):
            if status["status"] == "failed":
                raise RuntimeError(f"Ingestion failed: {status['message']}")
            return
        time.sleep(5)

    raise TimeoutError(f"Job {job_id} timed out")


with DAG(
    dag_id="findocflow_daily_pipeline",
    default_args=default_args,
    description="Daily SEC EDGAR ingestion → extraction → entity linking → Iceberg",
    schedule="0 6 * * *",  # 6 AM UTC daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["findocflow", "sec", "pipeline"],
) as dag:

    t_fetch = PythonOperator(
        task_id="fetch_sec_urls",
        python_callable=fetch_sec_urls,
    )

    t_ingest = PythonOperator(
        task_id="batch_ingest",
        python_callable=batch_ingest,
    )

    t_wait = PythonOperator(
        task_id="wait_for_ingestion",
        python_callable=wait_for_ingestion,
    )

    t_spark = BashOperator(
        task_id="run_spark_aggregation",
        bash_command=(
            "spark-submit "
            "--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,"
            "org.apache.hadoop:hadoop-aws:3.3.4 "
            "/opt/spark/jobs/entity_aggregator.py"
        ),
    )

    t_fetch >> t_ingest >> t_wait >> t_spark
