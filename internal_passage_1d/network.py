from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace

from .correlations import evaluate_edge
from .models import (
    EdgeResult,
    EdgeSpec,
    Geometry,
    NetworkSpec,
    NodeResult,
    NodeSpec,
    SolverOptions,
    SolverResult,
)
from .properties import make_property_provider


class FixedFlowSolver:
    """Steady fixed-flow network solver for directed acyclic passages."""

    def __init__(
        self,
        network: NetworkSpec,
        options: SolverOptions | None = None,
    ) -> None:
        self.network = network
        self.options = options or SolverOptions()
        self._nodes = {node.node_id: node for node in network.nodes}
        if len(self._nodes) != len(network.nodes):
            raise ValueError("Node IDs must be unique.")
        self._edges = {edge.edge_id: edge for edge in network.edges}
        if len(self._edges) != len(network.edges):
            raise ValueError("Edge IDs must be unique.")
        self._outgoing: dict[str, list[EdgeSpec]] = defaultdict(list)
        self._incoming: dict[str, list[EdgeSpec]] = defaultdict(list)
        for edge in network.edges:
            if edge.from_node not in self._nodes:
                raise ValueError(f"Unknown from_node: {edge.from_node}")
            if edge.to_node not in self._nodes:
                raise ValueError(f"Unknown to_node: {edge.to_node}")
            self._outgoing[edge.from_node].append(edge)
            self._incoming[edge.to_node].append(edge)

    def solve(self) -> SolverResult:
        property_provider = make_property_provider(self.options.property_model)
        reference_temperature = self._global_reference_temperature()
        options = replace(self.options)
        warnings: list[str] = []

        node_results: dict[str, NodeResult] = {}
        edge_results: dict[str, EdgeResult] = {}
        received: dict[str, list[EdgeResult]] = defaultdict(list)
        queue: deque[str] = deque()

        for node in self.network.nodes:
            if node.kind == "inlet" or node.inlet_mdot is not None:
                result = self._make_inlet_result(node)
                node_results[node.node_id] = result
                queue.append(node.node_id)

        while queue:
            node_id = queue.popleft()
            node_result = node_results[node_id]
            outgoing = self._outgoing.get(node_id, [])
            if not outgoing:
                continue

            flow_map, flow_warnings = self._outgoing_flows(node_result, outgoing)
            warnings.extend(flow_warnings)

            for edge in outgoing:
                if edge.edge_id in edge_results:
                    continue
                edge_for_eval = self._edge_for_evaluation(edge)
                mass_flow = flow_map[edge.edge_id]
                edge_result = evaluate_edge(
                    edge=edge_for_eval,
                    inlet=node_result,
                    mass_flow=mass_flow,
                    property_provider=property_provider,
                    options=options,
                    global_reference_temperature=reference_temperature,
                )
                edge_results[edge.edge_id] = edge_result
                warnings.extend(edge_result.warnings)
                to_node = edge.to_node
                received[to_node].append(edge_result)
                if len(received[to_node]) == len(self._incoming[to_node]):
                    if to_node not in node_results:
                        merged = self._make_node_result(
                            self._nodes[to_node],
                            received[to_node],
                        )
                        node_results[to_node] = merged
                        warnings.extend(merged.warnings)
                        queue.append(to_node)

        if len(edge_results) != len(self.network.edges):
            missing = sorted(set(self._edges) - set(edge_results))
            raise RuntimeError(
                "Network could not be fully solved. Check for loops or missing "
                f"inlets. Missing edges: {missing}"
            )

        return SolverResult(
            nodes=node_results,
            edges=edge_results,
            warnings=tuple(warnings),
            reference_temperature=reference_temperature,
        )

    def _edge_for_evaluation(self, edge: EdgeSpec) -> EdgeSpec:
        if edge.cooling_technology not in {"turning", "u_turn"}:
            return edge
        if edge.geometry.shape != "rectangular":
            return edge
        width, height = self._turning_neighbor_size(edge)
        if width is None or height is None:
            return edge
        geometry = Geometry(
            length=edge.geometry.length,
            shape="rectangular",
            width=width,
            height=height,
            diameter=edge.geometry.diameter,
        )
        return replace(edge, geometry=geometry, cooling_technology="turning")

    def _turning_neighbor_size(self, edge: EdgeSpec) -> tuple[float | None, float | None]:
        width_values: list[float] = []
        height_values: list[float] = []
        for adjacent in (
            *self._incoming.get(edge.from_node, []),
            *self._outgoing.get(edge.to_node, []),
        ):
            if adjacent.edge_id == edge.edge_id or adjacent.geometry.shape != "rectangular":
                continue
            if adjacent.geometry.width is not None:
                width_values.append(adjacent.geometry.width)
            if adjacent.geometry.height is not None:
                height_values.append(adjacent.geometry.height)
        width = sum(width_values) / len(width_values) if width_values else edge.geometry.width
        height = (
            sum(height_values) / len(height_values)
            if height_values
            else edge.geometry.height
        )
        return width, height

    def _global_reference_temperature(self) -> float:
        numerator = 0.0
        denominator = 0.0
        for node in self.network.nodes:
            if node.inlet_mdot is not None and node.inlet_temperature is not None:
                numerator += node.inlet_mdot * node.inlet_temperature
                denominator += node.inlet_mdot
        if denominator <= 0.0:
            raise ValueError("At least one inlet with positive mass flow is required.")
        return numerator / denominator

    def _make_inlet_result(self, node: NodeSpec) -> NodeResult:
        if node.inlet_mdot is None or node.inlet_mdot <= 0.0:
            raise ValueError(f"Inlet {node.node_id} requires positive inlet_mdot.")
        if node.inlet_temperature is None or node.inlet_temperature <= 0.0:
            raise ValueError(f"Inlet {node.node_id} requires positive inlet_temperature.")
        if node.inlet_pressure is None or node.inlet_pressure <= 0.0:
            raise ValueError(f"Inlet {node.node_id} requires positive inlet_pressure.")
        return NodeResult(
            node_id=node.node_id,
            kind=node.kind,
            mass_flow=node.inlet_mdot,
            temperature=node.inlet_temperature,
            pressure=node.inlet_pressure,
            outgoing_edges=tuple(edge.edge_id for edge in self._outgoing[node.node_id]),
        )

    def _make_node_result(
        self,
        node: NodeSpec,
        incoming_results: list[EdgeResult],
    ) -> NodeResult:
        total_mdot = sum(edge.mass_flow for edge in incoming_results)
        if total_mdot <= 0.0:
            raise ValueError(f"Node {node.node_id} received no positive mass flow.")
        temperature = (
            sum(edge.mass_flow * edge.outlet_temperature for edge in incoming_results)
            / total_mdot
        )
        pressures = [edge.outlet_pressure for edge in incoming_results]
        pressure = min(pressures)
        warnings: list[str] = []
        pressure_spread = max(pressures) - min(pressures)
        if len(pressures) > 1 and pressure_spread > self.options.merge_pressure_tolerance_pa:
            warnings.append(
                f"{node.node_id}: merge pressure spread is {pressure_spread:.1f} Pa. "
                "Fixed-flow mode does not rebalance branch flows."
            )
        return NodeResult(
            node_id=node.node_id,
            kind=node.kind,
            mass_flow=total_mdot,
            temperature=temperature,
            pressure=pressure,
            incoming_edges=tuple(edge.edge_id for edge in incoming_results),
            outgoing_edges=tuple(edge.edge_id for edge in self._outgoing[node.node_id]),
            warnings=tuple(warnings),
            details={"merge_pressure_spread_pa": pressure_spread},
        )

    def _outgoing_flows(
        self,
        node: NodeResult,
        outgoing: list[EdgeSpec],
    ) -> tuple[dict[str, float], list[str]]:
        if len(outgoing) == 1:
            edge = outgoing[0]
            return {edge.edge_id: edge.fixed_mdot or node.mass_flow}, []

        warnings: list[str] = []
        fixed = [edge for edge in outgoing if edge.fixed_mdot is not None]
        if fixed:
            flow_map = {edge.edge_id: float(edge.fixed_mdot or 0.0) for edge in outgoing}
            assigned = sum(flow_map.values())
            if abs(assigned - node.mass_flow) > max(1e-9, 1e-6 * node.mass_flow):
                warnings.append(
                    f"{node.node_id}: outgoing fixed_mdot sum {assigned:.6g} kg/s "
                    f"does not match node flow {node.mass_flow:.6g} kg/s."
                )
            return flow_map, warnings

        fractions = [edge.flow_fraction for edge in outgoing]
        if all(value is not None for value in fractions):
            total_fraction = sum(float(value) for value in fractions if value is not None)
            if total_fraction <= 0.0:
                raise ValueError(f"{node.node_id}: outgoing flow fractions must be positive.")
            if abs(total_fraction - 1.0) > 1e-9:
                warnings.append(
                    f"{node.node_id}: outgoing flow fractions were normalized from "
                    f"sum={total_fraction:.6g}."
                )
            return {
                edge.edge_id: node.mass_flow * float(edge.flow_fraction) / total_fraction
                for edge in outgoing
            }, warnings

        warnings.append(
            f"{node.node_id}: no split rule supplied; equal flow split was used."
        )
        equal_flow = node.mass_flow / len(outgoing)
        return {edge.edge_id: equal_flow for edge in outgoing}, warnings
