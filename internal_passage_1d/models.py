from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from typing import Any, Literal


NodeKind = Literal["inlet", "internal", "merge", "split", "outlet"]
WallMode = Literal["adiabatic", "wall_temperature", "heat_flux"]
GeometryShape = Literal["rectangular", "circular"]
CoolingTechnology = Literal["smooth", "rib", "u_turn", "pin_fin"]
PropertyModel = Literal["ideal_gas", "coolprop"]


@dataclass(frozen=True)
class Geometry:
    """Edge geometry in SI units."""

    length: float
    shape: GeometryShape = "rectangular"
    width: float | None = None
    height: float | None = None
    diameter: float | None = None

    def flow_area(self) -> float:
        if self.shape == "circular":
            diameter = self._require_positive(self.diameter, "diameter")
            return pi * diameter**2 / 4.0
        width = self._require_positive(self.width, "width")
        height = self._require_positive(self.height, "height")
        return width * height

    def wetted_perimeter(self) -> float:
        if self.shape == "circular":
            diameter = self._require_positive(self.diameter, "diameter")
            return pi * diameter
        width = self._require_positive(self.width, "width")
        height = self._require_positive(self.height, "height")
        return 2.0 * (width + height)

    def hydraulic_diameter(self) -> float:
        if self.shape == "circular":
            return self._require_positive(self.diameter, "diameter")
        return 4.0 * self.flow_area() / self.wetted_perimeter()

    def aspect_ratio(self) -> float | None:
        if self.shape != "rectangular":
            return None
        width = self._require_positive(self.width, "width")
        height = self._require_positive(self.height, "height")
        return width / height

    @staticmethod
    def _require_positive(value: float | None, name: str) -> float:
        if value is None or value <= 0.0:
            raise ValueError(f"Geometry {name} must be a positive number.")
        return value


@dataclass(frozen=True)
class WallBoundary:
    """Thermal boundary condition for an edge."""

    mode: WallMode = "adiabatic"
    wall_temperature: float | None = None
    heat_flux: float | None = None
    external_htc: float | None = None


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    kind: NodeKind = "internal"
    inlet_mdot: float | None = None
    inlet_temperature: float | None = None
    inlet_pressure: float | None = None


@dataclass(frozen=True)
class EdgeSpec:
    edge_id: str
    from_node: str
    to_node: str
    geometry: Geometry
    cooling_technology: CoolingTechnology = "smooth"
    wall: WallBoundary = field(default_factory=WallBoundary)
    params: dict[str, Any] = field(default_factory=dict)
    flow_fraction: float | None = None
    fixed_mdot: float | None = None


@dataclass(frozen=True)
class NetworkSpec:
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    fluid: str = "Air"


@dataclass(frozen=True)
class SolverOptions:
    property_model: PropertyModel = "ideal_gas"
    htc_reference: Literal["global_inlet", "edge_inlet"] = "global_inlet"
    thermal_driving_temperature: Literal["reference", "edge_inlet"] = "reference"
    merge_pressure_tolerance_pa: float = 100.0


@dataclass(frozen=True)
class AirProperties:
    temperature: float
    pressure: float
    rho: float
    mu: float
    k: float
    cp: float
    pr: float
    gamma: float
    r_specific: float


@dataclass(frozen=True)
class NodeResult:
    node_id: str
    kind: NodeKind
    mass_flow: float
    temperature: float
    pressure: float
    incoming_edges: tuple[str, ...] = ()
    outgoing_edges: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeResult:
    edge_id: str
    from_node: str
    to_node: str
    cooling_technology: CoolingTechnology
    mass_flow: float
    inlet_temperature: float
    outlet_temperature: float
    inlet_pressure: float
    outlet_pressure: float
    reynolds: float
    nusselt: float
    htc: float
    friction_factor_darcy: float
    velocity: float
    heat_transfer_area: float
    heat_rate: float
    dp_friction: float
    dp_minor: float
    dp_total: float
    properties: AirProperties
    warnings: tuple[str, ...] = ()
    intermediate: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SolverResult:
    nodes: dict[str, NodeResult]
    edges: dict[str, EdgeResult]
    warnings: tuple[str, ...]
    reference_temperature: float
