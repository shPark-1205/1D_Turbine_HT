from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite, pi, sin, sqrt
from typing import Any

from .models import EdgeResult, EdgeSpec, NodeResult, SolverOptions
from .properties import PropertyProvider, speed_of_sound


@dataclass(frozen=True)
class _HeatTransferResult:
    reynolds: float
    nusselt: float
    htc: float
    friction_factor_darcy: float
    velocity: float
    heat_transfer_area: float
    warnings: tuple[str, ...]
    intermediate: dict[str, Any]


def evaluate_edge(
    edge: EdgeSpec,
    inlet: NodeResult,
    mass_flow: float,
    property_provider: PropertyProvider,
    options: SolverOptions,
    global_reference_temperature: float,
) -> EdgeResult:
    if mass_flow <= 0.0:
        raise ValueError(f"Edge {edge.edge_id} mass flow must be positive.")
    if inlet.pressure <= 0.0:
        raise ValueError(
            f"{edge.edge_id}: inlet node {edge.from_node} pressure is "
            f"non-positive ({inlet.pressure:.1f} Pa). Upstream pressure loss "
            "already exceeded the available inlet pressure; check upstream "
            "geometry, K losses, mass flow, or parallel passage count."
        )
    if inlet.temperature <= 0.0:
        raise ValueError(
            f"{edge.edge_id}: inlet node {edge.from_node} temperature must be positive."
        )

    reference_temperature = (
        global_reference_temperature
        if options.htc_reference == "global_inlet"
        else inlet.temperature
    )
    properties = property_provider.air(reference_temperature, inlet.pressure)

    if edge.cooling_technology == "smooth":
        ht = _smooth(edge, mass_flow, properties)
    elif edge.cooling_technology == "rib":
        ht = _rib(edge, mass_flow, properties)
    elif edge.cooling_technology == "u_turn":
        ht = _u_turn(edge, mass_flow, properties)
    elif edge.cooling_technology == "pin_fin":
        ht = _pin_fin(edge, mass_flow, properties)
    else:
        raise ValueError(
            f"Unsupported cooling technology: {edge.cooling_technology}"
        )

    wall_warnings: list[str] = []
    heat_rate = _heat_rate(
        edge=edge,
        htc=ht.htc,
        area=ht.heat_transfer_area,
        inlet_temperature=inlet.temperature,
        reference_temperature=reference_temperature,
        options=options,
        warnings=wall_warnings,
    )
    energy_properties = property_provider.air(inlet.temperature, inlet.pressure)
    outlet_temperature = inlet.temperature + heat_rate / (
        mass_flow * energy_properties.cp
    )

    dynamic_head = 0.5 * properties.rho * ht.velocity**2
    dh = edge.geometry.hydraulic_diameter()
    dp_friction = (
        ht.friction_factor_darcy
        * (edge.geometry.length / dh)
        * dynamic_head
    )
    k_loss = _total_k_loss(edge)
    dp_minor = k_loss * dynamic_head
    dp_total = dp_friction + dp_minor
    outlet_pressure = inlet.pressure - dp_total

    mach = ht.velocity / speed_of_sound(properties)
    warnings = list(ht.warnings)
    warnings.extend(wall_warnings)
    if mach > 0.3:
        warnings.append(
            f"{edge.edge_id}: Mach={mach:.3f}; compressibility may matter."
        )
    if outlet_pressure <= 0.0:
        warnings.append(
            f"{edge.edge_id}: outlet pressure is non-positive; check inputs."
        )

    intermediate = dict(ht.intermediate)
    intermediate.update(
        {
            "dynamic_head_pa": dynamic_head,
            "hydraulic_diameter_m": dh,
            "flow_area_m2": edge.geometry.flow_area(),
            "wetted_perimeter_m": edge.geometry.wetted_perimeter(),
            "k_loss_total": k_loss,
            "mach": mach,
            "reference_temperature_k": reference_temperature,
        }
    )

    return EdgeResult(
        edge_id=edge.edge_id,
        from_node=edge.from_node,
        to_node=edge.to_node,
        cooling_technology=edge.cooling_technology,
        mass_flow=mass_flow,
        inlet_temperature=inlet.temperature,
        outlet_temperature=outlet_temperature,
        inlet_pressure=inlet.pressure,
        outlet_pressure=outlet_pressure,
        reynolds=ht.reynolds,
        nusselt=ht.nusselt,
        htc=ht.htc,
        friction_factor_darcy=ht.friction_factor_darcy,
        velocity=ht.velocity,
        heat_transfer_area=ht.heat_transfer_area,
        heat_rate=heat_rate,
        dp_friction=dp_friction,
        dp_minor=dp_minor,
        dp_total=dp_total,
        properties=properties,
        warnings=tuple(warnings),
        intermediate=intermediate,
    )


def _smooth(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    parallel_passages = _parallel_passages(edge)
    local_mass_flow = mass_flow / parallel_passages
    area = geom.flow_area()
    dh = geom.hydraulic_diameter()
    velocity = local_mass_flow / (properties.rho * area)
    reynolds = properties.rho * velocity * dh / properties.mu
    warnings = _common_internal_flow_warnings(edge.edge_id, reynolds, geom.length, dh)
    nusselt = 0.023 * reynolds**0.8 * properties.pr**0.3
    htc = nusselt * properties.k / dh
    f_darcy = _darcy_friction(reynolds) * float(edge.params.get("user_f_multiplier", 1.0))
    heat_area = geom.wetted_perimeter() * geom.length * parallel_passages
    return _HeatTransferResult(
        reynolds=reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=f_darcy,
        velocity=velocity,
        heat_transfer_area=heat_area,
        warnings=tuple(warnings),
        intermediate={
            "correlation": "Dittus-Boelter",
            "parallel_passages": parallel_passages,
            "local_mass_flow_kg_s": local_mass_flow,
        },
    )


def _rib(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    parallel_passages = _parallel_passages(edge)
    local_mass_flow = mass_flow / parallel_passages
    area = geom.flow_area()
    dh = geom.hydraulic_diameter()
    velocity = local_mass_flow / (properties.rho * area)
    reynolds = properties.rho * velocity * dh / properties.mu
    warnings = _common_internal_flow_warnings(edge.edge_id, reynolds, geom.length, dh)

    p = edge.params
    e_over_dh = _positive_param(p, "e_over_dh", edge.edge_id)
    p_over_e = _positive_param(p, "p_over_e", edge.edge_id)
    angle_deg = _positive_param(p, "angle_deg", edge.edge_id)
    aspect_ratio = geom.aspect_ratio()
    if aspect_ratio is None:
        raise ValueError(f"{edge.edge_id}: rib correlation needs rectangular geometry.")
    if not (30.0 <= angle_deg <= 90.0):
        warnings.append(
            f"{edge.edge_id}: rib angle is outside the usual 30-90 deg range."
        )

    f_darcy_smooth = _darcy_friction(reynolds)
    f_darcy = f_darcy_smooth * float(p.get("user_f_multiplier", 1.0))
    f_fanning = f_darcy / 4.0
    e_plus = e_over_dh * reynolds * sqrt(max(f_fanning / 2.0, 1e-30))
    r_e_plus = (
        (p_over_e / 10.0) ** 0.35
        * aspect_ratio**0.35
        * (
            12.31
            - 27.07 * (angle_deg / 90.0)
            + 17.86 * (angle_deg / 90.0) ** 2
        )
    )
    g_e_plus = (
        2.24
        * aspect_ratio**0.1
        * (angle_deg / 90.0) ** 0.35
        * (p_over_e / 10.0) ** 0.1
        * e_plus**0.35
    )
    denominator = (g_e_plus - r_e_plus) * sqrt(max(f_fanning / 2.0, 1e-30)) + 1.0
    if denominator <= 0.0:
        warnings.append(
            f"{edge.edge_id}: rib Stanton denominator <= 0; clipped for prototype."
        )
        denominator = 1e-12
    stanton = (f_fanning / 2.0) / denominator
    htc = stanton * properties.cp * properties.rho * velocity
    nusselt = htc * dh / properties.k
    heat_area = (
        geom.wetted_perimeter() * geom.length + _rib_extra_area(edge, dh)
    ) * parallel_passages

    return _HeatTransferResult(
        reynolds=reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=f_darcy,
        velocity=velocity,
        heat_transfer_area=heat_area,
        warnings=tuple(warnings),
        intermediate={
            "correlation": "Rib Stanton prototype",
            "e_plus": e_plus,
            "r_e_plus": r_e_plus,
            "g_e_plus": g_e_plus,
            "stanton": stanton,
            "fanning_friction_factor": f_fanning,
            "e_over_dh": e_over_dh,
            "p_over_e": p_over_e,
            "angle_deg": angle_deg,
            "aspect_ratio": aspect_ratio,
            "parallel_passages": parallel_passages,
            "local_mass_flow_kg_s": local_mass_flow,
        },
    )


def _u_turn(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    base = _smooth(edge, mass_flow, properties)
    multiplier = float(edge.params.get("nu_multiplier_turn", 1.0))
    nusselt = base.nusselt * multiplier
    htc = base.htc * multiplier
    intermediate = dict(base.intermediate)
    intermediate.update(
        {
            "correlation": "U-turn placeholder",
            "nu_multiplier_turn": multiplier,
            "turn_angle_deg": edge.params.get("turn_angle_deg"),
            "bend_radius_m": edge.params.get("bend_radius_m"),
            "turn_style": edge.params.get("turn_style"),
            "turn_clearance_m": edge.params.get("turn_clearance_m"),
            "upstream_width_m": edge.params.get("upstream_width_m"),
            "upstream_height_m": edge.params.get("upstream_height_m"),
            "downstream_width_m": edge.params.get("downstream_width_m"),
            "downstream_height_m": edge.params.get("downstream_height_m"),
        }
    )
    return _HeatTransferResult(
        reynolds=base.reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=base.friction_factor_darcy,
        velocity=base.velocity,
        heat_transfer_area=base.heat_transfer_area,
        warnings=base.warnings,
        intermediate=intermediate,
    )


def _pin_fin(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    if geom.shape != "rectangular":
        raise ValueError(f"{edge.edge_id}: pin-fin correlation needs rectangular geometry.")

    parallel_passages = _parallel_passages(edge)
    local_mass_flow = mass_flow / parallel_passages
    p = edge.params
    pin_diameter = _positive_param(p, "pin_diameter", edge.edge_id)
    pin_height = _positive_param(p, "pin_height", edge.edge_id)
    pitch_x = _positive_param(p, "pitch_x", edge.edge_id)
    pitch_s = _positive_param(p, "pitch_s", edge.edge_id)
    width = geom._require_positive(geom.width, "width")
    height = geom._require_positive(geom.height, "height")
    row_count = int(p.get("row_count") or max(1, floor(geom.length / pitch_x)))
    pins_cross = int(p.get("pins_cross") or max(1, floor(width / pitch_s)))
    total_pins = int(p.get("total_pins") or row_count * pins_cross)

    open_width = max(width - pins_cross * pin_diameter, 1e-9)
    blocked_height = min(pin_height, height)
    min_area = max(open_width * blocked_height, 1e-12)
    velocity_max = local_mass_flow / (properties.rho * min_area)
    reynolds = properties.rho * velocity_max * pin_diameter / properties.mu
    x_over_d = pitch_x / pin_diameter
    s_over_d = pitch_s / pin_diameter
    h_over_d = pin_height / pin_diameter
    warnings: list[str] = []
    if not (1.5 < x_over_d < 5.0):
        warnings.append(f"{edge.edge_id}: pin X/D is outside 1.5-5.0.")
    if abs(s_over_d - 2.5) > 0.25:
        warnings.append(
            f"{edge.edge_id}: Metzger pin correlation commonly assumes S/D near 2.5."
        )
    if not (0.5 <= h_over_d <= 3.0):
        warnings.append(f"{edge.edge_id}: pin H/D is outside 0.5-3.0.")
    if not (2_000.0 < reynolds < 100_000.0):
        warnings.append(f"{edge.edge_id}: pin Reynolds is outside 2,000-100,000.")

    nusselt = 0.135 * reynolds**0.69 * x_over_d**-0.34
    htc = nusselt * properties.k / pin_diameter
    dh = geom.hydraulic_diameter()
    bulk_area = geom.flow_area()
    bulk_velocity = local_mass_flow / (properties.rho * bulk_area)
    re_bulk = properties.rho * bulk_velocity * dh / properties.mu
    f_darcy = _darcy_friction(re_bulk) * float(p.get("user_f_multiplier", 1.0))
    base_area = geom.wetted_perimeter() * geom.length
    lateral_area = total_pins * pi * pin_diameter * pin_height
    tip_area = total_pins * pi * pin_diameter**2 / 4.0
    heat_area = (base_area + lateral_area + tip_area) * parallel_passages

    return _HeatTransferResult(
        reynolds=reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=f_darcy,
        velocity=bulk_velocity,
        heat_transfer_area=heat_area,
        warnings=tuple(warnings),
        intermediate={
            "correlation": "Metzger pin-fin prototype",
            "bulk_reynolds": re_bulk,
            "bulk_velocity_m_s": bulk_velocity,
            "v_max_m_s": velocity_max,
            "min_flow_area_m2": min_area,
            "pin_diameter_m": pin_diameter,
            "pin_height_m": pin_height,
            "pitch_x_m": pitch_x,
            "pitch_s_m": pitch_s,
            "x_over_d": x_over_d,
            "s_over_d": s_over_d,
            "h_over_d": h_over_d,
            "row_count": row_count,
            "pins_cross": pins_cross,
            "total_pins": total_pins,
            "pin_lateral_area_m2": lateral_area,
            "pin_tip_area_m2": tip_area,
            "parallel_passages": parallel_passages,
            "local_mass_flow_kg_s": local_mass_flow,
        },
    )


def _heat_rate(
    edge: EdgeSpec,
    htc: float,
    area: float,
    inlet_temperature: float,
    reference_temperature: float,
    options: SolverOptions,
    warnings: list[str],
) -> float:
    wall = edge.wall
    if wall.external_htc is not None:
        warnings.append(
            f"{edge.edge_id}: external_htc is stored but wall conduction is not coupled yet."
        )
    if wall.mode == "adiabatic":
        return 0.0
    if wall.mode == "wall_temperature":
        if wall.wall_temperature is None:
            raise ValueError(f"{edge.edge_id}: wall_temperature is required.")
        fluid_temperature = (
            reference_temperature
            if options.thermal_driving_temperature == "reference"
            else inlet_temperature
        )
        return htc * area * (wall.wall_temperature - fluid_temperature)
    if wall.mode == "heat_flux":
        if wall.heat_flux is None:
            raise ValueError(f"{edge.edge_id}: heat_flux is required.")
        return wall.heat_flux * area
    raise ValueError(f"Unsupported wall mode: {wall.mode}")


def _darcy_friction(reynolds: float) -> float:
    if reynolds <= 0.0 or not isfinite(reynolds):
        raise ValueError("Reynolds number must be finite and positive.")
    if reynolds < 2300.0:
        return 64.0 / reynolds
    if reynolds < 4000.0:
        laminar = 64.0 / reynolds
        turbulent = 0.3164 * reynolds**-0.25
        weight = (reynolds - 2300.0) / (4000.0 - 2300.0)
        return (1.0 - weight) * laminar + weight * turbulent
    return 0.3164 * reynolds**-0.25


def _common_internal_flow_warnings(
    edge_id: str,
    reynolds: float,
    length: float,
    hydraulic_diameter: float,
) -> list[str]:
    warnings: list[str] = []
    if reynolds < 10_000.0:
        warnings.append(
            f"{edge_id}: Re={reynolds:.0f}; Dittus-Boelter-style turbulent correlation is extrapolated."
        )
    if length / hydraulic_diameter < 10.0:
        warnings.append(
            f"{edge_id}: L/Dh={length / hydraulic_diameter:.1f}; developing-flow effects may matter."
        )
    return warnings


def _positive_param(params: dict[str, Any], name: str, edge_id: str) -> float:
    value = params.get(name)
    if value is None or float(value) <= 0.0:
        raise ValueError(f"{edge_id}: parameter {name} must be positive.")
    return float(value)


def _parallel_passages(edge: EdgeSpec) -> float:
    value = float(edge.params.get("parallel_passages", 1.0))
    if value <= 0.0:
        raise ValueError(f"{edge.edge_id}: parallel_passages must be positive.")
    return value


def _rib_extra_area(edge: EdgeSpec, hydraulic_diameter: float) -> float:
    geom = edge.geometry
    params = edge.params
    if geom.shape != "rectangular":
        return 0.0
    width = geom._require_positive(geom.width, "width")
    e_over_dh = _positive_param(params, "e_over_dh", edge.edge_id)
    p_over_e = _positive_param(params, "p_over_e", edge.edge_id)
    angle_deg = _positive_param(params, "angle_deg", edge.edge_id)
    rib_height = e_over_dh * hydraulic_diameter
    pitch = p_over_e * rib_height
    rib_count = int(params.get("rib_count") or max(0, floor(geom.length / pitch)))
    rib_width = float(params.get("rib_width", rib_height))
    ribbed_walls = int(params.get("ribbed_walls", 2))
    sin_angle = max(sin(angle_deg * pi / 180.0), 1e-6)
    rib_span = width / sin_angle
    exposed_area_per_rib = rib_span * (rib_width + 2.0 * rib_height)
    return ribbed_walls * rib_count * exposed_area_per_rib


def _total_k_loss(edge: EdgeSpec) -> float:
    params = edge.params
    return (
        float(params.get("user_K_loss", 0.0))
        + float(params.get("k_loss", 0.0))
        + float(params.get("k_turn", 0.0))
    )
