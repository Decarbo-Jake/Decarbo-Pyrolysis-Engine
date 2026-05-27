import math
from dataclasses import dataclass, field
from typing import Optional
from engine.constants import EU_WID, RHO_AIR_0C, T_REF_K


# -----------------------------------------------------------------------------
# SYNGAS STOICHIOMETRY
# NCG approximate composition for biomass pyrolysis (weight basis):
#   CO  ~45%wt, CO2 ~30%wt, CH4 ~15%wt, H2 ~10%wt
# Stoichiometric O2 demand [kg O2 per kg fuel]:
#   CO  + 0.5 O2 -> CO2  : 0.571 kg O2/kg CO
#   CH4 + 2 O2   -> CO2+2H2O : 4.000 kg O2/kg CH4
#   H2  + 0.5 O2 -> H2O  : 8.000 kg O2/kg H2
# Weighted average NCG: ~1.2 kg O2/kg NCG  -> ~5.17 kg air/kg NCG
# Tars (guaiacol C7H8O2, MW=124):
#   C7H8O2 + 7.5 O2 -> 7CO2 + 4H2O : 1.935 kg O2/kg tar -> ~8.34 kg air/kg tar
# H2O in syngas: no combustion air needed
# -----------------------------------------------------------------------------
STOIC_AIR_NCG  = 5.17   # kg air per kg NCG  (theoretical)
STOIC_AIR_TARS = 8.34   # kg air per kg tars (theoretical, guaiacol surrogate)
STOIC_AIR_H2O  = 0.0    # moisture needs no combustion air


@dataclass
class ChamberGeometry:
    """
    Combustion chamber physical dimensions.
    All inputs in METRES. Refractory reduces the internal volume.
    is_cylindrical: True for RBu (cylindrical), False for PCC (rectangular)
    """
    # External dimensions
    length_ext: float = 0.0
    width_ext: float = 0.0
    height_ext: float = 0.0
    diameter_ext: float = 0.0

    # Refractory
    refractory_thickness: float = 0.10   # m, default 100mm

    # Geometry type
    is_cylindrical: bool = False
    name: str = "Chamber"

    @property
    def internal_diameter(self):
        return self.diameter_ext - 2 * self.refractory_thickness

    @property
    def internal_length(self):
        return self.length_ext - 2 * self.refractory_thickness

    @property
    def internal_width(self):
        return self.width_ext - 2 * self.refractory_thickness

    @property
    def internal_height(self):
        return self.height_ext - 2 * self.refractory_thickness

    @property
    def internal_volume(self):
        if self.is_cylindrical:
            r = self.internal_diameter / 2.0
            if r <= 0 or self.internal_length <= 0:
                raise ValueError(
                    f"{self.name}: Internal diameter or length <= 0. "
                    f"Check external dimensions and refractory thickness."
                )
            return math.pi * r**2 * self.internal_length
        else:
            w = self.internal_width
            h = self.internal_height
            l = self.internal_length
            if w <= 0 or h <= 0 or l <= 0:
                raise ValueError(
                    f"{self.name}: One or more internal dimensions <= 0. "
                    f"Check external dimensions and refractory thickness."
                )
            return w * h * l

    @property
    def external_volume(self):
        if self.is_cylindrical:
            r = self.diameter_ext / 2.0
            return math.pi * r**2 * self.length_ext
        else:
            return self.length_ext * self.width_ext * self.height_ext


def rbu_default():
    """
    Default RBu geometry from engineering drawing.
    Cylindrical: external diameter=1500mm, length=3000mm, refractory=100mm.
    Internal: diameter=1300mm, length=2800mm, volume=3.72 m3.
    """
    return ChamberGeometry(
        diameter_ext         = 1.500,
        length_ext           = 3.000,
        refractory_thickness = 0.100,
        is_cylindrical       = True,
        name                 = "RBu",
    )


def pcc_default():
    """
    Default PCC geometry from engineering drawing.
    Rectangular: internal 2000x4000x4000mm (dimensions given as internal).
    External = internal + 2 x refractory on each side.
    Note: PCC dimensions entered as INTERNAL -- set refractory=0 and use
    internal dimensions directly as external for calculation.
    Internal volume = 2.0 x 4.0 x 4.0 = 32.0 m3.
    """
    return ChamberGeometry(
        length_ext           = 4.200,   # 4000mm internal + 100mm each end
        width_ext            = 2.200,   # 2000mm internal + 100mm each side
        height_ext           = 4.200,   # 4000mm internal + 100mm each side
        refractory_thickness = 0.100,
        is_cylindrical       = False,
        name                 = "PCC",
    )


# -----------------------------------------------------------------------------
# INPUT DATACLASSES
# -----------------------------------------------------------------------------

@dataclass
class SyngasComposition:
    """
    Syngas composition weight fractions (must sum to ~1.0).
    Defaults from LSM Report 2602TN-R0 (Jibito BR-01).
    """
    NCG_wt:  float = 0.543   # Non-condensable gas fraction
    tars_wt: float = 0.190   # Tars / condensable fraction
    H2O_wt:  float = 0.268   # Moisture fraction

    def validate(self):
        total = self.NCG_wt + self.tars_wt + self.H2O_wt
        if not (0.98 <= total <= 1.02):
            raise ValueError(
                f"Syngas fractions sum to {total:.3f} -- expected ~1.0. "
                f"Check NCG + tars + H2O fractions."
            )


@dataclass
class CombustionConfig:
    """
    Complete combustion system configuration.
    Set dual_chamber=False for single chamber operation.
    Set dual_chamber=True for RBu + PCC configuration.
    """
    # Chamber configuration
    dual_chamber: bool = True

    # Single chamber (used when dual_chamber=False)
    single_chamber: ChamberGeometry = None

    # Dual chamber
    rbu: ChamberGeometry = None
    pcc: ChamberGeometry = None

    # Operating temperatures
    T_rbu: float = 950.0    # degrees C -- RBu operating temperature
    T_pcc: float = 900.0    # degrees C -- PCC operating temperature

    # Excess air factors (actual air = stoichiometric x excess_air)
    excess_air_rbu: float = 1.30   # 30% excess air in RBu
    excess_air_pcc: float = 1.20   # 20% excess air in PCC

    # EU WID requirements (defaults from constants)
    tau_min_s: float = EU_WID["pcc_min_residence_time_s"]   # 2.0 s
    T_min_C:   float = EU_WID["pcc_min_temperature_C"]      # 850 degrees C

    # RBu EU WID applicability
    # Set True if RBu must also meet EU WID (conservative/safe)
    # Set False if RBu is permitted as process heater only
    rbu_requires_eu_wid: bool = False

    # Split sweep settings (dual chamber only)
    split_min:  float = 0.10   # minimum fraction of syngas to RBu
    split_max:  float = 0.90   # maximum fraction of syngas to RBu
    split_step: float = 0.05   # step size for sweep

    def __post_init__(self):
        if self.dual_chamber:
            if self.rbu is None:
                self.rbu = rbu_default()
            if self.pcc is None:
                self.pcc = pcc_default()
        else:
            if self.single_chamber is None:
                self.single_chamber = pcc_default()


# -----------------------------------------------------------------------------
# CORE CALCULATION FUNCTIONS
# -----------------------------------------------------------------------------

def gas_density(T_celsius):
    """Gas density at temperature T [kg/m3]. Ideal gas law from 0C reference."""
    return RHO_AIR_0C * (T_REF_K / (T_celsius + T_REF_K))


def volumetric_flow_m3s(mass_flow_kg_h, T_celsius):
    """Convert mass flow [kg/h] to volumetric flow [m3/s] at temperature T."""
    rho = gas_density(T_celsius)
    return (mass_flow_kg_h / 3600.0) / rho


def residence_time_s(chamber_volume_m3, vol_flow_m3s):
    """Residence time [s] = volume / volumetric flow rate."""
    if vol_flow_m3s <= 0:
        return float("inf")
    return chamber_volume_m3 / vol_flow_m3s


def combustion_air_demand(syngas_kg_h, composition, excess_air_factor):
    """
    Calculate combustion air demand for a given syngas flow.

    Stoichiometric air based on NCG and tars content.
    H2O in syngas requires no combustion air.

    Args:
        syngas_kg_h:      Total syngas mass flow [kg/h]
        composition:      SyngasComposition with NCG/tars/H2O fractions
        excess_air_factor: Actual/theoretical air ratio (e.g. 1.3 = 30% excess)

    Returns:
        dict with:
          theoretical_air_kg_h:  Stoichiometric air demand [kg/h]
          actual_air_kg_h:       Actual air with excess [kg/h]
          ncg_air_kg_h:          Air for NCG combustion [kg/h]
          tars_air_kg_h:         Air for tars combustion [kg/h]
          flue_gas_kg_h:         Total flue gas (syngas + actual air) [kg/h]
          excess_air_factor:     Echo back the input
    """
    ncg_flow  = syngas_kg_h * composition.NCG_wt
    tars_flow = syngas_kg_h * composition.tars_wt
    h2o_flow  = syngas_kg_h * composition.H2O_wt

    ncg_air_theoretical  = ncg_flow  * STOIC_AIR_NCG
    tars_air_theoretical = tars_flow * STOIC_AIR_TARS
    total_theoretical    = ncg_air_theoretical + tars_air_theoretical

    actual_air = total_theoretical * excess_air_factor
    flue_gas   = syngas_kg_h + actual_air

    return {
        "theoretical_air_kg_h": total_theoretical,
        "actual_air_kg_h":      actual_air,
        "ncg_air_kg_h":         ncg_air_theoretical * excess_air_factor,
        "tars_air_kg_h":        tars_air_theoretical * excess_air_factor,
        "flue_gas_kg_h":        flue_gas,
        "excess_air_factor":    excess_air_factor,
    }


def min_volume_for_compliance(vol_flow_m3s, tau_min=None):
    """Minimum chamber volume required to achieve tau_min residence time [m3]."""
    if tau_min is None:
        tau_min = EU_WID["pcc_min_residence_time_s"]
    return vol_flow_m3s * tau_min


# -----------------------------------------------------------------------------
# SINGLE CHAMBER RESULT
# -----------------------------------------------------------------------------

@dataclass
class SingleChamberResult:
    """Result for one combustion chamber at one operating point."""
    chamber_name: str = ""
    syngas_flow_kg_h: float = 0.0
    air_demand: dict = field(default_factory=dict)

    # Flows
    total_gas_flow_kg_h: float = 0.0
    volumetric_flow_m3s: float = 0.0
    gas_density_kg_m3: float = 0.0

    # Chamber
    internal_volume_m3: float = 0.0
    T_operating: float = 0.0

    # Residence time
    residence_time_s: float = 0.0
    tau_min_s: float = 2.0
    tau_margin_s: float = 0.0
    eu_wid_compliant: bool = False

    # Volume check
    min_volume_required_m3: float = 0.0
    volume_adequacy_pct: float = 0.0

    warnings: list = field(default_factory=list)


def calculate_chamber(
    syngas_kg_h: float,
    chamber: ChamberGeometry,
    composition: SyngasComposition,
    T_operating: float,
    excess_air: float,
    requires_eu_wid: bool = True,
    tau_min: float = None,
    T_min: float = None,
) -> SingleChamberResult:
    """
    Calculate combustion performance for one chamber.

    Args:
        syngas_kg_h:      Syngas entering this chamber [kg/h]
        chamber:          ChamberGeometry for this chamber
        composition:      SyngasComposition
        T_operating:      Chamber operating temperature [degrees C]
        excess_air:       Excess air factor
        requires_eu_wid:  Whether EU WID residence time applies
        tau_min:          Minimum residence time [s] (default: EU WID 2.0s)
        T_min:            Minimum temperature [degrees C] (default: EU WID 850C)

    Returns:
        SingleChamberResult
    """
    if tau_min is None:
        tau_min = EU_WID["pcc_min_residence_time_s"]
    if T_min is None:
        T_min = EU_WID["pcc_min_temperature_C"]

    result   = SingleChamberResult()
    warnings = []
    result.chamber_name  = chamber.name
    result.syngas_flow_kg_h = syngas_kg_h
    result.T_operating   = T_operating
    result.tau_min_s     = tau_min

    # Air demand
    result.air_demand = combustion_air_demand(syngas_kg_h, composition, excess_air)

    # Total gas flow and volumetric flow
    result.total_gas_flow_kg_h = result.air_demand["flue_gas_kg_h"]
    result.gas_density_kg_m3   = gas_density(T_operating)
    result.volumetric_flow_m3s = volumetric_flow_m3s(
        result.total_gas_flow_kg_h, T_operating
    )

    # Chamber volume
    result.internal_volume_m3 = chamber.internal_volume

    # Residence time
    result.residence_time_s = residence_time_s(
        result.internal_volume_m3, result.volumetric_flow_m3s
    )
    result.tau_margin_s = result.residence_time_s - tau_min

    # Minimum volume required
    result.min_volume_required_m3 = min_volume_for_compliance(
        result.volumetric_flow_m3s, tau_min
    )
    if result.min_volume_required_m3 > 0:
        result.volume_adequacy_pct = (
            result.internal_volume_m3 / result.min_volume_required_m3 * 100.0
        )

    # EU WID compliance
    if requires_eu_wid:
        result.eu_wid_compliant = (
            result.residence_time_s >= tau_min and
            T_operating >= T_min
        )
        if not result.eu_wid_compliant:
            if result.residence_time_s < tau_min:
                warnings.append(
                    f"EU WID NON-COMPLIANT [{chamber.name}]: "
                    f"tau={result.residence_time_s:.2f}s < {tau_min}s minimum. "
                    f"Min volume required: {result.min_volume_required_m3:.1f} m3, "
                    f"actual: {result.internal_volume_m3:.1f} m3. "
                    f"Chamber undersized by "
                    f"{result.min_volume_required_m3 - result.internal_volume_m3:.1f} m3."
                )
            if T_operating < T_min:
                warnings.append(
                    f"TEMPERATURE NON-COMPLIANT [{chamber.name}]: "
                    f"{T_operating}C < EU WID minimum {T_min}C."
                )
        elif result.tau_margin_s < 0.3:
            warnings.append(
                f"LOW MARGIN [{chamber.name}]: "
                f"tau={result.residence_time_s:.2f}s -- only {result.tau_margin_s:.2f}s "
                f"above EU WID minimum. Small increase in feed rate will cause "
                f"non-compliance."
            )
    else:
        result.eu_wid_compliant = True   # EU WID not required for this chamber

    result.warnings = warnings
    return result


# -----------------------------------------------------------------------------
# DUAL CHAMBER RESULT
# -----------------------------------------------------------------------------

@dataclass
class SplitResult:
    """Result for one specific syngas split in dual-chamber configuration."""
    split_fraction_rbu: float = 0.0    # fraction of syngas to RBu
    split_fraction_pcc: float = 0.0    # fraction to PCC (= 1 - RBu fraction)

    rbu: SingleChamberResult = None
    pcc: SingleChamberResult = None

    both_compliant: bool = False       # True if both EU WID requirements met
    feasible: bool = False             # True if split is physically valid


@dataclass
class DualChamberResult:
    """
    Complete dual-chamber analysis at one feed rate.
    Contains sweep across all split fractions.
    """
    total_syngas_kg_h: float = 0.0
    feed_rate_ar_kg_h: float = 0.0

    # Split sweep results
    split_results: list = field(default_factory=list)

    # Valid operating range
    valid_splits: list = field(default_factory=list)   # list of valid fractions
    split_min_valid: float = 0.0
    split_max_valid: float = 0.0
    split_recommended: float = 0.0
    has_valid_range: bool = False

    # At recommended split
    rbu_at_recommended: SingleChamberResult = None
    pcc_at_recommended: SingleChamberResult = None

    # Total air demand at recommended split
    total_air_kg_h: float = 0.0
    rbu_air_kg_h: float = 0.0
    pcc_air_kg_h: float = 0.0

    warnings: list = field(default_factory=list)
    scenario_name: str = ""


def calculate_dual(
    total_syngas_kg_h: float,
    config: CombustionConfig,
    composition: SyngasComposition,
    feed_rate_ar_kg_h: float = 0.0,
    scenario_name: str = "",
) -> DualChamberResult:
    """
    Calculate dual-chamber combustion system at one feed rate.
    Sweeps through all split fractions and identifies valid operating range.

    Args:
        total_syngas_kg_h: Total syngas from mass balance [kg/h]
        config:            CombustionConfig with RBu and PCC geometry
        composition:       SyngasComposition
        feed_rate_ar_kg_h: Feed rate for reporting [kg/h]
        scenario_name:     Label for output

    Returns:
        DualChamberResult with full split sweep and valid range
    """
    result = DualChamberResult()
    warnings = []
    result.total_syngas_kg_h  = total_syngas_kg_h
    result.feed_rate_ar_kg_h  = feed_rate_ar_kg_h
    result.scenario_name      = scenario_name

    # Generate split fractions to sweep
    splits = []
    s = config.split_min
    while s <= config.split_max + 1e-9:
        splits.append(round(s, 4))
        s += config.split_step
    if config.split_max not in splits:
        splits.append(config.split_max)

    # Sweep all splits
    valid_splits = []
    split_results = []

    for split in splits:
        syngas_rbu = total_syngas_kg_h * split
        syngas_pcc = total_syngas_kg_h * (1.0 - split)

        rbu_result = calculate_chamber(
            syngas_kg_h      = syngas_rbu,
            chamber          = config.rbu,
            composition      = composition,
            T_operating      = config.T_rbu,
            excess_air       = config.excess_air_rbu,
            requires_eu_wid  = config.rbu_requires_eu_wid,
            tau_min          = config.tau_min_s,
            T_min            = config.T_min_C,
        )

        pcc_result = calculate_chamber(
            syngas_kg_h      = syngas_pcc,
            chamber          = config.pcc,
            composition      = composition,
            T_operating      = config.T_pcc,
            excess_air       = config.excess_air_pcc,
            requires_eu_wid  = True,   # PCC always must meet EU WID
            tau_min          = config.tau_min_s,
            T_min            = config.T_min_C,
        )

        # A split is feasible if PCC is EU WID compliant
        # (RBu compliance depends on rbu_requires_eu_wid setting)
        pcc_ok = pcc_result.eu_wid_compliant
        rbu_ok = rbu_result.eu_wid_compliant if config.rbu_requires_eu_wid else True

        feasible = pcc_ok and rbu_ok

        sr = SplitResult(
            split_fraction_rbu = split,
            split_fraction_pcc = 1.0 - split,
            rbu                = rbu_result,
            pcc                = pcc_result,
            both_compliant     = feasible,
            feasible           = feasible,
        )
        split_results.append(sr)

        if feasible:
            valid_splits.append(split)

    result.split_results = split_results
    result.valid_splits  = valid_splits
    result.has_valid_range = len(valid_splits) > 0

    if result.has_valid_range:
        result.split_min_valid   = min(valid_splits)
        result.split_max_valid   = max(valid_splits)
        # Recommended split: midpoint of valid range
        result.split_recommended = round(
            (result.split_min_valid + result.split_max_valid) / 2.0, 2
        )

        # Calculate at recommended split
        syngas_rbu_rec = total_syngas_kg_h * result.split_recommended
        syngas_pcc_rec = total_syngas_kg_h * (1.0 - result.split_recommended)

        result.rbu_at_recommended = calculate_chamber(
            syngas_kg_h     = syngas_rbu_rec,
            chamber         = config.rbu,
            composition     = composition,
            T_operating     = config.T_rbu,
            excess_air      = config.excess_air_rbu,
            requires_eu_wid = config.rbu_requires_eu_wid,
        )
        result.pcc_at_recommended = calculate_chamber(
            syngas_kg_h     = syngas_pcc_rec,
            chamber         = config.pcc,
            composition     = composition,
            T_operating     = config.T_pcc,
            excess_air      = config.excess_air_pcc,
            requires_eu_wid = True,
        )

        result.rbu_air_kg_h   = result.rbu_at_recommended.air_demand["actual_air_kg_h"]
        result.pcc_air_kg_h   = result.pcc_at_recommended.air_demand["actual_air_kg_h"]
        result.total_air_kg_h = result.rbu_air_kg_h + result.pcc_air_kg_h

    else:
        warnings.append(
            f"NO VALID SPLIT EXISTS at {feed_rate_ar_kg_h:.0f} kg/h. "
            f"PCC cannot maintain EU WID compliance for any syngas split. "
            f"Feed rate exceeds system capacity."
        )

    result.warnings = warnings
    return result


# -----------------------------------------------------------------------------
# OPERATING ENVELOPE
# -----------------------------------------------------------------------------

@dataclass
class EnvelopePoint:
    """One row in the operating envelope table."""
    feed_rate_ar: float = 0.0
    syngas_kg_h: float = 0.0
    has_valid_range: bool = False
    split_min_valid: float = 0.0
    split_max_valid: float = 0.0
    split_recommended: float = 0.0
    rbu_tau_at_rec: float = 0.0
    pcc_tau_at_rec: float = 0.0
    rbu_air_kg_h: float = 0.0
    pcc_air_kg_h: float = 0.0
    total_air_kg_h: float = 0.0
    pcc_compliant: bool = False
    status: str = ""


def calculate_envelope(
    feed_rates: list,
    syngas_flows: list,
    config: CombustionConfig,
    composition: SyngasComposition = None,
) -> list:
    """
    Calculate operating envelope across a range of feed rates.

    Args:
        feed_rates:   List of feed rates [kg/h ar]
        syngas_flows: Corresponding syngas flows [kg/h] from mass balance
        config:       CombustionConfig
        composition:  SyngasComposition (default: Jibito values)

    Returns:
        List of EnvelopePoint -- one per feed rate
    """
    if composition is None:
        composition = SyngasComposition()

    composition.validate()
    envelope = []

    for feed_rate, syngas in zip(feed_rates, syngas_flows):
        if config.dual_chamber:
            dual = calculate_dual(
                total_syngas_kg_h = syngas,
                config            = config,
                composition       = composition,
                feed_rate_ar_kg_h = feed_rate,
                scenario_name     = f"{int(feed_rate)} kg/h",
            )
            pt = EnvelopePoint(
                feed_rate_ar      = feed_rate,
                syngas_kg_h       = syngas,
                has_valid_range   = dual.has_valid_range,
                split_min_valid   = dual.split_min_valid,
                split_max_valid   = dual.split_max_valid,
                split_recommended = dual.split_recommended,
                total_air_kg_h    = dual.total_air_kg_h,
                rbu_air_kg_h      = dual.rbu_air_kg_h,
                pcc_air_kg_h      = dual.pcc_air_kg_h,
            )
            if dual.has_valid_range and dual.rbu_at_recommended:
                pt.rbu_tau_at_rec = dual.rbu_at_recommended.residence_time_s
                pt.pcc_tau_at_rec = dual.pcc_at_recommended.residence_time_s
                pt.pcc_compliant  = dual.pcc_at_recommended.eu_wid_compliant

            # Status label
            if not dual.has_valid_range:
                pt.status = "EXCEEDS LIMIT"
            elif dual.split_max_valid - dual.split_min_valid < 0.10:
                pt.status = "TIGHT -- monitor split"
            elif pt.pcc_tau_at_rec < 2.5:
                pt.status = "LOW MARGIN"
            else:
                pt.status = "FEASIBLE"

        else:
            # Single chamber
            sc = calculate_chamber(
                syngas_kg_h     = syngas,
                chamber         = config.single_chamber,
                composition     = composition,
                T_operating     = config.T_pcc,
                excess_air      = config.excess_air_pcc,
                requires_eu_wid = True,
            )
            pt = EnvelopePoint(
                feed_rate_ar   = feed_rate,
                syngas_kg_h    = syngas,
                pcc_compliant  = sc.eu_wid_compliant,
                pcc_tau_at_rec = sc.residence_time_s,
                total_air_kg_h = sc.air_demand["actual_air_kg_h"],
                pcc_air_kg_h   = sc.air_demand["actual_air_kg_h"],
                has_valid_range = sc.eu_wid_compliant,
            )
            if not sc.eu_wid_compliant:
                pt.status = "EXCEEDS LIMIT"
            elif sc.residence_time_s < 2.5:
                pt.status = "LOW MARGIN"
            else:
                pt.status = "FEASIBLE"

        envelope.append(pt)

    return envelope


def print_envelope(envelope: list, dual_chamber: bool = True) -> None:
    """Print formatted operating envelope table."""
    print(f"\n{'='*95}")
    print("OPERATING ENVELOPE")
    print(f"{'='*95}")

    if dual_chamber:
        print(f"{'Feed':>8} {'Syngas':>8} {'Split min':>10} {'Split max':>10} "
              f"{'Rec split':>10} {'RBu tau':>8} {'PCC tau':>8} "
              f"{'Air RBu':>9} {'Air PCC':>9} {'Status'}")
        print(f"{'kg/h':>8} {'kg/h':>8} {'->RBu':>10} {'->RBu':>10} "
              f"{'->RBu':>10} {'[s]':>8} {'[s]':>8} "
              f"{'kg/h':>9} {'kg/h':>9}")
        print(f"{'-'*95}")
        for pt in envelope:
            if pt.has_valid_range:
                print(
                    f"{pt.feed_rate_ar:>8.0f} {pt.syngas_kg_h:>8.0f} "
                    f"{pt.split_min_valid:>10.2f} {pt.split_max_valid:>10.2f} "
                    f"{pt.split_recommended:>10.2f} {pt.rbu_tau_at_rec:>8.2f} "
                    f"{pt.pcc_tau_at_rec:>8.2f} "
                    f"{pt.rbu_air_kg_h:>9.0f} {pt.pcc_air_kg_h:>9.0f} "
                    f"  {pt.status}"
                )
            else:
                print(
                    f"{pt.feed_rate_ar:>8.0f} {pt.syngas_kg_h:>8.0f} "
                    f"{'---':>10} {'---':>10} {'---':>10} {'---':>8} "
                    f"{'---':>8} {'---':>9} {'---':>9}   {pt.status}"
                )
    else:
        print(f"{'Feed':>8} {'Syngas':>8} {'tau PCC':>10} "
              f"{'Compliant':>10} {'Air':>10} {'Status'}")
        print(f"{'-'*60}")
        for pt in envelope:
            print(
                f"{pt.feed_rate_ar:>8.0f} {pt.syngas_kg_h:>8.0f} "
                f"{pt.pcc_tau_at_rec:>10.2f} "
                f"{'YES' if pt.pcc_compliant else 'NO':>10} "
                f"{pt.total_air_kg_h:>10.0f}   {pt.status}"
            )

    print(f"{'='*95}\n")