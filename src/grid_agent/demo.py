"""Case loading and human-readable rendering helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .diagnosis import FaultDiagnoser, FaultDiagnosis
from .model import FeederCase


def load_case(path: str | Path) -> FeederCase:
    case_path = Path(path)
    with case_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("case JSON root must be an object")
    return FeederCase.from_dict(payload)


def run_case(path: str | Path) -> FaultDiagnosis:
    return FaultDiagnoser().diagnose(load_case(path))


def render_text(result: FaultDiagnosis, *, candidate_limit: int = 5) -> str:
    lines = [
        f"馈线：{result.feeder_name}",
        f"最可能故障支路：{result.likely_branch_name} ({result.likely_branch_id})",
        f"置信度：{result.confidence:.1%}",
        "",
        "候选排序：",
    ]
    for index, candidate in enumerate(result.candidates[:candidate_limit], start=1):
        lines.append(
            f"  {index}. {candidate.branch_name} ({candidate.branch_id}) "
            f"score={candidate.score:.4f}"
        )
        for evidence in candidate.evidence:
            lines.append(
                f"     - {evidence.name}: +{evidence.contribution:.4f}; {evidence.detail}"
            )

    lines.extend(["", "建议："])
    lines.extend(f"  - {item}" for item in result.recommendations)
    lines.extend(["", "限制："])
    lines.extend(f"  - {item}" for item in result.limitations)
    return "\n".join(lines)
