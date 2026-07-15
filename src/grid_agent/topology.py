"""Topology utilities for directed radial feeders."""

from __future__ import annotations

from collections import defaultdict, deque

from .model import Branch, FeederCase, Node


class TopologyError(ValueError):
    """Raised when a feeder case is not a valid directed radial network."""


class RadialFeeder:
    """Validated tree view of a feeder case.

    Branch direction must follow the normal power-supply direction, from the
    source node toward downstream loads.
    """

    def __init__(self, case: FeederCase) -> None:
        self.case = case
        self.nodes: dict[str, Node] = {node.id: node for node in case.nodes}
        self.branches: dict[str, Branch] = {branch.id: branch for branch in case.branches}
        self.children: dict[str, list[Branch]] = defaultdict(list)
        self.incoming: dict[str, Branch] = {}
        self._validate_and_index()

    def _validate_and_index(self) -> None:
        if len(self.nodes) != len(self.case.nodes):
            raise TopologyError("duplicate node id detected")
        if len(self.branches) != len(self.case.branches):
            raise TopologyError("duplicate branch id detected")
        if self.case.source_node not in self.nodes:
            raise TopologyError(f"source node {self.case.source_node!r} does not exist")

        for branch in self.case.branches:
            if branch.from_node not in self.nodes or branch.to_node not in self.nodes:
                raise TopologyError(f"branch {branch.id!r} references an unknown node")
            if branch.to_node == self.case.source_node:
                raise TopologyError("source node cannot have an incoming feeder branch")
            if branch.to_node in self.incoming:
                other = self.incoming[branch.to_node]
                raise TopologyError(
                    f"node {branch.to_node!r} has multiple incoming branches: "
                    f"{other.id!r}, {branch.id!r}"
                )
            self.children[branch.from_node].append(branch)
            self.incoming[branch.to_node] = branch

        visited: set[str] = set()
        active: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in active:
                raise TopologyError(f"cycle detected at node {node_id!r}")
            if node_id in visited:
                return
            active.add(node_id)
            for branch in self.children.get(node_id, []):
                visit(branch.to_node)
            active.remove(node_id)
            visited.add(node_id)

        visit(self.case.source_node)
        unreachable = set(self.nodes) - visited
        if unreachable:
            names = ", ".join(sorted(unreachable))
            raise TopologyError(f"nodes are unreachable from source: {names}")

        missing_parent = {
            node_id
            for node_id in self.nodes
            if node_id != self.case.source_node and node_id not in self.incoming
        }
        if missing_parent:
            names = ", ".join(sorted(missing_parent))
            raise TopologyError(f"non-source nodes without incoming branch: {names}")

    def parent_branch(self, node_id: str) -> Branch | None:
        return self.incoming.get(node_id)

    def child_branches(self, node_id: str) -> tuple[Branch, ...]:
        return tuple(self.children.get(node_id, ()))

    def downstream_nodes(self, branch_id: str) -> tuple[str, ...]:
        """Return all nodes supplied through a candidate branch, including its end node."""

        branch = self.branches[branch_id]
        result: list[str] = []
        queue: deque[str] = deque([branch.to_node])
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            queue.extend(child.to_node for child in self.children.get(node_id, ()))
        return tuple(result)

    def upstream_nodes(self, branch_id: str) -> tuple[str, ...]:
        """Return source-side nodes ending at the branch's from-node."""

        branch = self.branches[branch_id]
        result: list[str] = [branch.from_node]
        current = branch.from_node
        while current != self.case.source_node:
            parent = self.incoming[current]
            current = parent.from_node
            result.append(current)
        result.reverse()
        return tuple(result)

    def path_branch_ids(self, node_id: str) -> tuple[str, ...]:
        """Return the unique source-to-node branch path."""

        if node_id not in self.nodes:
            raise KeyError(node_id)
        path: list[str] = []
        current = node_id
        while current != self.case.source_node:
            parent = self.incoming[current]
            path.append(parent.id)
            current = parent.from_node
        path.reverse()
        return tuple(path)

    def branch_depth(self, branch_id: str) -> int:
        """Return branch depth where source-adjacent branches have depth 1."""

        branch = self.branches[branch_id]
        return len(self.path_branch_ids(branch.to_node))

    def leaf_nodes(self) -> tuple[str, ...]:
        return tuple(node_id for node_id in self.nodes if not self.children.get(node_id))
