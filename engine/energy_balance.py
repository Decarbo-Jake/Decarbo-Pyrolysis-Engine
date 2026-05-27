"""
Module 3 — Energy Balance

Calculates all energy inputs and outputs for the pyrolysis plant.
Reference temperature: 0°C (all enthalpy terms relative to 0°C).

Validated against: LSM Report 2602TN-R0 (Jibito BR-01, May 2026)
Residual difference vs LSM (~0.4%) explained by LHV_ar discrepancy (Q3).
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.constants import (
    CP_BIOMASS_WET,
    CP_MOIST_AIR,
    CP_BIOCHAR,
    JIBITO_REFERENCE,
)


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnergyBalanceInput:
    """
    Inputs for energy balance calculation.
    Combines feedstock, mass balance, and hardware data.
    """
    # Feed
    feed_rate_ar: float = 0.0        # kg/h as-received
    LHV_ar: float = 0.0              # kJ/kg — from feedstock module
    T_feed: float = 35.0             # °C feedstock temperature
    T_ref: float = 0.0               # °C reference temperature

    # Air
    air_flow: float = 0.0            # kg/h total combustion air
    T_air: float = 27.0              # °C ambient air temperature

    # Biochar
    biochar_dry: float = 0.0         # kg/h from mass balance module
    LHV_biochar_dry: float = 16672.0 # kJ/kg — from LSM/Eurofins
    T_pyrolysis: float = 550.0       # °C pyrolysis temperature

    # Support burner (0 if self-sustaining)
    support_burner_kW: float = 0.0

    # Outputs
    flue_gas_loss_kW: float = 0.0    # kW — from HSC model or measurement
    radiation_kW: float = 85.0       # kW — fixed loss (LSM Section 1.7)
    biochar_latent_kW: float = 0.0   # kW — residual moisture in biochar

    scenario_name: str = ""


@dataclass
class EnergyBalanceResult:
    """
    Complete energy balance result.
    All values in kW.
    """
    # --- INPUTS ---
    feed_combustion_kW: float = 0.0   # Chemical energy in feed (LHV basis)
    feed_sensible_kW: float = 0.0     # Sensible heat of feed above T_ref
    air_sensible_kW: float = 0.0      # Sensible heat of combustion air
    support_burner_kW: float = 0.0    # External fuel input
    total_in_kW: float = 0.0

    # --- OUTPUTS ---
    flue_gas_loss_kW: float = 0.0     # Dominant loss — hot PCC exhaust
    radiation_kW: float = 0.0         # Surface radiation losses
    biochar_combustion_kW: float = 0.0 # Chemical energy in biochar (sequestered)
    biochar_sensible_kW: float = 0.0  # Sensible heat of hot biochar
    biochar_latent_kW: float = 0.0    # Latent heat of residual biochar moisture
    total_out_kW: float = 0.0

    # --- BALANCE ---
    balance_kW: float = 0.0           # IN - OUT (should be ~0)
    balance_error_pct: float = 0.0    # % deviation

    # --- FRACTIONS ---
    flue_gas_fraction: float = 0.0    # flue gas loss / total IN
    biochar_energy_fraction: float = 0.0  # biochar chem energy / feed combustion

    warnings: list = field(default_factory=list)
    scenario_name: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def feed_combustion_power(feed_rate_ar: float, LHV_ar: float) -> float:
    """
    Chemical energy input from feedstock combustion (LHV basis).

    Formula:
        P_feed [kW] = Feed_ar [kg/h] / 3600 * LHV_ar [kJ/kg]

    Args:
        feed_rate_ar: Feed rate as-received [kg/h]
        LHV_ar:       Lower Heating Value as-received [kJ/kg]

    Returns:
        Combustion power [kW]

    Example (Jibito Scenario A, using LSM LHV_ar=13,204):
        feed_combustion_power(2000, 13204) -> 7,335 kW
        LSM value: 7,316 kW  (diff: +0.26% from LHV rounding)
    """
    return (feed_rate_ar / 3600.0) * LHV_ar


def sensible_heat(
    mass_flow: float,
    Cp: float,
    T_stream: float,
    T_ref: float = 0.0
) -> float:
    """
    Sensible heat of a stream above reference temperature.

    Formula:
        Q [kW] = (mass_flow [kg/h] / 3600) * Cp [kJ/kg·K] * (T_stream - T_ref) [K]

    Args:
        mass_flow: Mass flow rate [kg/h]
        Cp:        Specific heat capacity [kJ/kg·K]
        T_stream:  Stream temperature [°C]
        T_ref:     Reference temperature [°C]  default: 0°C

    Returns:
        Sensible heat [kW]

    Examples (Jibito Scenario A):
        Feed:  sensible_heat(2000, 1.65, 35, 0) -> 32.1 kW  (LSM: 32 kW)
        Air:   sensible_heat(20117, 1.04, 27, 0) -> 157 kW   (LSM: 157 kW)
        Biochar: sensible_heat(318, 1.256, 550, 0) -> 61 kW  (LSM: 61 kW)
    """
    return (mass_flow / 3600.0) * Cp * (T_stream - T_ref)


def biochar_chemical_energy(biochar_dry: float, LHV_biochar_dry: float) -> float:
    """
    Chemical energy stored in biochar (not combusted — sequestered carbon).

    This energy is RETAINED in the solid product, not released as heat.
    It represents the carbon removal credit of the plant.

    Formula:
        Q_biochar [kW] = Biochar_dry [kg/h] / 3600 * LHV_biochar_dry [kJ/kg]

    Args:
        biochar_dry:      Biochar flow dry basis [kg/h]
        LHV_biochar_dry:  LHV of biochar [kJ/kg]  LSM: 16,672 kJ/kg

    Returns:
        Biochar chemical energy [kW]

    Example (Jibito Scenario A):
        biochar_chemical_energy(318, 16672) -> 1,471 kW  (LSM: 1,471 kW ✓)
    """
    return (biochar_dry / 3600.0) * LHV_biochar_dry


def air_flow_from_sensible_heat(
    sensible_heat_kW: float,
    T_air: float,
    T_ref: float = 0.0,
    Cp_air: float = CP_MOIST_AIR
) -> float:
    """
    Back-calculate total air mass flow from known sensible heat.
    Used when HSC air flow is not available but sensible heat is known.

    Formula:
        m_air = Q_air * 3600 / (Cp * (T_air - T_ref))

    Args:
        sensible_heat_kW: Air sensible heat from energy balance [kW]
        T_air:            Air temperature [°C]
        T_ref:            Reference temperature [°C]
        Cp_air:           Specific heat of moist air [kJ/kg·K]

    Returns:
        Total air mass flow [kg/h]

    Example (Jibito Scenario A):
        air_flow_from_sensible_heat(157, 27) -> ~20,117 kg/h
    """
    if T_air <= T_ref:
        raise ValueError(f"Air temperature ({T_air}°C) must be above T_ref ({T_ref}°C)")
    return sensible_heat_kW * 3600.0 / (Cp_air * (T_air - T_ref))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CALCULATION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def calculate(inputs: EnergyBalanceInput) -> EnergyBalanceResult:
    """
    Run complete energy balance for one scenario.

    Sequence:
      1. Calculate energy inputs (combustion, sensible heat, air, burner)
      2. Calculate energy outputs (flue gas, radiation, biochar)
      3. Sum totals and check closure

    Args:
        inputs: EnergyBalanceInput

    Returns:
        EnergyBalanceResult with all terms in kW
    """
    result = EnergyBalanceResult()
    warnings = []
    result.scenario_name = inputs.scenario_name

    # ── INPUTS ────────────────────────────────────────────────────────────

    # 1a. Feed combustion power
    result.feed_combustion_kW = feed_combustion_power(
        inputs.feed_rate_ar, inputs.LHV_ar
    )

    # 1b. Feed sensible heat
    result.feed_sensible_kW = sensible_heat(
        inputs.feed_rate_ar, CP_BIOMASS_WET,
        inputs.T_feed, inputs.T_ref
    )

    # 1c. Air sensible heat
    result.air_sensible_kW = sensible_heat(
        inputs.air_flow, CP_MOIST_AIR,
        inputs.T_air, inputs.T_ref
    )

    # 1d. Support burner
    result.support_burner_kW = inputs.support_burner_kW

    result.total_in_kW = (
        result.feed_combustion_kW +
        result.feed_sensible_kW +
        result.air_sensible_kW +
        result.support_burner_kW
    )

    # ── OUTPUTS ───────────────────────────────────────────────────────────

    # 2a. Flue gas loss (from HSC model or measurement)
    result.flue_gas_loss_kW = inputs.flue_gas_loss_kW

    # 2b. Radiation losses
    result.radiation_kW = inputs.radiation_kW

    # 2c. Biochar chemical energy (sequestered — largest output after flue gas)
    result.biochar_combustion_kW = biochar_chemical_energy(
        inputs.biochar_dry, inputs.LHV_biochar_dry
    )

    # 2d. Biochar sensible heat
    result.biochar_sensible_kW = sensible_heat(
        inputs.biochar_dry, CP_BIOCHAR,
        inputs.T_pyrolysis, inputs.T_ref
    )

    # 2e. Biochar latent heat (residual moisture)
    result.biochar_latent_kW = inputs.biochar_latent_kW

    result.total_out_kW = (
        result.flue_gas_loss_kW +
        result.radiation_kW +
        result.biochar_combustion_kW +
        result.biochar_sensible_kW +
        result.biochar_latent_kW
    )

    # ── BALANCE ───────────────────────────────────────────────────────────

    result.balance_kW = result.total_in_kW - result.total_out_kW

    if result.total_in_kW > 0:
        result.balance_error_pct = (
            result.balance_kW / result.total_in_kW * 100.0
        )

    # ── FRACTIONS ─────────────────────────────────────────────────────────

    if result.total_in_kW > 0:
        result.flue_gas_fraction = (
            result.flue_gas_loss_kW / result.total_in_kW
        )
        result.biochar_energy_fraction = (
            result.biochar_combustion_kW / result.feed_combustion_kW
            if result.feed_combustion_kW > 0 else 0.0
        )

    # ── FLAGS ─────────────────────────────────────────────────────────────

    if abs(result.balance_error_pct) > 5.0:
        warnings.append(
            f"Energy balance error {result.balance_error_pct:+.1f}% "
            f"exceeds 5% threshold. Check flue gas loss input."
        )

    if result.flue_gas_fraction > 0.85:
        warnings.append(
            f"Flue gas loss fraction = {result.flue_gas_fraction:.1%} "
            f"— unusually high. Consider waste heat recovery."
        )

    if result.support_burner_kW > 0:
        warnings.append(
            f"Support burner required: {result.support_burner_kW:.0f} kW. "
            f"Plant is not thermally self-sustaining at this feed rate."
        )

    result.warnings = warnings
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SCENARIO RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def calculate_scenarios(
    feed_rates: list,
    LHV_ar: float,
    biochar_flows: list,
    air_flows: list,
    flue_gas_losses: list,
    biochar_latent: list = None,
    T_feed: float = 35.0,
    T_air: float = 27.0,
    T_ref: float = 0.0,
    T_pyrolysis: float = 550.0,
    LHV_biochar_dry: float = 16672.0,
    radiation_kW: float = 85.0,
    scenario_names: list = None,
) -> list:
    """
    Run energy balance for multiple scenarios.

    Args:
        feed_rates:       List of feed rates [kg/h ar]
        LHV_ar:           LHV as-received [kJ/kg] — same for all scenarios
        biochar_flows:    List of biochar dry flows [kg/h]
        air_flows:        List of total air flows [kg/h]
        flue_gas_losses:  List of flue gas losses [kW] from HSC or measurement
        biochar_latent:   List of biochar latent heat [kW]  default: [4,5,6]
        scenario_names:   Optional list of labels

    Returns:
        List of EnergyBalanceResult
    """
    n = len(feed_rates)
    if biochar_latent is None:
        biochar_latent = [4.0, 5.0, 6.0][:n]
        if len(biochar_latent) < n:
            biochar_latent += [5.0] * (n - len(biochar_latent))
    if scenario_names is None:
        scenario_names = [f"{int(fr)} kg/h" for fr in feed_rates]

    results = []
    for i in range(n):
        inp = EnergyBalanceInput(
            feed_rate_ar      = feed_rates[i],
            LHV_ar            = LHV_ar,
            T_feed            = T_feed,
            T_ref             = T_ref,
            air_flow          = air_flows[i],
            T_air             = T_air,
            biochar_dry       = biochar_flows[i],
            LHV_biochar_dry   = LHV_biochar_dry,
            T_pyrolysis       = T_pyrolysis,
            flue_gas_loss_kW  = flue_gas_losses[i],
            radiation_kW      = radiation_kW,
            biochar_latent_kW = biochar_latent[i],
            scenario_name     = scenario_names[i],
        )
        results.append(calculate(inp))

    return results


def print_summary(results: list) -> None:
    """Print formatted energy balance comparison table."""
    print(f"\n{'─'*75}")
    print("ENERGY BALANCE SUMMARY  [kW]")
    print(f"{'─'*75}")
    header = f"{'Term':<30}" + "".join(f"{r.scenario_name:>15}" for r in results)
    print(header)
    print(f"{'─'*75}")

    rows = [
        ("— INPUTS —",              None),
        ("Feed combustion (LHV)",   lambda r: r.feed_combustion_kW),
        ("Feed sensible",           lambda r: r.feed_sensible_kW),
        ("Air sensible",            lambda r: r.air_sensible_kW),
        ("Support burner",          lambda r: r.support_burner_kW),
        ("TOTAL IN",                lambda r: r.total_in_kW),
        ("— OUTPUTS —",             None),
        ("Flue gas loss",           lambda r: r.flue_gas_loss_kW),
        ("Radiation",               lambda r: r.radiation_kW),
        ("Biochar combustion",      lambda r: r.biochar_combustion_kW),
        ("Biochar sensible",        lambda r: r.biochar_sensible_kW),
        ("Biochar latent",          lambda r: r.biochar_latent_kW),
        ("TOTAL OUT",               lambda r: r.total_out_kW),
        ("Balance (IN-OUT)",        lambda r: r.balance_kW),
        ("Balance error [%]",       lambda r: r.balance_error_pct),
        ("Flue gas fraction",       lambda r: r.flue_gas_fraction),
    ]

    for label, fn in rows:
        if fn is None:
            print(f"\n{label}")
        else:
            row = f"{label:<30}" + "".join(f"{fn(r):>15.1f}" for r in results)
            print(row)

    print(f"{'─'*75}\n")