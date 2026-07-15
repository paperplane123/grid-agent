"""Domain models for radial distribution feeder diagnosis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Node:
    """A bus, switching point, transformer point, or terminal node."""

    id: str
    name: str
    nominal_voltage_kv: float = 10.0
    kind: str = "bus"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            nominal_voltage_kv=float(data.get("nominal_voltage_kv", 10.0)),
            kind=str(data.get("kind", "bus")),
        )


@dataclass(frozen=True, slots=True)
class Branch:
    """A directed feeder branch from the source toward downstream loads."""

    id: str
    name: str
    from_node: str
    to_node: str
    length_km: float = 0.0
    switch_id: str | None = None
    normally_closed: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Branch:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            from_node=str(data["from_node"]),
            to_node=str(data["to_node"]),
            length_km=float(data.get("length_km", 0.0)),
            switch_id=data.get("switch_id"),
            normally_closed=bool(data.get("normally_closed", True)),
        )


@dataclass(frozen=True, slots=True)
class Measurement:
    """Snapshot measurement used by the explainable v0.1 diagnoser."""

    node_voltage_pu: dict[str, float] = field(default_factory=dict)
    branch_zero_sequence_current_a: dict[str, float] = field(default_factory=dict)
    operated_protections: tuple[str, ...] = ()
    opened_switches: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Measurement:
        return cls(
            node_voltage_pu={
                str(key): float(value)
                for key, value in data.get("node_voltage_pu", {}).items()
            },
            branch_zero_sequence_current_a={
                str(key): float(value)
                for key, value in data.get("branch_zero_sequence_current_a", {}).items()
            },
            operated_protections=tuple(map(str, data.get("operated_protections", []))),
            opened_switches=tuple(map(str, data.get("opened_switches", []))),
        )


@dataclass(frozen=True, slots=True)
class FeederCase:
    """Complete input case for one feeder diagnosis run."""

    name: str
    source_node: str
    nodes: tuple[Node, ...]
    branches: tuple[Branch, ...]
    measurement: Measurement
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeederCase:
        return cls(
            name=str(data.get("name", "unnamed feeder")),
            source_node=str(data["source_node"]),
            nodes=tuple(Node.from_dict(item) for item in data["nodes"]),
            branches=tuple(Branch.from_dict(item) for item in data["branches"]),
            measurement=Measurement.from_dict(data.get("measurement", {})),
            metadata=dict(data.get("metadata", {})),
        )
