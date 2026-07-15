"""Explainable fault-section diagnosis for a radial feeder snapshot."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean

from .model import FeederCase
from .topology import RadialFeeder


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class Evidence:
    name: str
    value: float
    contribution: float
    detail: str


@dataclass(frozen=True, slots=True)
class CandidateScore:
    branch_id: str
    branch_name: str
    score: float
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class FaultDiagnosis:
    feeder_name: str
    likely_branch_id: str
    likely_branch_name: str
    confidence: float
    candidates: tuple[CandidateScore, ...]
    recommendations: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FaultDiagnoser:
    """Score fault-section candidates using topology-constrained measurements.

    This v0.1 diagnoser is deliberately interpretable. It combines four evidence
    groups rather than pretending that empirical scores are a transient analytical
    solution. The weights can later be calibrated against PSCAD or field cases.
    """

    def __init__(
        self,
        *,
        low_voltage_threshold_pu: float = 0.92,
        severe_voltage_pu: float = 0.75,
        zero_sequence_reference_a: float = 20.0,
    ) -> None:
        if severe_voltage_pu >= low_voltage_threshold_pu:
            raise ValueError("severe_voltage_pu must be below low_voltage_threshold_pu")
        self.low_voltage_threshold_pu = low_voltage_threshold_pu
        self.severe_voltage_pu = severe_voltage_pu
        self.zero_sequence_reference_a = zero_sequence_reference_a

    def diagnose(self, case: FeederCase) -> FaultDiagnosis:
        feeder = RadialFeeder(case)
        measurement = case.measurement
        measured_i0 = measurement.branch_zero_sequence_current_a
        observed_max_i0 = max((abs(value) for value in measured_i0.values()), default=0.0)
        i0_scale = max(self.zero_sequence_reference_a, observed_max_i0)

        candidates = tuple(
            sorted(
                (self._score_branch(feeder, branch_id, i0_scale) for branch_id in feeder.branches),
                key=lambda item: (-item.score, feeder.branch_depth(item.branch_id), item.branch_id),
            )
        )
        if not candidates:
            raise ValueError("feeder has no branch candidates")

        winner = candidates[0]
        runner_up = candidates[1].score if len(candidates) > 1 else 0.0
        relative_margin = (winner.score - runner_up) / max(winner.score, 1e-9)
        evidence_strength = _clamp(winner.score / 0.70)
        confidence = _clamp((0.45 + 0.55 * relative_margin) * evidence_strength)

        branch = feeder.branches[winner.branch_id]
        downstream = feeder.downstream_nodes(branch.id)
        recommendations: list[str] = []
        if branch.switch_id:
            recommendations.append(
                f"复核 {branch.switch_id} 遥信与保护动作，确认后隔离支路 {branch.name}。"
            )
        else:
            recommendations.append(f"复核并隔离支路 {branch.name} 两端可操作开关。")
        recommendations.append(
            "检查下游节点 " + "、".join(downstream) + " 的接地、绝缘和录波数据。"
        )
        recommendations.append("隔离后重新进行拓扑着色与潮流/供电恢复校核，禁止仅凭本评分直接遥控。")

        limitations = (
            "当前算法使用稳态/准稳态快照和工程评分，尚未接入高频暂态解析模型。",
            "评分权重尚未使用连云港现场样本或 PSCAD 批量仿真标定。",
            "诊断结果用于研发验证，不替代继电保护、调度规程和现场安全确认。",
        )

        return FaultDiagnosis(
            feeder_name=case.name,
            likely_branch_id=winner.branch_id,
            likely_branch_name=winner.branch_name,
            confidence=round(confidence, 4),
            candidates=candidates,
            recommendations=tuple(recommendations),
            limitations=limitations,
        )

    def _score_branch(
        self,
        feeder: RadialFeeder,
        branch_id: str,
        i0_scale: float,
    ) -> CandidateScore:
        branch = feeder.branches[branch_id]
        measurement = feeder.case.measurement
        downstream_nodes = feeder.downstream_nodes(branch_id)
        upstream_nodes = feeder.upstream_nodes(branch_id)

        downstream_voltages = [
            measurement.node_voltage_pu[node_id]
            for node_id in downstream_nodes
            if node_id in measurement.node_voltage_pu
        ]
        upstream_voltages = [
            measurement.node_voltage_pu[node_id]
            for node_id in upstream_nodes
            if node_id in measurement.node_voltage_pu
        ]

        i0_value = abs(measurement.branch_zero_sequence_current_a.get(branch_id, 0.0))
        i0_signal = _clamp(i0_value / max(i0_scale, 1e-9))
        i0_contribution = 0.45 * i0_signal

        if downstream_voltages:
            downstream_drop = fmean(
                _clamp(
                    (self.low_voltage_threshold_pu - voltage)
                    / (self.low_voltage_threshold_pu - self.severe_voltage_pu)
                )
                for voltage in downstream_voltages
            )
            downstream_average = fmean(downstream_voltages)
        else:
            downstream_drop = 0.0
            downstream_average = 1.0
        voltage_contribution = 0.25 * downstream_drop

        if upstream_voltages and downstream_voltages:
            upstream_average = fmean(upstream_voltages)
            boundary_contrast = _clamp((upstream_average - downstream_average) / 0.20)
        else:
            upstream_average = 1.0
            boundary_contrast = 0.0
        boundary_contribution = 0.20 * boundary_contrast

        protection_hit = branch.id in measurement.operated_protections
        switch_hit = branch.switch_id is not None and branch.switch_id in measurement.opened_switches
        action_signal = 1.0 if protection_hit or switch_hit else 0.0
        action_contribution = 0.10 * action_signal

        evidence = (
            Evidence(
                name="zero_sequence_current",
                value=round(i0_value, 4),
                contribution=round(i0_contribution, 4),
                detail=f"支路零序电流 {i0_value:.2f} A，按 {i0_scale:.2f} A 标度归一化。",
            ),
            Evidence(
                name="downstream_voltage_drop",
                value=round(downstream_average, 4),
                contribution=round(voltage_contribution, 4),
                detail=(
                    f"下游 {len(downstream_voltages)} 个有效量测点平均电压 "
                    f"{downstream_average:.3f} pu。"
                ),
            ),
            Evidence(
                name="topology_boundary_contrast",
                value=round(boundary_contrast, 4),
                contribution=round(boundary_contribution, 4),
                detail=(
                    f"上游平均 {upstream_average:.3f} pu，下游平均 "
                    f"{downstream_average:.3f} pu。"
                ),
            ),
            Evidence(
                name="protection_or_switch_action",
                value=action_signal,
                contribution=round(action_contribution, 4),
                detail=(
                    "候选支路存在保护/开关动作证据。"
                    if action_signal
                    else "未取得与候选支路直接对应的保护/开关动作证据。"
                ),
            ),
        )
        score = round(sum(item.contribution for item in evidence), 4)
        return CandidateScore(
            branch_id=branch.id,
            branch_name=branch.name,
            score=score,
            evidence=evidence,
        )
