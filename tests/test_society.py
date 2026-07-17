from dataclasses import replace
from pathlib import Path

from grid_agent.society import GridSocietySimulator, load_scenario, run_simulation


EXAMPLE = Path(__file__).parents[1] / "examples" / "gridsociety_incident.json"


def test_mvp_contains_high_confidence_incident_directly() -> None:
    report = run_simulation(EXAMPLE)

    assert report.metrics.diagnosis_top1_correct is True
    assert report.metrics.diagnosable is True
    assert report.metrics.direct_isolation is True
    assert report.metrics.incident_contained is True
    assert report.metrics.affected_customers == 500
    assert report.metrics.affected_critical_nodes == 1
    assert report.metrics.elapsed_minutes_to_containment == 2.0
    assert report.metrics.customer_minutes_to_containment == 1000.0
    assert report.metrics.switching_operations == 1
    assert report.metrics.field_inspections == 0
    assert report.metrics.incorrect_isolations == 0


def test_low_feasibility_requests_field_verification() -> None:
    scenario = load_scenario(EXAMPLE)
    conservative_incident = replace(
        scenario.incident,
        minimum_direct_isolation_confidence=0.99,
    )
    conservative_scenario = replace(scenario, incident=conservative_incident)

    report = GridSocietySimulator().run(conservative_scenario)

    assert report.metrics.diagnosable is False
    assert report.metrics.direct_isolation is False
    assert report.metrics.incident_contained is True
    assert report.metrics.elapsed_minutes_to_containment == 22.0
    assert report.metrics.field_inspections == 2
    assert report.metrics.switching_operations == 1
    assert report.metrics.manual_review_required is False
