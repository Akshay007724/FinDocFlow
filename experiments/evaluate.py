"""FinDocFlow — Main Evaluation Script

Loads QA pairs from dataset/sample_qa.json, calls the reasoning service, and
computes Accuracy, EGS (Evidence Grounding Score), and MRR.

Usage:
    python -m experiments.evaluate --model full
    python -m experiments.evaluate --dataset path/to/qa.json --model no_graph --service-url http://localhost:8004
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("evaluate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_DATASET = Path(__file__).parent.parent / "dataset" / "sample_qa.json"
DEFAULT_SERVICE_URL = os.getenv("REASONING_SERVICE_URL", "http://localhost:8004")

ABLATION_VARIANTS = [
    "full",
    "no_graph",
    "no_chart",
    "no_hierarchy",
    "no_verify",
    "no_crossref",
]

BERTSCORE_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# BERTScore helper (lazy import so the script still works without bert_score)
# ---------------------------------------------------------------------------


def _bertscore_f1(candidate: str, reference: str) -> float:
    """Return BERTScore F1 between candidate and reference.

    Falls back to a simple token-overlap F1 when bert_score is not installed.
    """
    try:
        from bert_score import score as bert_score  # type: ignore

        P, R, F = bert_score([candidate], [reference], lang="en", verbose=False)
        return float(F[0])
    except ImportError:
        logger.warning(
            "bert_score not installed — falling back to token-overlap F1 for text answers."
        )
        return _token_overlap_f1(candidate, reference)


def _token_overlap_f1(pred: str, ref: str) -> float:
    pred_tokens = set(re.sub(r"[^a-z0-9]", " ", pred.lower()).split())
    ref_tokens = set(re.sub(r"[^a-z0-9]", " ", ref.lower()).split())
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = pred_tokens & ref_tokens
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------------------
# Numeric exact-match with tolerance
# ---------------------------------------------------------------------------


def _numeric_match(pred_text: str, reference_numeric: float, tol: float = 0.02) -> bool:
    """Return True if any number found in pred_text is within tol of reference_numeric."""
    numbers = re.findall(r"-?\d+(?:\.\d+)?", pred_text.replace(",", ""))
    for n in numbers:
        try:
            val = float(n)
            if reference_numeric != 0:
                if abs(val - reference_numeric) / abs(reference_numeric) <= tol:
                    return True
            else:
                if abs(val) <= tol:
                    return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Evidence Grounding Score
# ---------------------------------------------------------------------------


def _evidence_grounding_score(cited_pages: list[int], supporting_pages: list[int]) -> float:
    """Fraction of supporting pages that appear in the model's cited pages."""
    if not supporting_pages:
        return 1.0  # vacuously true
    cited_set = set(cited_pages)
    support_set = set(supporting_pages)
    if not cited_set:
        return 0.0
    recall = len(cited_set & support_set) / len(support_set)
    return round(recall, 4)


# ---------------------------------------------------------------------------
# Reasoning service client
# ---------------------------------------------------------------------------


def call_reasoning_service(
    service_url: str,
    doc_id: str,
    question: str,
    ablation_config: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """POST to /answer on the reasoning service and return the JSON response.

    The /answer endpoint is a convenience wrapper that internally fetches
    document pages for the given doc_id and runs the THINK→ACT→VERIFY loop.
    An optional X-Ablation-Config header carries the ablation configuration.
    """
    url = f"{service_url.rstrip('/')}/answer"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if ablation_config:
        headers["X-Ablation-Config"] = json.dumps(ablation_config)

    payload = {"doc_id": doc_id, "question": question}

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "HTTP %s from reasoning service for doc_id=%s: %s",
            exc.response.status_code,
            doc_id,
            exc.response.text[:300],
        )
        raise
    except httpx.RequestError as exc:
        logger.error("Request error calling %s: %s", url, exc)
        raise


# ---------------------------------------------------------------------------
# MRR helper
# ---------------------------------------------------------------------------


def _reciprocal_rank(cited_pages: list[int], supporting_pages: list[int]) -> float:
    """Return the reciprocal rank of the first correctly cited page."""
    for rank, page in enumerate(cited_pages, start=1):
        if page in supporting_pages:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------------------
# Per-question evaluation
# ---------------------------------------------------------------------------


def evaluate_single(
    qa: dict[str, Any],
    service_url: str,
    ablation_config: dict[str, Any] | None,
    model: str,
) -> dict[str, Any]:
    qa_id = qa["qa_id"]
    doc_id = qa["doc_id"]
    question = qa["question"]
    reference_answer = qa["answer"]
    answer_numeric = qa.get("answer_numeric")
    supporting_pages = qa.get("supporting_pages", [])

    result: dict[str, Any] = {
        "qa_id": qa_id,
        "doc_id": doc_id,
        "question_type": qa.get("question_type", "unknown"),
        "difficulty": qa.get("difficulty", "unknown"),
        "modalities_used": qa.get("modalities_used", []),
        "model": model,
        "predicted_answer": None,
        "cited_pages": [],
        "confidence": None,
        "latency_s": None,
        "accuracy": False,
        "egs": 0.0,
        "mrr": 0.0,
        "bertscore_f1": None,
        "error": None,
    }

    t0 = time.perf_counter()
    try:
        response = call_reasoning_service(service_url, doc_id, question, ablation_config)
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning("Skipping %s due to error: %s", qa_id, exc)
        return result

    latency = time.perf_counter() - t0
    result["latency_s"] = round(latency, 3)

    predicted_answer: str = response.get("answer", "")
    cited_pages: list[int] = response.get("cited_pages", [])
    result["predicted_answer"] = predicted_answer
    result["cited_pages"] = cited_pages
    result["confidence"] = response.get("confidence")

    # --- Accuracy -----------------------------------------------------------
    if answer_numeric is not None:
        result["accuracy"] = _numeric_match(predicted_answer, answer_numeric)
    else:
        bf1 = _bertscore_f1(predicted_answer, reference_answer)
        result["bertscore_f1"] = round(bf1, 4)
        result["accuracy"] = bf1 >= BERTSCORE_THRESHOLD

    # --- Evidence Grounding Score -------------------------------------------
    result["egs"] = _evidence_grounding_score(cited_pages, supporting_pages)

    # --- MRR ----------------------------------------------------------------
    result["mrr"] = _reciprocal_rank(cited_pages, supporting_pages)

    logger.info(
        "%s | acc=%s | egs=%.2f | mrr=%.2f | latency=%.1fs",
        qa_id,
        result["accuracy"],
        result["egs"],
        result["mrr"],
        latency,
    )
    return result


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in results if r["error"] is None]
    if not valid:
        return {"error": "All questions failed"}

    accuracy = sum(1 for r in valid if r["accuracy"]) / len(valid)
    egs = sum(r["egs"] for r in valid) / len(valid)
    mrr = sum(r["mrr"] for r in valid) / len(valid)
    avg_latency = sum(r["latency_s"] for r in valid) / len(valid)

    by_difficulty: dict[str, dict[str, float]] = {}
    for diff in ("easy", "medium", "hard"):
        subset = [r for r in valid if r.get("difficulty") == diff]
        if subset:
            by_difficulty[diff] = {
                "count": len(subset),
                "accuracy": round(sum(1 for r in subset if r["accuracy"]) / len(subset), 4),
                "egs": round(sum(r["egs"] for r in subset) / len(subset), 4),
                "mrr": round(sum(r["mrr"] for r in subset) / len(subset), 4),
            }

    by_qtype: dict[str, dict[str, float]] = {}
    qtypes = {r["question_type"] for r in valid}
    for qt in qtypes:
        subset = [r for r in valid if r["question_type"] == qt]
        by_qtype[qt] = {
            "count": len(subset),
            "accuracy": round(sum(1 for r in subset if r["accuracy"]) / len(subset), 4),
            "egs": round(sum(r["egs"] for r in subset) / len(subset), 4),
        }

    return {
        "total_questions": len(results),
        "evaluated": len(valid),
        "errors": len(results) - len(valid),
        "accuracy": round(accuracy, 4),
        "egs": round(egs, 4),
        "mrr": round(mrr, 4),
        "avg_latency_s": round(avg_latency, 3),
        "by_difficulty": by_difficulty,
        "by_question_type": by_qtype,
    }


# ---------------------------------------------------------------------------
# Summary table printer
# ---------------------------------------------------------------------------


def print_summary_table(summary: dict[str, Any], model: str) -> None:
    print("\n" + "=" * 60)
    print(f"  FinDocFlow Evaluation — model: {model}")
    print("=" * 60)
    print(f"  Questions evaluated : {summary.get('evaluated', 0)} / {summary.get('total_questions', 0)}")
    print(f"  Accuracy            : {summary.get('accuracy', 0):.2%}")
    print(f"  EGS (evidence)      : {summary.get('egs', 0):.4f}")
    print(f"  MRR                 : {summary.get('mrr', 0):.4f}")
    print(f"  Avg latency         : {summary.get('avg_latency_s', 0):.2f}s")
    print("-" * 60)

    by_diff = summary.get("by_difficulty", {})
    if by_diff:
        print("  By difficulty:")
        for diff, metrics in sorted(by_diff.items()):
            print(
                f"    {diff:<8}  acc={metrics['accuracy']:.2%}  "
                f"egs={metrics['egs']:.3f}  mrr={metrics['mrr']:.3f}  "
                f"n={metrics['count']}"
            )

    by_qt = summary.get("by_question_type", {})
    if by_qt:
        print("  By question type:")
        for qt, metrics in sorted(by_qt.items()):
            print(
                f"    {qt:<30}  acc={metrics['accuracy']:.2%}  "
                f"egs={metrics['egs']:.3f}  n={metrics['count']}"
            )
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Ablation config factory
# ---------------------------------------------------------------------------


def build_ablation_config(model: str) -> dict[str, Any]:
    """Return a config dict that the reasoning service respects via X-Ablation-Config."""
    defaults = {
        "use_graph": True,
        "use_charts": True,
        "use_hierarchy": True,
        "use_verify": True,
        "use_crossref": True,
    }
    overrides: dict[str, dict[str, bool]] = {
        "full": {},
        "no_graph": {"use_graph": False},
        "no_chart": {"use_charts": False},
        "no_hierarchy": {"use_hierarchy": False},
        "no_verify": {"use_verify": False},
        "no_crossref": {"use_crossref": False},
        "bm25": {"use_graph": False, "use_charts": False, "use_hierarchy": False, "use_verify": False},
        "dense": {"use_graph": False, "use_charts": False, "use_hierarchy": False, "use_verify": False},
        "llm_only": {
            "use_graph": False,
            "use_charts": False,
            "use_hierarchy": False,
            "use_verify": False,
            "use_crossref": False,
        },
        "gpt4": {},
    }
    cfg = {**defaults, **overrides.get(model, {})}
    cfg["model_variant"] = model
    return cfg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate FinDocFlow reasoning service on a QA dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to the QA JSON file.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="full",
        choices=[
            "full",
            "no_graph",
            "no_chart",
            "no_hierarchy",
            "no_verify",
            "no_crossref",
            "bm25",
            "dense",
            "llm_only",
            "gpt4",
        ],
        help="Model/ablation variant to evaluate.",
    )
    parser.add_argument(
        "--service-url",
        type=str,
        default=DEFAULT_SERVICE_URL,
        help="Base URL of the reasoning service.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit evaluation to the first N QA pairs (useful for smoke tests).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds per request.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESULTS_DIR,
        help="Directory to write result JSON files.",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Filter QA pairs to a single doc_id.",
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        default=None,
        choices=["easy", "medium", "hard"],
        help="Filter QA pairs by difficulty.",
    )
    return parser.parse_args(argv)


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = args.dataset
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        sys.exit(1)

    logger.info("Loading dataset from %s", dataset_path)
    with dataset_path.open() as fh:
        qa_pairs: list[dict[str, Any]] = json.load(fh)

    # Optional filters
    if args.doc_id:
        qa_pairs = [q for q in qa_pairs if q["doc_id"] == args.doc_id]
        logger.info("Filtered to doc_id=%s: %d questions", args.doc_id, len(qa_pairs))
    if args.difficulty:
        qa_pairs = [q for q in qa_pairs if q.get("difficulty") == args.difficulty]
        logger.info("Filtered to difficulty=%s: %d questions", args.difficulty, len(qa_pairs))
    if args.limit:
        qa_pairs = qa_pairs[: args.limit]
        logger.info("Limited to first %d questions", args.limit)

    if not qa_pairs:
        logger.error("No QA pairs to evaluate after filtering.")
        sys.exit(1)

    ablation_config = build_ablation_config(args.model)
    logger.info(
        "Running evaluation: model=%s, questions=%d, service=%s",
        args.model,
        len(qa_pairs),
        args.service_url,
    )

    results: list[dict[str, Any]] = []
    for i, qa in enumerate(qa_pairs, start=1):
        logger.info("[%d/%d] Evaluating %s", i, len(qa_pairs), qa["qa_id"])
        result = evaluate_single(qa, args.service_url, ablation_config, args.model)
        results.append(result)

    summary = aggregate_results(results)
    print_summary_table(summary, args.model)

    # Write results to disk
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.output_dir / f"{args.model}_{timestamp}.json"

    output = {
        "model": args.model,
        "timestamp": timestamp,
        "dataset": str(dataset_path),
        "service_url": args.service_url,
        "ablation_config": ablation_config,
        "summary": summary,
        "results": results,
    }

    with out_path.open("w") as fh:
        json.dump(output, fh, indent=2)

    logger.info("Results written to %s", out_path)
    return output


def main() -> None:
    args = parse_args()
    run_evaluation(args)


if __name__ == "__main__":
    main()
