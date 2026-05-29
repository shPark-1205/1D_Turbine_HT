from __future__ import annotations

from math import sqrt
from typing import Protocol

from .models import AirProperties


class PropertyProvider(Protocol):
    def air(self, temperature: float, pressure: float) -> AirProperties:
        """Return air properties at temperature [K] and pressure [Pa]."""


class IdealGasAir:
    """Simple ideal-gas air properties for early solver development."""

    r_specific = 287.05287
    cp = 1007.0
    pr = 0.71
    gamma = 1.4
    sutherland_t0 = 273.15
    sutherland_mu0 = 1.716e-5
    sutherland_s = 110.4

    def air(self, temperature: float, pressure: float) -> AirProperties:
        if temperature <= 0.0:
            raise ValueError("Temperature must be positive.")
        if pressure <= 0.0:
            raise ValueError("Pressure must be positive.")

        rho = pressure / (self.r_specific * temperature)
        mu = self.sutherland_mu0 * (
            (temperature / self.sutherland_t0) ** 1.5
            * (self.sutherland_t0 + self.sutherland_s)
            / (temperature + self.sutherland_s)
        )
        k = self.cp * mu / self.pr
        return AirProperties(
            temperature=temperature,
            pressure=pressure,
            rho=rho,
            mu=mu,
            k=k,
            cp=self.cp,
            pr=self.pr,
            gamma=self.gamma,
            r_specific=self.r_specific,
        )


class CoolPropAir:
    """CoolProp-backed air properties.

    CoolProp is optional. Import is delayed so the base solver remains usable
    without external dependencies.
    """

    def __init__(self) -> None:
        try:
            import CoolProp.CoolProp as coolprop
        except ImportError as exc:
            raise RuntimeError(
                "CoolProp is not installed. Install optional dependency "
                "with: pip install .[coolprop]"
            ) from exc
        self._cp = coolprop

    def air(self, temperature: float, pressure: float) -> AirProperties:
        cp = self._cp
        fluid = "Air"
        rho = cp.PropsSI("Dmass", "T", temperature, "P", pressure, fluid)
        mu = cp.PropsSI("V", "T", temperature, "P", pressure, fluid)
        k = cp.PropsSI("L", "T", temperature, "P", pressure, fluid)
        cp_mass = cp.PropsSI("Cpmass", "T", temperature, "P", pressure, fluid)
        cv_mass = cp.PropsSI("Cvmass", "T", temperature, "P", pressure, fluid)
        pr = cp.PropsSI("Prandtl", "T", temperature, "P", pressure, fluid)
        gamma = cp_mass / cv_mass
        r_specific = cp_mass - cv_mass
        return AirProperties(
            temperature=temperature,
            pressure=pressure,
            rho=rho,
            mu=mu,
            k=k,
            cp=cp_mass,
            pr=pr,
            gamma=gamma,
            r_specific=r_specific,
        )


def make_property_provider(model: str) -> PropertyProvider:
    if model == "ideal_gas":
        return IdealGasAir()
    if model == "coolprop":
        return CoolPropAir()
    raise ValueError(f"Unsupported property model: {model}")


def speed_of_sound(properties: AirProperties) -> float:
    return sqrt(
        properties.gamma * properties.r_specific * properties.temperature
    )
