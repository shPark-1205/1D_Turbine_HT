from __future__ import annotations

from .models import EdgeSpec, Geometry, NetworkSpec, NodeSpec, WallBoundary


def build_default_network() -> NetworkSpec:
    """Return the first fixed-flow turbine internal-passage example."""

    inlet_t = 694.9
    inlet_p = 707_000.0
    hot_wall = WallBoundary(
        mode="external_convection",
        external_temperature=1150.0,
        external_htc=1200.0,
        wall_thickness=0.0015,
        wall_conductivity=18.0,
        tbc_thickness=0.00025,
        tbc_conductivity=1.2,
    )

    nodes = [
        NodeSpec(
            "1-1",
            kind="inlet",
            inlet_mdot=0.071,
            inlet_temperature=inlet_t,
            inlet_pressure=inlet_p,
        ),
        NodeSpec(
            "1-2",
            kind="inlet",
            inlet_mdot=0.057,
            inlet_temperature=inlet_t,
            inlet_pressure=inlet_p,
        ),
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
            },
        ),
        EdgeSpec(
            "3_to_4",
            "3",
            "4",
            Geometry(length=0.04, width=0.022, height=0.014),
            "turning",
            hot_wall,
            params={
                "c_nu": 1.5,
                "turn_angle_deg": 180.0,
            },
        ),
        EdgeSpec(
            "4_to_5",
            "4",
            "5",
            Geometry(length=0.24, width=0.017, height=0.017),
            "rib",
            hot_wall,
            params={
                "e_over_dh": 0.059,
                "p_over_e": 13.0,
                "angle_deg": 45.0,
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
            "turning",
            hot_wall,
            params={
                "c_nu": 1.5,
                "turn_angle_deg": 180.0,
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
            },
        ),
        EdgeSpec(
            "7_to_8",
            "7",
            "8",
            Geometry(length=0.065, width=0.100, height=0.011),
            "pin_fin",
            hot_wall,
            params={
                "pin_diameter": 0.004,
                "pin_height": 0.011,
                "pitch_x": 0.010,
                "pitch_s": 0.010,
            },
        ),
    ]
    return NetworkSpec(nodes=nodes, edges=edges)
