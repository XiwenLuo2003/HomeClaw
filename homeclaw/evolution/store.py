"""Atomic local evidence-pack storage."""

from __future__ import annotations

import json
import os
from pathlib import Path

from homeclaw.evolution.models import EvidencePack


class EvidenceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, pack: EvidencePack) -> Path:
        target = (self.root / f"{pack.evidence_id}.json").resolve()
        if self.root not in target.parents:
            raise ValueError("evidence path escapes configured root")
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(pack.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target
