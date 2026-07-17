"""Physical-cognitive multi-agent simulation for distribution-grid incidents.

The MVP deliberately keeps electrical diagnosis and operational decision making
separate: :class:`FaultDiagnoser` produces engineering evidence, while a dispatch
policy decides whether to isolate directly or request field verification.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .diagnosis import FaultDiagnosis, FaultDiagnoser
from .model import FeederCase
from .topology import RadialFeeder


class DecisionAction(StrEnum):
    """Actions available to the dispatch decision layer in the MVP."""

    DIRECT_ISOLATION = "direct_isolation"
    REQUEST_FIELD_INSPECTION = "request_field_inspection"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class IncidentConfig:
    """Ground-truth and timing assumptions for one synthetic incident."""

    ground_truth_fault_branch: str
    customers_by_node: dict[str, int] = field(default_factory=dict)
    critical_nodes: tuple[str, ...] = ()
    remote_operation_minutes: float = 2.0
    field_inspection_minutes: float = 20.0
    manual_review_minutes: float = 10.0
    minimum_direct_isolation_confidence: float = 0.72
    minimum_top_margin: float = 0.10
    max_field_candidates: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IncidentConfig:
        config = cls(
            ground_truth_fault_branch=str(data["ground_truth_fault_branch"]),
            customers_by_node={
                str(node_id): int(count)
                for node_id, count in data.get("customers_by_node", {}).items()
            },
            critical_nodes=tuple(map(str, data.get("critical_nodes", []))),
            remote_operation_minutes=float(data.get("remote_operation_minutes", 2.0)),
            field_inspection_minutes=float(data.get("field_inspection_minutes", 20.0)),
            manual_review_minutes=float(data.get("manual_review_minutes", 10.0)),
            minimum_direct_isolation_confidence=float(
                data.get("minimum_direct_isolation_confidence", 0.72)
            ),
            minimum_top_margin=float(data.get("minimum_top_margin", 0.10)),
            max_field_candidates=int(data.get("max_field_candidates", 2)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if any(count < 0 for count in self.customers_by_node.values()):
            raise ValueError("customers_by_node values must be non-negative")
        if self.remote_operation_minutes < 0:
            raise ValueError("remote_operation_minutes must be non-negative")
        if self.field_inspection_minutes < 0:
            raise ValueError("field_inspection_minutes must be non-negative")
        if self.manual_review_minutes < 0:
            raise ValueError("manual_review_minutes must be non-negative")
        if not 0.0 <= self.minimum_direct_isolation_confidence <= 1.0:
            raise ValueError("minimum_direct_isolation_confidence must be in [0, 1]")
        if not 0.0 <= self.minimum_top_margin <= 1.0:
            raise ValueError("minimum_top_margin must be in [0, 1]")
        if self.max_field_candidates < 1:
            raise ValueError("max_field_candidates must be at least 1")


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """A feeder snapshot plus incident assumptions used by GridSociety."""

    name: str
    feeder_case: FeederCase
    incident: IncidentConfig


@dataclass(frozen=True, slots=True)
class DiagnosticAssessment:
    """Diagnosis enriched with a feasibility gate for operational use."""

    diagnosis: FaultDiagnosis
    top_margin: float
    diagnosable: bool
    reason: str


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    """A dispatch-layer decision independent from any specific LLM provider."""

    action: DecisionAction
    branch_id: str | None
    candidate_branch_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class FieldInspectionReport:
    """Synthetic field feedback used to close the incident loop."""

    inspected_branch_ids: tuple[str, ...]
    confirmed_fault_branch: str | None
    elapsed_minutes: float
    notes: str


@dataclass(frozen=True, slots=True)
class CustomerImpact:
    """Customer impact derived from the physical feeder topology."""

    affected_nodes: tuple[str, ...]
    affected_customers: int
    affected_critical_nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    """One observable event in the multi-agent incident timeline."""

    sequence: int
    elapsed_minutes: float
    actor: str
    event_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulationMetrics:
    """System-level metrics for comparing decision policies."""

    diagnosis_top1_correct: bool
    diagnosable: bool
    direct_isolation: bool
    incident_contained: bool
    affected_customers: int
    affected_critical_nodes: int
    elapsed_minutes_to_containment: float
    customer_minutes_to_containment: float
    switching_operations: int
    field_inspections: int
    incorrect_isolations: int
    manual_review_required: bool


@dataclass(frozen=True, slots=True)
class SimulationReport:
    """Complete GridSociety run output."""

    scenario_name: str
    policy_name: str
    diagnosis: DiagnosticAssessment
    customer_impact: CustomerImpact
    events: tuple[SimulationEvent, ...]
    metrics: SimulationMetrics
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DispatchPolicy(Protocol):
    """Provider-neutral policy contract for rules, local models, or hosted LLMs."""

    name: str

    def decide(
        self,
        assessment: DiagnosticAssessment,
        incident: IncidentConfig,
        field_report: FieldInspectionReport | None = None,
    ) -> DispatchDecision:
        """Return the next dispatch action for the current incident state."""


class RuleBasedDispatcher:
    """Deterministic baseline used before connecting an LLM policy."""

    name = "rule-based-safe-baseline"

    def decide(
        self,
        assessment: DiagnosticAssessment,
        incident: IncidentConfig,
        field_report: FieldInspectionReport | None = None,
    ) -> DispatchDecision:
        if field_report is not None:
            if field_report.confirmed_fault_branch is not None:
                return DispatchDecision(
                    action=DecisionAction.DIRECT_ISOLATION,
                    branch_id=field_report.confirmed_fault_branch,
                    candidate_branch_ids=field_report.inspected_branch_ids,
                    rationale="现场反馈已确认故障区段，进入隔离操作。",
                )
            return DispatchDecision(
                action=DecisionAction.MANUAL_REVIEW,
                branch_id=None,
                candidate_branch_ids=field_report.inspected_branch_ids,
                rationale="首轮现场核查未确认故障，升级人工复核与补充量测。",
            )

        winner = assessment.diagnosis.likely_branch_id
        if assessment.diagnosable:
            return DispatchDecision(
                action=DecisionAction.DIRECT_ISOLATION,
                branch_id=winner,
                candidate_branch_ids=(winner,),
                rationale=(
                    "诊断置信度和候选区段间隔均达到安全基线，"
                    "建议复核遥信后直接隔离首选区段。"
                ),
            )

        candidates = tuple(
            item.branch_id
            for item in assessment.diagnosis.candidates[: incident.max_field_candidates]
        )
        return DispatchDecision(
            action=DecisionAction.REQUEST_FIELD_INSPECTION,
            branch_id=None,
            candidate_branch_ids=candidates,
            rationale="当前场景可诊断性不足，先核查 Top-K 候选区段，禁止直接遥控。",
        )


class DiagnosticAgent:
    """Wrap the engineering diagnoser and expose an operational feasibility head."""

    def __init__(self, diagnoser: FaultDiagnoser | None = None) -> None:
        self.diagnoser = diagnoser or FaultDiagnoser()

    def assess(
        self,
        case: FeederCase,
        incident: IncidentConfig,
    ) -> DiagnosticAssessment:
        diagnosis = self.diagnoser.diagnose(case)
        if len(diagnosis.candidates) > 1:
            top_margin = diagnosis.candidates[0].score - diagnosis.candidates[1].score
        else:
            top_margin = diagnosis.candidates[0].score

        confidence_ok = (
            diagnosis.confidence >= incident.minimum_direct_isolation_confidence
        )
        margin_ok = top_margin >= incident.minimum_top_margin
        diagnosable = confidence_ok and margin_ok
        reason = (
            "置信度与候选间隔均满足直接隔离阈值。"
            if diagnosable
            else (
                f"直接隔离门槛未满足：confidence={diagnosis.confidence:.3f}, "
                f"top_margin={top_margin:.3f}。"
            )
        )
        return DiagnosticAssessment(
            diagnosis=diagnosis,
            top_margin=round(top_margin, 4),
            diagnosable=diagnosable,
            reason=reason,
        )


class FieldCrewAgent:
    """Synthetic field crew that verifies a bounded set of candidate sections."""

    def inspect(
        self,
        candidate_branch_ids: tuple[str, ...],
        incident: IncidentConfig,
    ) -> FieldInspectionReport:
        confirmed = (
            incident.ground_truth_fault_branch
            if incident.ground_truth_fault_branch in candidate_branch_ids
            else None
        )
        notes = (
            f"现场确认故障位于 {confirmed}。"
            if confirmed is not None
            else "首轮候选区段未发现明确故障证据。"
        )
        return FieldInspectionReport(
            inspected_branch_ids=candidate_branch_ids,
            confirmed_fault_branch=confirmed,
            elapsed_minutes=incident.field_inspection_minutes,
            notes=notes,
        )


class CustomerServiceAgent:
    """Translate topology impact into customer and critical-load pressure."""

    def summarize(
        self,
        feeder: RadialFeeder,
        incident: IncidentConfig,
    ) -> CustomerImpact:
        affected_nodes = feeder.downstream_nodes(incident.ground_truth_fault_branch)
        affected_customers = sum(
            incident.customers_by_node.get(node_id, 0) for node_id in affected_nodes
        )
        critical = tuple(
            node_id for node_id in affected_nodes if node_id in incident.critical_nodes
        )
        return CustomerImpact(
            affected_nodes=affected_nodes,
            affected_customers=affected_customers,
            affected_critical_nodes=critical,
        )


class PhysicalEnvironment:
    """Minimal state machine for field checks, switching, and containment."""

    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.feeder = RadialFeeder(scenario.feeder_case)
        if scenario.incident.ground_truth_fault_branch not in self.feeder.branches:
            raise ValueError("ground_truth_fault_branch does not exist in feeder")

        unknown_customer_nodes = (
            set(scenario.incident.customers_by_node) - set(self.feeder.nodes)
        )
        if unknown_customer_nodes:
            names = ", ".join(sorted(unknown_customer_nodes))
            raise ValueError(f"customers_by_node references unknown nodes: {names}")

        self.elapsed_minutes = 0.0
        self.switching_operations = 0
        self.field_inspections = 0
        self.incorrect_isolations = 0
        self.manual_review_required = False
        self.incident_contained = False
        self.isolated_branches: list[str] = []

    def apply_field_inspection(self, report: FieldInspectionReport) -> None:
        self.elapsed_minutes += report.elapsed_minutes
        self.field_inspections += len(report.inspected_branch_ids)

    def apply_manual_review(self) -> None:
        self.manual_review_required = True
        self.elapsed_minutes += self.scenario.incident.manual_review_minutes

    def isolate(self, branch_id: str) -> bool:
        if branch_id not in self.feeder.branches:
            raise ValueError(f"cannot isolate unknown branch {branch_id!r}")
        self.elapsed_minutes += self.scenario.incident.remote_operation_minutes
        self.switching_operations += 1
        self.isolated_branches.append(branch_id)
        correct = branch_id == self.scenario.incident.ground_truth_fault_branch
        if correct:
            self.incident_contained = True
        else:
            self.incorrect_isolations += 1
        return correct


class GridSocietySimulator:
    """Run the MVP multi-agent incident workflow to a contained terminal state."""

    def __init__(
        self,
        *,
        policy: DispatchPolicy | None = None,
        diagnostic_agent: DiagnosticAgent | None = None,
        field_agent: FieldCrewAgent | None = None,
        customer_agent: CustomerServiceAgent | None = None,
    ) -> None:
        self.policy = policy or RuleBasedDispatcher()
        self.diagnostic_agent = diagnostic_agent or DiagnosticAgent()
        self.field_agent = field_agent or FieldCrewAgent()
        self.customer_agent = customer_agent or CustomerServiceAgent()

    def run(self, scenario: SimulationScenario) -> SimulationReport:
        environment = PhysicalEnvironment(scenario)
        events: list[SimulationEvent] = []

        def record(
            actor: str,
            event_type: str,
            summary: str,
            payload: dict[str, Any] | None = None,
        ) -> None:
            events.append(
                SimulationEvent(
                    sequence=len(events) + 1,
                    elapsed_minutes=round(environment.elapsed_minutes, 3),
                    actor=actor,
                    event_type=event_type,
                    summary=summary,
                    payload=payload or {},
                )
            )

        assessment = self.diagnostic_agent.assess(
            scenario.feeder_case,
            scenario.incident,
        )
        record(
            "diagnostic-agent",
            "diagnosis",
            (
                f"Top-1 候选 {assessment.diagnosis.likely_branch_id}，"
                f"confidence={assessment.diagnosis.confidence:.3f}。"
            ),
            {
                "likely_branch_id": assessment.diagnosis.likely_branch_id,
                "confidence": assessment.diagnosis.confidence,
                "top_margin": assessment.top_margin,
                "diagnosable": assessment.diagnosable,
            },
        )

        impact = self.customer_agent.summarize(environment.feeder, scenario.incident)
        record(
            "customer-service-agent",
            "impact_assessment",
            (
                f"预计影响 {impact.affected_customers} 户，"
                f"关键节点 {len(impact.affected_critical_nodes)} 个。"
            ),
            asdict(impact),
        )

        initial_decision = self.policy.decide(assessment, scenario.incident)
        direct_isolation = initial_decision.action == DecisionAction.DIRECT_ISOLATION
        record(
            "dispatcher-agent",
            "decision",
            initial_decision.rationale,
            asdict(initial_decision),
        )

        if initial_decision.action == DecisionAction.DIRECT_ISOLATION:
            if initial_decision.branch_id is None:
                raise ValueError("direct isolation decision requires branch_id")
            correct = environment.isolate(initial_decision.branch_id)
            record(
                "physical-environment",
                "switching",
                (
                    f"隔离 {initial_decision.branch_id}，故障已被控制。"
                    if correct
                    else f"隔离 {initial_decision.branch_id} 后故障仍存在。"
                ),
                {"branch_id": initial_decision.branch_id, "correct": correct},
            )
        elif initial_decision.action == DecisionAction.REQUEST_FIELD_INSPECTION:
            field_report = self.field_agent.inspect(
                initial_decision.candidate_branch_ids,
                scenario.incident,
            )
            environment.apply_field_inspection(field_report)
            record(
                "field-crew-agent",
                "field_feedback",
                field_report.notes,
                asdict(field_report),
            )
            follow_up = self.policy.decide(
                assessment,
                scenario.incident,
                field_report,
            )
            record(
                "dispatcher-agent",
                "decision",
                follow_up.rationale,
                asdict(follow_up),
            )
            if follow_up.action == DecisionAction.DIRECT_ISOLATION:
                if follow_up.branch_id is None:
                    raise ValueError("direct isolation decision requires branch_id")
                correct = environment.isolate(follow_up.branch_id)
                record(
                    "physical-environment",
                    "switching",
                    (
                        f"隔离 {follow_up.branch_id}，故障已被控制。"
                        if correct
                        else f"隔离 {follow_up.branch_id} 后故障仍存在。"
                    ),
                    {"branch_id": follow_up.branch_id, "correct": correct},
                )
            else:
                environment.apply_manual_review()
                record(
                    "human-supervisor",
                    "manual_review",
                    "人工复核补充量测并锁定真实故障区段。",
                    {"branch_id": scenario.incident.ground_truth_fault_branch},
                )
        else:
            environment.apply_manual_review()
            record(
                "human-supervisor",
                "manual_review",
                "决策策略直接要求人工复核。",
                {"branch_id": scenario.incident.ground_truth_fault_branch},
            )

        if not environment.incident_contained:
            if not environment.manual_review_required:
                environment.apply_manual_review()
                record(
                    "human-supervisor",
                    "manual_review",
                    "错误隔离未控制故障，升级人工复核。",
                    {"branch_id": scenario.incident.ground_truth_fault_branch},
                )
            truth = scenario.incident.ground_truth_fault_branch
            correct = environment.isolate(truth)
            record(
                "physical-environment",
                "switching",
                f"隔离人工确认区段 {truth}，故障已被控制。",
                {"branch_id": truth, "correct": correct},
            )

        elapsed = round(environment.elapsed_minutes, 3)
        metrics = SimulationMetrics(
            diagnosis_top1_correct=(
                assessment.diagnosis.likely_branch_id
                == scenario.incident.ground_truth_fault_branch
            ),
            diagnosable=assessment.diagnosable,
            direct_isolation=direct_isolation,
            incident_contained=environment.incident_contained,
            affected_customers=impact.affected_customers,
            affected_critical_nodes=len(impact.affected_critical_nodes),
            elapsed_minutes_to_containment=elapsed,
            customer_minutes_to_containment=round(
                impact.affected_customers * elapsed,
                3,
            ),
            switching_operations=environment.switching_operations,
            field_inspections=environment.field_inspections,
            incorrect_isolations=environment.incorrect_isolations,
            manual_review_required=environment.manual_review_required,
        )

        limitations = (
            "MVP 只模拟故障控制时间，不模拟联络转供、负荷恢复和潮流越限。",
            "现场反馈由场景真值生成，用于验证流程，不代表真实巡检不确定性。",
            "默认策略是可复现规则基线；LLM 接入后仍必须经过同一安全动作门控。",
            "所有结果仅用于研发验证，不替代调度规程、保护定值和现场安全确认。",
        )
        return SimulationReport(
            scenario_name=scenario.name,
            policy_name=self.policy.name,
            diagnosis=assessment,
            customer_impact=impact,
            events=tuple(events),
            metrics=metrics,
            limitations=limitations,
        )


def load_scenario(path: str | Path) -> SimulationScenario:
    """Load a scenario JSON file, resolving feeder_case_path relative to it."""

    scenario_path = Path(path)
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    if "feeder_case" in data:
        feeder_data = data["feeder_case"]
    elif "feeder_case_path" in data:
        feeder_path = scenario_path.parent / str(data["feeder_case_path"])
        feeder_data = json.loads(feeder_path.read_text(encoding="utf-8"))
    else:
        raise ValueError("scenario requires feeder_case or feeder_case_path")

    incident = IncidentConfig.from_dict(dict(data["incident"]))
    return SimulationScenario(
        name=str(data.get("name", "unnamed GridSociety scenario")),
        feeder_case=FeederCase.from_dict(dict(feeder_data)),
        incident=incident,
    )


def run_simulation(
    path: str | Path,
    *,
    policy: DispatchPolicy | None = None,
) -> SimulationReport:
    """Load and run one GridSociety scenario."""

    return GridSocietySimulator(policy=policy).run(load_scenario(path))


def render_simulation_text(report: SimulationReport) -> str:
    """Render a concise human-readable incident report."""

    metrics = report.metrics
    lines = [
        f"场景：{report.scenario_name}",
        f"策略：{report.policy_name}",
        (
            "诊断："
            f"{report.diagnosis.diagnosis.likely_branch_id} "
            f"(confidence={report.diagnosis.diagnosis.confidence:.3f}, "
            f"top_margin={report.diagnosis.top_margin:.3f}, "
            f"diagnosable={report.diagnosis.diagnosable})"
        ),
        (
            f"影响：{metrics.affected_customers} 户，"
            f"关键节点 {metrics.affected_critical_nodes} 个"
        ),
        (
            f"结果：contained={metrics.incident_contained}, "
            f"耗时={metrics.elapsed_minutes_to_containment:.1f} min, "
            f"开关操作={metrics.switching_operations}, "
            f"现场核查={metrics.field_inspections}, "
            f"错误隔离={metrics.incorrect_isolations}"
        ),
        "",
        "事件时间线：",
    ]
    for event in report.events:
        lines.append(
            f"{event.sequence:02d}. +{event.elapsed_minutes:.1f} min "
            f"[{event.actor}] {event.summary}"
        )
    lines.extend(("", "边界：", *(f"- {item}" for item in report.limitations)))
    return "\n".join(lines)
