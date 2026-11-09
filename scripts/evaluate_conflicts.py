"""Evaluate HomeClaw conflict rules on the repository-owned labeled set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeclaw.domain import ActionProposal, DeviceRef  # noqa: E402
from homeclaw.eval.conflict_metrics import (  # noqa: E402
    ConflictExample,
    evaluate_conflict_detector,
)
from homeclaw.verification import ActionConflictDetector  # noqa: E402


def load_cases(path: Path) -> tuple[list[ConflictExample], list[str]]:
    cases = []
    case_ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        actions = []
        for item in raw["actions"]:
            expected = dict(item["expected"])
            actions.append(
                ActionProposal(
                    tool_name=item["tool"],
                    target=DeviceRef("evaluation-home", item["device_id"]),
                    arguments=dict(item.get("arguments", {})),
                    source_skill="conflict-evaluation",
                    expected_state=expected,
                    preconditions=tuple(item.get("preconditions", ())),
                    verification=dict(
                        item.get(
                            "verification",
                            {"path": next(iter(expected)), "equals": next(iter(expected.values()))},
                        )
                    ),
                    action_id=item["action_id"],
                )
            )
        cases.append(
            ConflictExample(
                actions,
                frozenset(raw["expected_codes"]),
                raw.get("dependencies", {}),
            )
        )
        case_ids.append(raw["case_id"])
    return cases, case_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/eval/conflict_gold.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/conflict-eval.json")
    args = parser.parse_args()
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    output = args.output if args.output.is_absolute() else ROOT / args.output
    dataset = dataset.resolve()
    output = output.resolve()
    if ROOT not in dataset.parents or ROOT not in output.parents:
        raise SystemExit("dataset and output must remain inside HomeClaw")
    examples, case_ids = load_cases(dataset)
    metrics = evaluate_conflict_detector(ActionConflictDetector(), examples)
    raw_data = dataset.read_bytes()
    report = {
        "provenance": {
            "kind": "homeclaw_synthetic_conflict_rule_evaluation",
            "dataset": str(dataset.relative_to(ROOT)),
            "sha256": hashlib.sha256(raw_data).hexdigest(),
            "warning": "Repository-owned synthetic rule coverage; not a KnowDetector paper result.",
        },
        "case_ids": case_ids,
        "metrics": {
            "sample_count": metrics.sample_count,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
            "exact_match": metrics.exact_match,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
