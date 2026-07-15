"""Command-line interface for grid-agent."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .demo import render_text, run_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grid-agent",
        description="树状 10 kV 配电馈线故障诊断 Demo",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "diagnose":
        raise RuntimeError(f"unsupported command: {args.command}")

    result = run_case(args.case)
    if args.format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text(result, candidate_limit=max(1, args.candidate_limit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
