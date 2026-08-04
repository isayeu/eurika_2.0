#!/usr/bin/env python3
"""
Record learning outcomes for llm_extract_block operations from fix apply-from-report.

Run from project root: python scripts/record_llm_extract_outcomes.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAILED_OPS = [
    {"target_file": "eurika/analysis/metric_vector.py", "kind": "llm_extract_block"},
    {"target_file": "eurika/analysis/scoring.py", "kind": "llm_extract_block"},
    {"target_file": "eurika/api/explain_api.py", "kind": "llm_extract_block"},
]

SUCCESS_OPS = [
    {"target_file": "eurika/api/serve_routes_post.py", "kind": "llm_extract_block"},
]


def main() -> None:
    from eurika.storage import record_outcome

    # 3 failed: incomplete/broken LLM extraction (metric_vector truncated, scoring placeholder, explain placeholder)
    record_outcome(
        ROOT,
        [op["target_file"] for op in FAILED_OPS],
        FAILED_OPS,
        [],
        verify_success=False,
        failure_reason="incomplete_or_broken_llm_extract",
    )

    # 1 success: serve_routes_post was already correct
    record_outcome(
        ROOT,
        [op["target_file"] for op in SUCCESS_OPS],
        SUCCESS_OPS,
        [],
        verify_success=True,
    )

    print("Recorded: 3 llm_extract_block failures, 1 success")


if __name__ == "__main__":
    main()
