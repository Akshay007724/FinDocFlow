"""FinDocFlow — Ablation Study Script

Runs the full evaluation for each ablation variant and produces a side-by-side
comparison table saved to experiments/results/ablation_summary.json.

Usage:
    python -m experiments.ablation
    python -m experiments.ablation --variants full no_graph no_verify --limit 20
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse evaluate module utilities
from experiments.evaluate import (
    DEFAULT_DATASET,
    DEFAULT_SERVICE_URL,
    RESULTS_DIR,
    aggregate_results,
    build_ablation_config,
    evaluate_single,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ablation")

ALL_VARIANTS = [
    "full",
    "no_graph",
    "no_chart",
    "no_hierarchy",
    "no_verify",
    "no_crossref",
]

# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------


def _fmt(value: Any, as_pct: bool = False) -> str:
    if value is None:
        return "—"
    if as_pct:
        return f"{float(value):.2%}"
    return f"{float(value):.4f}"


def print_markdown_table(summaries: dict[str, dict[str, Any]]) -> None:
    """Print a GitHub-flavored Markdown comparison table to stdout."""
    variants = list(summaries.keys())
    header = (
        "| Variant         | Accuracy | EGS    | MRR    | Avg Latency (s) | Evaluated |"
    )
    separator = (
        "|:----------------|:--------:|:------:|:------:|:---------------:|:---------:|"
    )

    print("\n### Ablation Study Results\n")
    print(header)
    print(separator)

    for variant in variants:
        s = summaries[variant]
        row = (
            f"| {variant:<15} "
            f"| {_fmt(s.get('accuracy'), as_pct=True):>8} "
            f"| {_fmt(s.get('egs')):>6} "
            f"| {_fmt(s.get('mrr')):>6} "
            f"| {_fmt(s.get('avg_latency_s')):>15} "
            f"| {s.get('evaluated', 0):>9} |"
        )
        print(row)

    print()

    # Per-difficulty breakdown
    first_summary = next(iter(summaries.values()))
    difficulties = sorted(first_summary.get("by_difficulty", {}).keys())
    if difficulties:
        print("#### Accuracy by Difficulty\n")
        diff_header = "| Variant         | " + " | ".join(f"{d:<6}" for d in difficulties) + " |"
        diff_sep = "|:----------------|" + "|".join(":------:" for _ in difficulties) + "|"
        print(diff_header)
        print(diff_sep)
        for variant in variants:
            s = summaries[variant]
            cells = []
            for d in difficulties:
                acc = s.get("by_difficulty", {}).get(d, {}).get("accuracy")
                cells.append(f"{_fmt(acc, as_pct=True):>6}")
            print(f"| {variant:<15} | " + " | ".join(cells) + " |")
        print()


# ---------------------------------------------------------------------------
# Delta column relative to "full" baseline
# ---------------------------------------------------------------------------


def compute_deltas(summaries: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    baseline = summaries.get("full")
    if not baseline:
        return {}
    deltas: dict[str, dict[str, float]] = {}
    for variant, s in summaries.items():
        if variant == "full":
            deltas[variant] = {"accuracy_delta": 0.0, "egs_delta": 0.0, "mrr_delta": 0.0}
            continue
        deltas[variant] = {
            "accuracy_delta": round(
                (s.get("accuracy", 0) or 0) - (baseline.get("accuracy", 0) or 0), 4
            ),
            "egs_delta": round(
                (s.get("egs", 0) or 0) - (baseline.get("egs", 0) or 0), 4
            ),
            "mrr_delta": round(
                (s.get("mrr", 0) or 0) - (baseline.get("mrr", 0) or 0), 4
            ),
        }
    return deltas


# ---------------------------------------------------------------------------
# Core ablation runner
# ---------------------------------------------------------------------------


def run_ablation(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = args.dataset
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        sys.exit(1)

    import json as _json

    with dataset_path.open() as fh:
        qa_pairs: list[dict[str, Any]] = _json.load(fh)

    if args.limit:
        qa_pairs = qa_pairs[: args.limit]
        logger.info("Limited to first %d questions", args.limit)

    if not qa_pairs:
        logger.error("No QA pairs loaded.")
        sys.exit(1)

    per_variant_results: dict[str, list[dict[str, Any]]] = {}
    per_variant_summaries: dict[str, dict[str, Any]] = {}

    for variant in args.variants:
        logger.info("=" * 60)
        logger.info("Running ablation variant: %s (%d questions)", variant, len(qa_pairs))
        logger.info("=" * 60)

        ablation_config = build_ablation_config(variant)
        results: list[dict[str, Any]] = []

        for i, qa in enumerate(qa_pairs, start=1):
            logger.info("[%s] [%d/%d] %s", variant, i, len(qa_pairs), qa["qa_id"])
            result = evaluate_single(qa, args.service_url, ablation_config, variant)
            results.append(result)

        summary = aggregate_results(results)
        per_variant_results[variant] = results
        per_variant_summaries[variant] = summary
        logger.info(
            "%s — acc=%.2f%% egs=%.4f mrr=%.4f",
            variant,
            (summary.get("accuracy") or 0) * 100,
            summary.get("egs") or 0,
            summary.get("mrr") or 0,
        )

    # Print markdown table
    print_markdown_table(per_variant_summaries)

    deltas = compute_deltas(per_variant_summaries)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ablation_output: dict[str, Any] = {
        "timestamp": timestamp,
        "dataset": str(dataset_path),
        "service_url": args.service_url,
        "variants_evaluated": args.variants,
        "summaries": per_variant_summaries,
        "deltas_vs_full": deltas,
        "per_variant_results": per_variant_results,
    }

    # Write summary JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "ablation_summary.json"
    with out_path.open("w") as fh:
        _json.dump(ablation_output, fh, indent=2)

    logger.info("Ablation summary written to %s", out_path)

    # Also write timestamped copy for archiving
    archive_path = RESULTS_DIR / f"ablation_{timestamp}.json"
    with archive_path.open("w") as fh:
        _json.dump(ablation_output, fh, indent=2)

    logger.info("Archived copy written to %s", archive_path)
    return ablation_output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run FinDocFlow ablation study across all model variants.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to the QA JSON file.",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=ALL_VARIANTS,
        choices=ALL_VARIANTS,
        help="Ablation variants to evaluate.",
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
        help="Limit evaluation to the first N QA pairs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout per request in seconds.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run_ablation(args)


if __name__ == "__main__":
    main()
