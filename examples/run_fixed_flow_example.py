from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal_passage_1d import FixedFlowSolver, SolverOptions
from internal_passage_1d.sample_cases import build_default_network


def main() -> None:
    network = build_default_network()
    result = FixedFlowSolver(
        network,
        SolverOptions(property_model="ideal_gas"),
    ).solve()

    print(f"Reference temperature: {result.reference_temperature:.2f} K")
    print("\nNode results")
    print("node, kind, mdot[kg/s], T[K], P[Pa]")
    for node_id, node in result.nodes.items():
        print(
            f"{node_id}, {node.kind}, {node.mass_flow:.6f}, "
            f"{node.temperature:.2f}, {node.pressure:.1f}"
        )

    print("\nEdge results")
    print(
        "edge, tech, Re, Nu, h[W/m2-K], f_D, "
        "dp_friction[Pa], dp_rotation[Pa], dp_total[Pa], "
        "q[W], qflux[W/m2], Twall_i[K], Tout[K]"
    )
    for edge_id, edge in result.edges.items():
        print(
            f"{edge_id}, {edge.cooling_technology}, {edge.reynolds:.0f}, "
            f"{edge.nusselt:.2f}, {edge.htc:.2f}, "
            f"{edge.friction_factor_darcy:.5f}, {edge.dp_friction:.1f}, "
            f"{edge.dp_rotation:.1f}, {edge.dp_total:.1f}, "
            f"{edge.heat_rate:.1f}, "
            f"{edge.intermediate.get('heat_flux_w_m2', 0.0):.1f}, "
            f"{edge.intermediate.get('coolant_side_wall_temperature_k', 0.0):.2f}, "
            f"{edge.outlet_temperature:.2f}"
        )

    if result.warnings:
        print("\nWarnings")
        for warning in result.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
