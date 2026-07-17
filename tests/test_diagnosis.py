from pathlib import Path

from grid_agent.demo import load_case, run_case
from grid_agent.topology import RadialFeeder

EXAMPLE = Path(__file__).parents[1] / "examples" / "feeder_10kv.json"


def test_example_identifies_faulted_branch() -> None:
    result = run_case(EXAMPLE)
    assert result.likely_branch_id == "B23"
    assert result.confidence >= 0.70
    assert result.candidates[0].score > result.candidates[1].score


def test_radial_topology_queries_unique_path() -> None:
    feeder = RadialFeeder(load_case(EXAMPLE))
    assert feeder.path_branch_ids("N4") == ("B01", "B12", "B23", "B34")
    assert feeder.downstream_nodes("B23") == ("N3", "N4")
    assert feeder.upstream_nodes("B23") == ("S", "N1", "N2")
    assert set(feeder.leaf_nodes()) == {"N4", "N5"}
