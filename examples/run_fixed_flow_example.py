from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal_passage_1d import (
    EdgeSpec,
    FixedFlowSolver,
    Geometry,
    NetworkSpec,
    NodeSpec,
    SolverOptions,
    WallBoundary,
)


def build_example_network() -> NetworkSpec:
    inlet_t = 694.9
    inlet_p = 707_000.0
    hot_wall = WallBoundary(mode="wall_temperature", wall_temperature=950.0)

    nodes = [
        NodeSpec("1-1", kind="inlet", inlet_mdot=0.071, inlet_temperature=inlet_t, inlet_pressure=inlet_p),
        NodeSpec("1-2", kind="inlet", inlet_mdot=0.057, inlet_temperature=inlet_t, inlet_pressure=inlet_p),
        NodeSpec("2", kind="internal"),
        NodeSpec("3", kind="internal"),
        NodeSpec("4", kind="internal"),
        NodeSpec("5", kind="merge"),
        NodeSpec("6", kind="internal"),
        NodeSpec("7", kind="internal"),
        NodeSpec("8", kind="outlet"),
    ]

    edges = [
        EdgeSpec(
            "1-1_to_2",
            "1-1",
            "2",
            Geometry(length=0.09, shape="circular", diameter=0.019),
            "smooth",
            hot_wall,
        ),
        EdgeSpec(
            "2_to_3",
            "2",
            "3",
            Geometry(length=0.22, width=0.027, height=0.010),
            "rib",
            hot_wall,
            params={
                "e_over_dh": 0.069,
                "p_over_e": 11.0,
                "angle_deg": 45.0,
                "user_f_multiplier": 2.0,
            },
        ),
        EdgeSpec(
            "3_to_4",
            "3",
            "4",
            Geometry(length=0.04, width=0.022, height=0.014),
            "u_turn",
            hot_wall,
            params={
                "nu_multiplier_turn": 1.25,
                "k_turn": 1.0,
                "turn_angle_deg": 180.0,
                "bend_radius_m": 0.012,
                "turn_style": "sharp",
                "turn_clearance_m": 0.014,
                "upstream_width_m": 0.027,
                "upstream_height_m": 0.010,
                "downstream_width_m": 0.017,
                "downstream_height_m": 0.170,
            },
        ),
        EdgeSpec(
            "4_to_5",
            "4",
            "5",
            Geometry(length=0.24, width=0.017, height=0.170),
            "rib",
            hot_wall,
            params={
                "e_over_dh": 0.059,
                "p_over_e": 13.0,
                "angle_deg": 45.0,
                "user_f_multiplier": 2.0,
            },
        ),
        EdgeSpec(
            "1-2_to_5",
            "1-2",
            "5",
            Geometry(length=0.105, width=0.026, height=0.007),
            "smooth",
            hot_wall,
        ),
        EdgeSpec(
            "5_to_6",
            "5",
            "6",
            Geometry(length=0.03, width=0.024, height=0.014),
            "u_turn",
            hot_wall,
            params={
                "nu_multiplier_turn": 1.30,
                "k_turn": 1.0,
                "turn_angle_deg": 180.0,
                "bend_radius_m": 0.012,
                "turn_style": "sharp",
                "turn_clearance_m": 0.014,
                "upstream_width_m": 0.017,
                "upstream_height_m": 0.170,
                "downstream_width_m": 0.030,
                "downstream_height_m": 0.010,
            },
        ),
        EdgeSpec(
            "6_to_7",
            "6",
            "7",
            Geometry(length=0.24, width=0.030, height=0.010),
            "rib",
            hot_wall,
            params={
                "e_over_dh": 0.067,
                "p_over_e": 7.0,
                "angle_deg": 45.0,
                "user_f_multiplier": 2.0,
            },
        ),
        EdgeSpec(
            "7_to_8",
            "7",
            "8",
            Geometry(length=0.065, width=0.004, height=0.011),
            "pin_fin",
            hot_wall,
            params={
                "pin_diameter": 0.001,
                "pin_height": 0.011,
                "pitch_x": 0.004,
                "pitch_s": 0.002,
                "row_count": 16,
                "pins_cross": 2,
                "user_f_multiplier": 3.0,
                "user_K_loss": 2.0,
            },
        ),
    ]
    return NetworkSpec(nodes=nodes, edges=edges)


def main() -> None:
    network = build_example_network()
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
    print("edge, tech, Re, Nu, h[W/m2-K], f_D, dp[Pa], q[W], Tout[K]")
    for edge_id, edge in result.edges.items():
        print(
            f"{edge_id}, {edge.cooling_technology}, {edge.reynolds:.0f}, "
            f"{edge.nusselt:.2f}, {edge.htc:.2f}, "
            f"{edge.friction_factor_darcy:.5f}, {edge.dp_total:.1f}, "
            f"{edge.heat_rate:.1f}, {edge.outlet_temperature:.2f}"
        )

    if result.warnings:
        print("\nWarnings")
        for warning in result.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
