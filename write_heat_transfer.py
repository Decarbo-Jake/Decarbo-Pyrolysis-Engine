content = '''\
import math
from dataclasses import dataclass, field
from engine.constants import (
    STEEL_GRADES, HTC, PYROLYSIS_ENTHALPY,
    STEFAN_BOLTZMANN, EMISSIVITY_BARE_STEEL,
    LATENT_HEAT_WATER_100C, CP_BIOMASS_WET, T_REF_K,
)


@dataclass
class ReactorGeometry:
    diameter_outer: float = 2.4
    length_heated: float = 6.0
    wall_thickness: float = 0.012
    steel_grade: str = "SS304"
    diameter_inner: float = 1.4
    reactor_type: str = "rotary_kiln_double_pass"

    @property
    def heat_transfer_area(self):
        return math.pi * self.diameter_outer * self.length_heated

    @property
    def thermal_conductivity(self):
        if self.steel_grade not in STEEL_GRADES:
            raise ValueError(
                f"Steel grade {self.steel_grade!r} not found. "
                f"Available: {list(STEEL_GRADES.keys())}"
            )
        return STEEL_GRADES[self.steel_grade]["thermal_conductivity"]

    @property
    def max_service_temp(self):
        return STEEL_GRADES[self.steel_grade]["max_service_temp"]


@dataclass
class HeatTransferInput:
    T_combustion_gas: float = 779.0
    T_pyrolysis: float = 600.0
    T_feed: float = 35.0
    T_ref: float = 0.0
    feed_rate_ar: float = 1000.0
    moisture_ar: float = 10.13
    ash_dry: float = 6.843
    feedstock_type: str = "sugar_cane"
    h_combustion_conv: float = 50.0
    h_pyrolysis: float = 35.0
    emissivity: float = EMISSIVITY_BARE_STEEL
    geometry: object = None
    scenario_name: str = ""

    def __post_init__(self):
        if self.geometry is None:
            self.geometry = ReactorGeometry()


@dataclass
class HeatTransferResult:
    heat_transfer_area_m2: float = 0.0
    wall_thickness_m: float = 0.0
    steel_grade: str = ""
    thermal_conductivity: float = 0.0
    h_radiation: float = 0.0
    h_combustion_total: float = 0.0
    h_pyrolysis: float = 0.0
    R_wall: float = 0.0
    U_overall: float = 0.0
    T_combustion_gas: float = 0.0
    T_pyrolysis: float = 0.0
    delta_T: float = 0.0
    T_wall_outer: float = 0.0
    T_wall_inner: float = 0.0
    Q_delivered_kW: float = 0.0
    Q_sensible_kW: float = 0.0
    Q_moisture_kW: float = 0.0
    Q_reaction_kW: float = 0.0
    Q_required_kW: float = 0.0
    Q_surplus_kW: float = 0.0
    thermal_margin_pct: float = 0.0
    can_sustain_pyrolysis: bool = False
    max_feed_rate_ar: float = 0.0
    steel_temp_warning: bool = False
    warnings: list = field(default_factory=list)
    scenario_name: str = ""


def radiative_htc(T_hot, T_cold, emissivity=EMISSIVITY_BARE_STEEL):
    T_hot_K  = T_hot  + T_REF_K
    T_cold_K = T_cold + T_REF_K
    if abs(T_hot_K - T_cold_K) < 1.0:
        return 0.0
    q_rad = STEFAN_BOLTZMANN * emissivity * (T_hot_K**4 - T_cold_K**4)
    return q_rad / (T_hot_K - T_cold_K)


def overall_htc(h_combustion_conv, h_radiation, wall_thickness,
                thermal_conductivity, h_pyrolysis):
    h_comb_total = h_combustion_conv + h_radiation
    R_combustion = 1.0 / h_comb_total if h_comb_total > 0 else float("inf")
    R_wall       = wall_thickness / thermal_conductivity
    R_pyrolysis  = 1.0 / h_pyrolysis if h_pyrolysis > 0 else float("inf")
    R_total = R_combustion + R_wall + R_pyrolysis
    U = 1.0 / R_total
    return U, R_wall, h_comb_total


def estimate_wall_temperatures(T_combustion, T_pyrolysis,
                                h_combustion_total, h_pyrolysis, U_overall):
    q = U_overall * (T_combustion - T_pyrolysis)
    T_wall_outer = T_combustion - q / h_combustion_total
    T_wall_inner = T_pyrolysis  + q / h_pyrolysis
    return T_wall_outer, T_wall_inner


def heat_required(feed_rate_ar, moisture_ar, T_pyrolysis, T_feed,
                  feedstock_type="sugar_cane", T_ref=0.0):
    feed_dry   = feed_rate_ar * (1.0 - moisture_ar / 100.0)
    moisture   = feed_rate_ar * moisture_ar / 100.0
    Q_sensible = (feed_dry / 3600.0) * CP_BIOMASS_WET * (T_pyrolysis - T_feed)
    Q_moisture = (moisture / 3600.0) * (
        4.18 * (100.0 - T_feed) + LATENT_HEAT_WATER_100C
    )
    dH = PYROLYSIS_ENTHALPY.get(feedstock_type, PYROLYSIS_ENTHALPY["default"])
    Q_reaction = (feed_dry / 3600.0) * dH
    Q_total    = Q_sensible + Q_moisture + Q_reaction
    return Q_sensible, Q_moisture, Q_reaction, Q_total


def max_feed_rate(Q_delivered_kW, moisture_ar, T_pyrolysis, T_feed,
                  feedstock_type="sugar_cane"):
    ref_rate = 1000.0
    _, _, _, Q_ref = heat_required(
        ref_rate, moisture_ar, T_pyrolysis, T_feed, feedstock_type
    )
    if Q_ref <= 0:
        return 0.0
    return ref_rate * (Q_delivered_kW / Q_ref)


def calculate(inputs):
    result   = HeatTransferResult()
    warnings = []
    result.scenario_name         = inputs.scenario_name
    geo                          = inputs.geometry
    result.heat_transfer_area_m2 = geo.heat_transfer_area
    result.wall_thickness_m      = geo.wall_thickness
    result.steel_grade           = geo.steel_grade
    result.thermal_conductivity  = geo.thermal_conductivity
    result.T_combustion_gas      = inputs.T_combustion_gas
    result.T_pyrolysis           = inputs.T_pyrolysis
    result.delta_T               = inputs.T_combustion_gas - inputs.T_pyrolysis

    T_wall_est         = inputs.T_pyrolysis + 0.7 * result.delta_T
    result.h_radiation = radiative_htc(
        inputs.T_combustion_gas, T_wall_est, inputs.emissivity
    )
    result.h_pyrolysis = inputs.h_pyrolysis

    result.U_overall, result.R_wall, result.h_combustion_total = overall_htc(
        inputs.h_combustion_conv, result.h_radiation,
        geo.wall_thickness, geo.thermal_conductivity, inputs.h_pyrolysis
    )
    result.T_wall_outer, result.T_wall_inner = estimate_wall_temperatures(
        inputs.T_combustion_gas, inputs.T_pyrolysis,
        result.h_combustion_total, inputs.h_pyrolysis, result.U_overall
    )

    result.h_radiation = radiative_htc(
        inputs.T_combustion_gas, result.T_wall_outer, inputs.emissivity
    )
    result.U_overall, result.R_wall, result.h_combustion_total = overall_htc(
        inputs.h_combustion_conv, result.h_radiation,
        geo.wall_thickness, geo.thermal_conductivity, inputs.h_pyrolysis
    )

    result.Q_delivered_kW = (
        result.U_overall * result.heat_transfer_area_m2 * result.delta_T / 1000.0
    )

    (result.Q_sensible_kW,
     result.Q_moisture_kW,
     result.Q_reaction_kW,
     result.Q_required_kW) = heat_required(
        inputs.feed_rate_ar, inputs.moisture_ar,
        inputs.T_pyrolysis, inputs.T_feed, inputs.feedstock_type
    )

    result.Q_surplus_kW          = result.Q_delivered_kW - result.Q_required_kW
    result.can_sustain_pyrolysis  = result.Q_surplus_kW >= 0

    if result.Q_required_kW > 0:
        result.thermal_margin_pct = (
            result.Q_surplus_kW / result.Q_required_kW * 100.0
        )

    result.max_feed_rate_ar = max_feed_rate(
        result.Q_delivered_kW, inputs.moisture_ar,
        inputs.T_pyrolysis, inputs.T_feed, inputs.feedstock_type
    )

    if inputs.T_combustion_gas > geo.max_service_temp:
        result.steel_temp_warning = True
        warnings.append(
            f"TEMP WARNING: {inputs.T_combustion_gas}C exceeds "
            f"{geo.steel_grade} limit {geo.max_service_temp}C"
        )
    if not result.can_sustain_pyrolysis:
        warnings.append(
            f"THERMAL LIMIT: {inputs.feed_rate_ar:.0f} kg/h needs "
            f"{result.Q_required_kW:.0f} kW, reactor delivers "
            f"{result.Q_delivered_kW:.0f} kW. "
            f"Max: {result.max_feed_rate_ar:.0f} kg/h"
        )
    if result.thermal_margin_pct < 10.0 and result.can_sustain_pyrolysis:
        warnings.append(
            f"LOW MARGIN: {result.thermal_margin_pct:.1f}% headroom"
        )

    result.warnings = warnings
    return result


def feed_rate_sweep(geometry, T_combustion_gas, T_pyrolysis, moisture_ar,
                    feed_rates, T_feed=35.0, h_combustion_conv=50.0,
                    h_pyrolysis=35.0, feedstock_type="sugar_cane"):
    results = []
    for fr in feed_rates:
        inp = HeatTransferInput(
            T_combustion_gas  = T_combustion_gas,
            T_pyrolysis       = T_pyrolysis,
            T_feed            = T_feed,
            feed_rate_ar      = fr,
            moisture_ar       = moisture_ar,
            h_combustion_conv = h_combustion_conv,
            h_pyrolysis       = h_pyrolysis,
            feedstock_type    = feedstock_type,
            geometry          = geometry,
            scenario_name     = f"{int(fr)} kg/h",
        )
        results.append(calculate(inp))
    return results
'''

with open("engine/heat_transfer.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Written successfully -", len(content.splitlines()), "lines")