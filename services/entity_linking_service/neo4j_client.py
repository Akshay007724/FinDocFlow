"""Neo4j client for the entity knowledge graph."""
from __future__ import annotations

import logging
from typing import Optional

from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Manages Neo4j connection and graph operations."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def health_check(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ── Write operations ──────────────────────────────────────────────────

    def upsert_company(self, name: str, ticker: str | None = None, cik: str | None = None) -> str:
        query = """
        MERGE (c:Company {name: $name})
        SET c.ticker = coalesce($ticker, c.ticker),
            c.cik    = coalesce($cik, c.cik)
        RETURN elementId(c) AS node_id
        """
        with self._driver.session() as s:
            result = s.run(query, name=name, ticker=ticker, cik=cik)
            return result.single()["node_id"]

    def upsert_metric(self, name: str, unit: str | None = None) -> str:
        query = """
        MERGE (m:Metric {name: $name})
        SET m.unit = coalesce($unit, m.unit)
        RETURN elementId(m) AS node_id
        """
        with self._driver.session() as s:
            result = s.run(query, name=name, unit=unit)
            return result.single()["node_id"]

    def upsert_time_period(self, period: str) -> str:
        query = """
        MERGE (t:TimePeriod {period: $period})
        RETURN elementId(t) AS node_id
        """
        with self._driver.session() as s:
            result = s.run(query, period=period)
            return result.single()["node_id"]

    def link_company_metric(
        self,
        company_name: str,
        metric_name: str,
        period: str,
        value: str,
        doc_id: str,
        page_num: int,
    ) -> None:
        query = """
        MATCH (c:Company {name: $company})
        MATCH (m:Metric {name: $metric})
        MATCH (t:TimePeriod {period: $period})
        MERGE (c)-[r:REPORTED {period: $period, doc_id: $doc_id, page_num: $page_num}]->(m)
        SET r.value = $value,
            r.doc_id = $doc_id,
            r.page_num = $page_num
        MERGE (c)-[:IN_PERIOD]->(t)
        MERGE (m)-[:IN_PERIOD]->(t)
        """
        with self._driver.session() as s:
            s.run(query, company=company_name, metric=metric_name,
                  period=period, value=value, doc_id=doc_id, page_num=page_num)

    # ── Read operations ───────────────────────────────────────────────────

    def get_company_metrics(self, company_name: str) -> list[dict]:
        query = """
        MATCH (c:Company {name: $name})-[r:REPORTED]->(m:Metric)
        RETURN m.name AS metric, r.value AS value, r.period AS period,
               r.doc_id AS doc_id, r.page_num AS page_num
        ORDER BY r.period DESC
        LIMIT 100
        """
        with self._driver.session() as s:
            return [dict(record) for record in s.run(query, name=company_name)]

    def find_related_companies(self, company_name: str, metric_name: str) -> list[str]:
        query = """
        MATCH (c1:Company {name: $company})-[:REPORTED]->(m:Metric {name: $metric})
        MATCH (c2:Company)-[:REPORTED]->(m)
        WHERE c2.name <> $company
        RETURN DISTINCT c2.name AS company
        LIMIT 10
        """
        with self._driver.session() as s:
            return [r["company"] for r in s.run(query, company=company_name, metric=metric_name)]

    def get_cross_page_context(self, doc_id: str, metric_name: str) -> list[dict]:
        """Find all pages in a document that mention a given metric."""
        query = """
        MATCH (c:Company)-[r:REPORTED {doc_id: $doc_id}]->(m:Metric {name: $metric})
        RETURN c.name AS company, r.value AS value, r.period AS period, r.page_num AS page_num
        ORDER BY r.page_num
        """
        with self._driver.session() as s:
            return [dict(record) for record in s.run(query, doc_id=doc_id, metric=metric_name)]
