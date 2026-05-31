from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite, log, pi, sin, sqrt
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
    elif edge.cooling_technology in {"turning", "u_turn"}:
        ht = _turning(edge, mass_flow, properties)
    elif edge.cooling_technology == "pin_fin":
        ht = _pin_fin(edge, mass_flow, properties)
    else:
        raise ValueError(
            f"Unsupported cooling technology: {edge.cooling_technology}"
        )

    wall_warnings: list[str] = []
    heat_rate, wall_intermediate = _heat_rate(
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
    dp_length_scale = float(ht.intermediate.get("pressure_loss_diameter_m", dh))
    dp_friction = (
        ht.friction_factor_darcy
        * (edge.geometry.length / dp_length_scale)
        * dynamic_head
    )
    dp_rotation = _rotation_pressure_loss(edge, properties)
    dp_total = dp_friction + dp_rotation
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
            "pressure_loss_diameter_m": dp_length_scale,
            "flow_area_m2": edge.geometry.flow_area(),
            "wetted_perimeter_m": edge.geometry.wetted_perimeter(),
            "dp_rotation_pa": dp_rotation,
            "mach": mach,
            "reference_temperature_k": reference_temperature,
        }
    )
    intermediate.update(wall_intermediate)

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
        dp_rotation=dp_rotation,
        dp_minor=dp_rotation,
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
    area = geom.flow_area()
    dh = geom.hydraulic_diameter()
    velocity = mass_flow / (properties.rho * area)
    reynolds = properties.rho * velocity * dh / properties.mu
    warnings = _common_internal_flow_warnings(edge.edge_id, reynolds, geom.length, dh)
    nusselt_db = _dittus_boelter(reynolds, properties.pr)
    c_nu = float(edge.params.get("c_nu", 1.0))
    nusselt = c_nu * nusselt_db
    htc = nusselt * properties.k / dh
    f_darcy = _smooth_friction(reynolds)
    heat_area = geom.wetted_perimeter() * geom.length
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
            "nusselt_db": nusselt_db,
            "c_nu": c_nu,
        },
    )


def _rib(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    area = geom.flow_area()
    dh = geom.hydraulic_diameter()
    velocity = mass_flow / (properties.rho * area)
    reynolds = properties.rho * velocity * dh / properties.mu
    warnings = _common_internal_flow_warnings(edge.edge_id, reynolds, geom.length, dh)

    p = edge.params
    e_over_dh = _positive_param(p, "e_over_dh", edge.edge_id)
    p_over_e = _positive_param(p, "p_over_e", edge.edge_id)
    angle_deg = _positive_param(p, "angle_deg", edge.edge_id)
    aspect_ratio = geom.aspect_ratio()
    if aspect_ratio is None:
        raise ValueError(f"{edge.edge_id}: rib correlation needs rectangular geometry.")
    width = geom._require_positive(geom.width, "width")
    height = geom._require_positive(geom.height, "height")
    aspect_ratio_used = min(aspect_ratio, 2.0)
    m_exp = 0.0 if abs(angle_deg - 90.0) < 1e-9 else 0.35
    if not (30.0 <= angle_deg <= 90.0):
        warnings.append(
            f"{edge.edge_id}: rib angle is outside the usual 30-90 deg range."
        )
    if aspect_ratio > 2.0:
        warnings.append(f"{edge.edge_id}: rib AR={aspect_ratio:.3g}; AR=2 was used.")

    f_darcy, e_plus, r_e_plus, converged, iterations = _solve_rib_friction(
        edge_id=edge.edge_id,
        reynolds=reynolds,
        e_over_dh=e_over_dh,
        p_over_e=p_over_e,
        angle_deg=angle_deg,
        width=width,
        height=height,
        aspect_ratio_used=aspect_ratio_used,
        m_exp=m_exp,
    )
    if not converged:
        warnings.append(
            f"{edge.edge_id}: rib friction iteration did not converge; last value was used."
        )
    g_e_plus = (
        2.24
        * aspect_ratio_used**0.1
        * (angle_deg / 90.0) ** m_exp
        * (p_over_e / 10.0) ** 0.1
        * e_plus**0.35
    )
    denominator = (g_e_plus - r_e_plus) * sqrt(max(f_darcy / 2.0, 1e-30)) + 1.0
    if denominator <= 0.0:
        warnings.append(
            f"{edge.edge_id}: rib Stanton denominator <= 0; clipped for prototype."
        )
        denominator = 1e-12
    stanton = (f_darcy / 2.0) / denominator
    htc = stanton * properties.cp * properties.rho * velocity
    nusselt = htc * dh / properties.k
    heat_area = geom.wetted_perimeter() * geom.length + _rib_extra_area(edge, dh)

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
            "e_over_dh": e_over_dh,
            "p_over_e": p_over_e,
            "angle_deg": angle_deg,
            "aspect_ratio": aspect_ratio,
            "aspect_ratio_used": aspect_ratio_used,
            "m_exponent": m_exp,
            "rib_friction_iterations": iterations,
            "rib_friction_converged": converged,
        },
    )


def _turning(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    area = geom.flow_area()
    dh = geom.hydraulic_diameter()
    velocity = mass_flow / (properties.rho * area)
    reynolds = properties.rho * velocity * dh / properties.mu
    warnings = _common_internal_flow_warnings(edge.edge_id, reynolds, geom.length, dh)
    c_nu = float(edge.params.get("c_nu", edge.params.get("nu_multiplier_turn", 1.5)))
    nusselt_db = _dittus_boelter(reynolds, properties.pr)
    nusselt = c_nu * nusselt_db
    htc = nusselt * properties.k / dh
    f_darcy = 3.0 * _smooth_friction(reynolds)
    turn_angle = float(edge.params.get("turn_angle_deg", 180.0))
    if not (0.0 < turn_angle <= 180.0):
        warnings.append(f"{edge.edge_id}: turn angle should be between 0 and 180 deg.")

    return _HeatTransferResult(
        reynolds=reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=f_darcy,
        velocity=velocity,
        heat_transfer_area=geom.wetted_perimeter() * geom.length,
        warnings=tuple(warnings),
        intermediate={
            "correlation": "Turning: 3 x smooth-channel friction, C_Nu x Dittus-Boelter",
            "nusselt_db": nusselt_db,
            "c_nu": c_nu,
            "turn_angle_deg": turn_angle,
            "smooth_friction_factor": f_darcy / 3.0,
        },
    )


def _pin_fin(
    edge: EdgeSpec,
    mass_flow: float,
    properties,
) -> _HeatTransferResult:
    geom = edge.geometry
    if geom.shape != "rectangular":
        raise ValueError(f"{edge.edge_id}: pin-fin correlation needs rectangular geometry.")

    p = edge.params
    pin_diameter = _positive_param(p, "pin_diameter", edge.edge_id)
    pin_height = _positive_param(p, "pin_height", edge.edge_id)
    pitch_x = _positive_param(p, "pitch_x", edge.edge_id)
    pitch_s = _positive_param(p, "pitch_s", edge.edge_id)
    width = geom._require_positive(geom.width, "width")
    height = geom._require_positive(geom.height, "height")
    row_count = max(1, floor(geom.length / pitch_x))
    pins_cross = max(1, floor(width / pitch_s))
    total_pins = int(p.get("total_pins") or row_count * pins_cross)

    pin_projected_area = pins_cross * pin_diameter * min(pin_height, height)
    min_area = width * height - pin_projected_area
    if min_area <= 0.0:
        raise ValueError(
            f"{edge.edge_id}: pin-fin blockage leaves no positive flow area."
        )
    velocity_max = mass_flow / (properties.rho * min_area)
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

    nusselt = 0.135 * reynolds**0.69 * s_over_d**-0.34
    htc = nusselt * properties.k / pin_diameter
    bulk_area = geom.flow_area()
    bulk_velocity = mass_flow / (properties.rho * bulk_area)
    dh = geom.hydraulic_diameter()
    re_bulk = properties.rho * bulk_velocity * dh / properties.mu
    f_darcy = 4.0 * 1.76 * reynolds**-0.318
    base_area = geom.wetted_perimeter() * geom.length
    lateral_area = total_pins * pi * pin_diameter * pin_height
    tip_area = total_pins * pi * pin_diameter**2 / 4.0
    heat_area = base_area + lateral_area + tip_area

    return _HeatTransferResult(
        reynolds=reynolds,
        nusselt=nusselt,
        htc=htc,
        friction_factor_darcy=f_darcy,
        velocity=velocity_max,
        heat_transfer_area=heat_area,
        warnings=tuple(warnings),
        intermediate={
            "correlation": "Metzger pin-fin prototype",
            "bulk_reynolds": re_bulk,
            "bulk_velocity_m_s": bulk_velocity,
            "v_max_m_s": velocity_max,
            "min_flow_area_m2": min_area,
            "pin_projected_area_m2": pin_projected_area,
            "pressure_loss_diameter_m": pin_diameter,
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
) -> tuple[float, dict[str, Any]]:
    wall = edge.wall
    details: dict[str, Any] = {"wall_mode": wall.mode}
    if wall.mode == "adiabatic":
        details["heat_flux_w_m2"] = 0.0
        return 0.0, details
    if wall.mode == "wall_temperature":
        if wall.wall_temperature is None:
            raise ValueError(f"{edge.edge_id}: wall_temperature is required.")
        fluid_temperature = (
            reference_temperature
            if options.thermal_driving_temperature == "reference"
            else inlet_temperature
        )
        heat_rate = htc * area * (wall.wall_temperature - fluid_temperature)
        details.update(
            {
                "thermal_area_m2": area,
                "fluid_reference_temperature_k": fluid_temperature,
                "coolant_side_wall_temperature_k": wall.wall_temperature,
                "heat_flux_w_m2": heat_rate / area,
            }
        )
        return heat_rate, details
    if wall.mode == "heat_flux":
        if wall.heat_flux is None:
            raise ValueError(f"{edge.edge_id}: heat_flux is required.")
        heat_rate = wall.heat_flux * area
        details.update(
            {
                "thermal_area_m2": area,
                "heat_flux_w_m2": wall.heat_flux,
            }
        )
        return heat_rate, details
    if wall.mode == "external_convection":
        return _external_convection_heat_rate(
            edge=edge,
            wall=wall,
            htc=htc,
            area=area,
            inlet_temperature=inlet_temperature,
            reference_temperature=reference_temperature,
            options=options,
        )
    raise ValueError(f"Unsupported wall mode: {wall.mode}")


def _external_convection_heat_rate(
    edge: EdgeSpec,
    wall,
    htc: float,
    area: float,
    inlet_temperature: float,
    reference_temperature: float,
    options: SolverOptions,
) -> tuple[float, dict[str, Any]]:
    if area <= 0.0:
        raise ValueError(f"{edge.edge_id}: heat-transfer area must be positive.")
    if htc <= 0.0:
        raise ValueError(f"{edge.edge_id}: internal HTC must be positive.")
    external_temperature = _positive_wall_value(
        wall.external_temperature,
        "external_temperature",
        edge.edge_id,
    )
    external_htc = _positive_wall_value(
        wall.external_htc,
        "external_htc",
        edge.edge_id,
    )
    wall_thickness = _nonnegative_wall_value(
        wall.wall_thickness,
        "wall_thickness",
        edge.edge_id,
    )
    wall_conductivity = _layer_conductivity(
        wall.wall_conductivity,
        wall_thickness,
        "wall_conductivity",
        edge.edge_id,
    )
    tbc_thickness = _nonnegative_wall_value(
        wall.tbc_thickness,
        "tbc_thickness",
        edge.edge_id,
        default=0.0,
    )
    tbc_conductivity = _layer_conductivity(
        wall.tbc_conductivity,
        tbc_thickness,
        "tbc_conductivity",
        edge.edge_id,
    )
    fluid_temperature = (
        reference_temperature
        if options.thermal_driving_temperature == "reference"
        else inlet_temperature
    )

    r_internal = 1.0 / (htc * area)
    r_wall = wall_thickness / (wall_conductivity * area) if wall_thickness else 0.0
    r_tbc = tbc_thickness / (tbc_conductivity * area) if tbc_thickness else 0.0
    r_external = 1.0 / (external_htc * area)
    r_total = r_internal + r_wall + r_tbc + r_external
    heat_rate = (external_temperature - fluid_temperature) / r_total

    coolant_side_wall_t = fluid_temperature + heat_rate * r_internal
    metal_outer_t = coolant_side_wall_t + heat_rate * r_wall
    tbc_outer_t = metal_outer_t + heat_rate * r_tbc
    details = {
        "wall_mode": "external_convection",
        "thermal_area_m2": area,
        "fluid_reference_temperature_k": fluid_temperature,
        "external_temperature_k": external_temperature,
        "external_htc_w_m2_k": external_htc,
        "wall_thickness_m": wall_thickness,
        "wall_conductivity_w_m_k": wall_conductivity,
        "tbc_thickness_m": tbc_thickness,
        "tbc_conductivity_w_m_k": tbc_conductivity,
        "r_internal_k_w": r_internal,
        "r_wall_k_w": r_wall,
        "r_tbc_k_w": r_tbc,
        "r_external_k_w": r_external,
        "r_total_k_w": r_total,
        "heat_flux_w_m2": heat_rate / area,
        "coolant_side_wall_temperature_k": coolant_side_wall_t,
        "metal_outer_temperature_k": metal_outer_t,
        "tbc_outer_temperature_k": tbc_outer_t,
    }
    return heat_rate, details


def _positive_wall_value(value: float | None, name: str, edge_id: str) -> float:
    if value is None or value <= 0.0:
        raise ValueError(f"{edge_id}: {name} must be positive.")
    return value


def _nonnegative_wall_value(
    value: float | None,
    name: str,
    edge_id: str,
    default: float | None = None,
) -> float:
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"{edge_id}: {name} is required.")
    if value < 0.0:
        raise ValueError(f"{edge_id}: {name} must be non-negative.")
    return value


def _layer_conductivity(
    value: float | None,
    thickness: float,
    name: str,
    edge_id: str,
) -> float:
    if thickness == 0.0:
        return 1.0
    if value is None or value <= 0.0:
        raise ValueError(
            f"{edge_id}: {name} must be positive when layer thickness is set."
        )
    return value


def _dittus_boelter(reynolds: float, prandtl: float) -> float:
    return 0.023 * reynolds**0.8 * prandtl**0.3


def _smooth_friction(reynolds: float) -> float:
    if reynolds <= 0.0 or not isfinite(reynolds):
        raise ValueError("Reynolds number must be finite and positive.")
    denominator = 2.236 * log(reynolds) - 4.639
    if denominator <= 0.0:
        raise ValueError(
            "Smooth-channel friction correlation denominator must be positive."
        )
    return 2.0 * denominator**-2.0


def _solve_rib_friction(
    edge_id: str,
    reynolds: float,
    e_over_dh: float,
    p_over_e: float,
    angle_deg: float,
    width: float,
    height: float,
    aspect_ratio_used: float,
    m_exp: float,
) -> tuple[float, float, float, bool, int]:
    friction = _smooth_friction(reynolds)
    r_e_plus = 0.0
    e_plus = 0.0
    for iteration in range(1, 61):
        e_plus = e_over_dh * reynolds * sqrt(max(friction / 2.0, 1e-30))
        r_e_plus = _rib_roughness_function(
            p_over_e=p_over_e,
            aspect_ratio_used=aspect_ratio_used,
            angle_deg=angle_deg,
            m_exp=m_exp,
        )
        log_argument = (2.0 * e_over_dh) * (2.0 * width / (width + height))
        if log_argument <= 0.0:
            raise ValueError(f"{edge_id}: rib friction log argument must be positive.")
        bracket = r_e_plus - 2.5 * log(log_argument) - 2.5
        if abs(bracket) < 1e-12:
            raise ValueError(f"{edge_id}: rib friction denominator is near zero.")
        next_friction = 0.5 * bracket**-2.0
        relaxed = 0.5 * friction + 0.5 * next_friction
        if abs(relaxed - friction) <= max(1e-9, 1e-6 * abs(friction)):
            friction = relaxed
            e_plus = e_over_dh * reynolds * sqrt(max(friction / 2.0, 1e-30))
            return friction, e_plus, r_e_plus, True, iteration
        friction = relaxed
    e_plus = e_over_dh * reynolds * sqrt(max(friction / 2.0, 1e-30))
    return friction, e_plus, r_e_plus, False, 60


def _rib_roughness_function(
    p_over_e: float,
    aspect_ratio_used: float,
    angle_deg: float,
    m_exp: float,
) -> float:
    angle_ratio = angle_deg / 90.0
    return (
        (p_over_e / 10.0) ** 0.35
        * aspect_ratio_used**m_exp
        * (12.31 - 27.07 * angle_ratio + 17.86 * angle_ratio**2)
    )


def _rotation_pressure_loss(edge: EdgeSpec, properties) -> float:
    if edge.cooling_technology != "rib":
        return 0.0
    radius = float(edge.params.get("radius_m", 1.23))
    rpm = float(edge.params.get("rpm", 3000.0))
    c_rotation = float(edge.params.get("c_rotation", 1.056))
    if radius < 0.0 or rpm < 0.0 or c_rotation < 0.0:
        raise ValueError(f"{edge.edge_id}: rotation parameters must be non-negative.")
    rotation_speed = rpm * radius * pi / 60.0
    return properties.rho * c_rotation * rotation_speed**2 * edge.geometry.length


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
