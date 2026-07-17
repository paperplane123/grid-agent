"""Command-line interface for grid-agent."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .demo import render_text, run_case
from .society import render_simulation_text, run_simulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grid-agent",
        description="配电网故障诊断与物理—认知多智能体仿真工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser("diagnose", help="诊断一个 JSON 馈线案例")
    diagnose.add_argument("case", help="案例 JSON 文件路径")
    diagnose.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式，默认 text",
    )
    diagnose.add_argument(
        "--candidate-limit",
        type=int,
        default=5,
        help="文本模式最多展示多少个候选支路",
    )

    simulate = subparsers.add_parser(
        "simulate",
        help="运行一个 GridSociety 故障处置场景",
    )
    simulate.add_argument("scenario", help="场景 JSON 文件路径")
    simulate.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式，默认 text",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "diagnose":
        result = run_case(args.case)
        if args.format == "json":
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_text(result, candidate_limit=max(1, args.candidate_limit)))
        return 0

    if args.command == "simulate":
        report = run_simulation(args.scenario)
        if args.format == "json":
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_simulation_text(report))
        return 0

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
