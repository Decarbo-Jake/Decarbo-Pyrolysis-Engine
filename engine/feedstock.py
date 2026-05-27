"""
Module 1 — Feedstock Characterisation

Converts raw laboratory data (ultimate + proximate analysis) into
all heating value bases used by the calculation engine.

All functions are pure — they take inputs and return outputs with no
side effects. No state is stored between calls.

Validated against: LSM Report 2602TN-R0 (Jibito BR-01, May 2026)
Tolerance vs LSM HSC Chemistry:
  HHV_daf : +0.5%  (HSC uses proprietary thermochemical database)
  LHV_dry : +2.2%  (Q2 — HSC LHV correction differs from standard Clausius)
  LHV_ar  : +0.5%  (Q3 — cascades from LHV_dry discrepancy)
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.constants import (
    BOIE,
    LATENT_HEAT_WATER_25C,
    H_TO_WATER_MASS_RATIO,
    KCAL_TO_KJ,
    MOLAR_MASS,
)


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FeedstockInput:
    """
    Raw laboratory data for a feedstock sample.
    All compositions in % (not fractions).
    """
    name: str = "unnamed"
    lab_report: str = ""

    # Ultimate analysis — DRY basis [%wt dry]
    C_dry: float = 0.0
    H_dry: float = 0.0
    N_dry: float = 0.0
    O_dry: float = 0.0
    S_dry: float = 0.0
    Cl_dry: float = 0.05

    # Proximate analysis — WET (as-received) basis [%wt ar]
    moisture_ar: float = 0.0
    ash_ar: float = 0.0
    VM_ar: float = 0.0
    FC_ar: float = 0.0

    # Calorific value from lab
    HHV_dry_kcal: Optional[float] = None
    HHV_dry_kJ: Optional[float] = None


@dataclass
class FeedstockResult:
    """
    Full characterisation result produced by analyse().
    All heating values in kJ/kg.
    """
    ash_dry_pct: float = 0.0

    # daf compositions [%daf]
    C_daf: float = 0.0
    H_daf: float = 0.0
    N_daf: float = 0.0
    O_daf: float = 0.0
    S_daf: float = 0.0
    sum_daf: float = 0.0

    # Boie result
    HHV_daf_boie: float = 0.0

    # Heating value cascade
    HHV_dry: float = 0.0
    LHV_dry: float = 0.0
    HHV_ar: float = 0.0
    LHV_ar: float = 0.0

    # kCal equivalents
    HHV_dry_kcal: float = 0.0
    LHV_ar_kcal: float = 0.0

    # Lab reference
    HHV_dry_lab_kJ: Optional[float] = None
    HHV_discrepancy_pct: Optional[float] = None

    # Flags
    composition_consistent: bool = True
    sum_daf_warning: bool = False
    warnings: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def ash_dry_from_wet(ash_ar: float, moisture_ar: float) -> float:
    """
    Convert ash from wet basis to dry basis.
    Ash_dry = Ash_ar / (1 - Moisture_ar / 100)

    Example (Jibito BR-01):
        ash_dry_from_wet(6.15, 10.13) -> 6.843 %dry
    """
    if moisture_ar >= 100.0:
        raise ValueError(f"Moisture cannot be >= 100% (got {moisture_ar}%)")
    return ash_ar / (1.0 - moisture_ar / 100.0)


def daf_composition(
    C_dry: float, H_dry: float, N_dry: float,
    O_dry: float, S_dry: float,
    ash_dry: float
) -> dict:
    """
    Convert ultimate analysis from dry basis to dry-ash-free (daf) basis.
    X_daf = X_dry / (1 - Ash_dry / 100)

    Example (Jibito BR-01 original):
        C_dry=35.17, ash_dry=6.843 -> C_daf = 37.75 %daf
    """
    factor = 1.0 / (1.0 - ash_dry / 100.0)
    return {
        "C":   C_dry * factor,
        "H":   H_dry * factor,
        "N":   N_dry * factor,
        "O":   O_dry * factor,
        "S":   S_dry * factor,
        "sum": (C_dry + H_dry + N_dry + O_dry + S_dry) * factor,
    }


def boie_hhv_daf(
    C_daf: float, H_daf: float, N_daf: float,
    O_daf: float, S_daf: float
) -> float:
    """
    Calculate HHV from ultimate analysis using the Boie equation.
    Inputs are PERCENTAGES on dry-ash-free basis.

    HHV_daf [kJ/kg] = 35160*xC + 116225*xH - 11090*xO + 6280*xN + 10465*xS
    where x = mass fraction (% / 100)

    Example (Jibito BR-01 corrected):
        boie_hhv_daf(43.5, 6.49, 1.05, 48.51, 0.46) -> ~17,572 kJ/kg
        LSM HSC value: 17,484 kJ/kg  (diff: +0.5%)
    """
    xC = C_daf / 100.0
    xH = H_daf / 100.0
    xN = N_daf / 100.0
    xO = O_daf / 100.0
    xS = S_daf / 100.0

    return (
        BOIE["C"] * xC +
        BOIE["H"] * xH +
        BOIE["O"] * xO +
        BOIE["N"] * xN +
        BOIE["S"] * xS
    )


def hhv_dry_from_daf(HHV_daf: float, ash_dry: float) -> float:
    """
    HHV_dry = HHV_daf * (1 - Ash_dry / 100)

    Example (Jibito):
        hhv_dry_from_daf(17572, 6.843) -> 16,369 kJ/kg
        LSM value: 16,288 kJ/kg  (diff: +0.5%)
    """
    return HHV_daf * (1.0 - ash_dry / 100.0)


def hhv_ar_from_dry(HHV_dry: float, moisture_ar: float) -> float:
    """
    HHV_ar = HHV_dry * (1 - Moisture_ar / 100)
    """
    return HHV_dry * (1.0 - moisture_ar / 100.0)


def lhv_dry(HHV_dry: float, H_dry: float) -> float:
    """
    LHV_dry = HHV_dry - 2442 * 9 * H_dry_fraction

    Subtracts latent heat of water formed when hydrogen combusts.
    9 kg H2O produced per kg H (molar mass ratio 18/2).

    Note: LSM reports 14,720 kJ/kg for Jibito; this gives ~15,040 kJ/kg.
    Known discrepancy Q2 — HSC uses different LHV correction.
    """
    H_dry_frac = H_dry / 100.0
    return HHV_dry - LATENT_HEAT_WATER_25C * H_TO_WATER_MASS_RATIO * H_dry_frac


def lhv_ar(
    HHV_ar: float,
    H_dry: float,
    ash_dry: float,
    moisture_ar: float
) -> float:
    """
    LHV_ar = HHV_ar - 2442 * (9 * H_ar_fraction + M_ar / 100)

    Subtracts latent heat of ALL steam in flue gas:
      (a) from hydrogen combustion: 9 * H_ar
      (b) from feed moisture evaporation: M_ar / 100

    Example (Jibito):
        lhv_ar(14711, 6.05, 6.843, 10.13) -> ~13,270 kJ/kg
        LSM value: 13,204 kJ/kg  (diff: +0.5% — documented as Q3)
    """
    H_ar_frac = (H_dry / 100.0) * (1.0 - ash_dry / 100.0) * (1.0 - moisture_ar / 100.0)
    M_ar_frac = moisture_ar / 100.0
    return HHV_ar - LATENT_HEAT_WATER_25C * (
        H_TO_WATER_MASS_RATIO * H_ar_frac + M_ar_frac
    )


def molar_ratios(
    C_pct: float, H_pct: float, O_pct: float,
    basis: str = "daf"
) -> dict:
    """
    Calculate H/C and O/C molar ratios for EBC biochar quality assessment.

    Example (Jibito Eurofins Sample 01 — dry basis):
        molar_ratios(54.7, 1.2, 4.3) -> H/C=0.263, O/C=0.059
        LSM values: H/C=0.26, O/C=0.059  confirmed
    """
    if C_pct <= 0:
        raise ValueError("Carbon content must be > 0")
    mol_C = C_pct / MOLAR_MASS["C"]
    mol_H = H_pct / MOLAR_MASS["H"]
    mol_O = O_pct / MOLAR_MASS["O"]
    return {
        "H_C": mol_H / mol_C,
        "O_C": mol_O / mol_C,
        "basis": basis,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANALYSIS FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def analyse(feedstock: FeedstockInput) -> FeedstockResult:
    """
    Run full feedstock characterisation from raw lab data.

    Sequence:
      1. Convert ash to dry basis
      2. Convert ultimate analysis to daf basis
      3. Boie equation -> HHV_daf
      4. HHV cascade: daf -> dry -> ar
      5. LHV_dry and LHV_ar
      6. Compare Boie vs lab HHV
      7. Flag inconsistencies
    """
    result = FeedstockResult()
    warnings = []

    # Step 1: Ash dry basis
    result.ash_dry_pct = ash_dry_from_wet(feedstock.ash_ar, feedstock.moisture_ar)

    # Step 2: daf composition
    daf = daf_composition(
        feedstock.C_dry, feedstock.H_dry, feedstock.N_dry,
        feedstock.O_dry, feedstock.S_dry,
        result.ash_dry_pct
    )
    result.C_daf = daf["C"]
    result.H_daf = daf["H"]
    result.N_daf = daf["N"]
    result.O_daf = daf["O"]
    result.S_daf = daf["S"]
    result.sum_daf = daf["sum"]

    if not (98.0 <= result.sum_daf <= 102.0):
        result.sum_daf_warning = True
        warnings.append(
            f"daf composition sums to {result.sum_daf:.1f}% (expected ~100%). "
            f"Check O is calculated by difference and all elements are included."
        )

    # Step 3: Boie HHV_daf
    result.HHV_daf_boie = boie_hhv_daf(
        result.C_daf, result.H_daf, result.N_daf,
        result.O_daf, result.S_daf
    )

    # Step 4: HHV cascade
    result.HHV_dry  = hhv_dry_from_daf(result.HHV_daf_boie, result.ash_dry_pct)
    result.HHV_ar   = hhv_ar_from_dry(result.HHV_dry, feedstock.moisture_ar)
    result.HHV_dry_kcal = result.HHV_dry / 4.1868

    # Step 5: LHV
    result.LHV_dry     = lhv_dry(result.HHV_dry, feedstock.H_dry)
    result.LHV_ar      = lhv_ar(result.HHV_ar, feedstock.H_dry,
                                 result.ash_dry_pct, feedstock.moisture_ar)
    result.LHV_ar_kcal = result.LHV_ar / 4.1868

    # Step 6: Compare against lab HHV
    if feedstock.HHV_dry_kJ is not None:
        lab_HHV_kJ = feedstock.HHV_dry_kJ
    elif feedstock.HHV_dry_kcal is not None:
        lab_HHV_kJ = feedstock.HHV_dry_kcal * 4.1868
    else:
        lab_HHV_kJ = None

    result.HHV_dry_lab_kJ = lab_HHV_kJ

    # Step 7: Consistency check
    if lab_HHV_kJ is not None:
        discrepancy = (result.HHV_dry - lab_HHV_kJ) / lab_HHV_kJ * 100.0
        result.HHV_discrepancy_pct = discrepancy

        if abs(discrepancy) > 5.0:
            result.composition_consistent = False
            warnings.append(
                f"WARNING HHV INCONSISTENCY: Boie gives {result.HHV_dry:.0f} kJ/kg dry, "
                f"lab reports {lab_HHV_kJ:.0f} kJ/kg dry "
                f"(discrepancy: {discrepancy:+.1f}%). "
                f"Elemental composition (especially C) may not match the reported HHV. "
                f"New certified lab analysis recommended. See Q1."
            )
        elif abs(discrepancy) > 2.0:
            warnings.append(
                f"Note: Boie vs lab HHV discrepancy = {discrepancy:+.1f}% "
                f"(within acceptable range for Boie equation)"
            )

    result.warnings = warnings
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: load from library
# ─────────────────────────────────────────────────────────────────────────────

def from_library(key: str) -> FeedstockInput:
    """
    Create a FeedstockInput from the built-in feedstock library in constants.py.

    Usage:
        feedstock = from_library("sugar_cane_brush")
        result = analyse(feedstock)
    """
    from engine.constants import FEEDSTOCK_LIBRARY

    if key not in FEEDSTOCK_LIBRARY:
        available = list(FEEDSTOCK_LIBRARY.keys())
        raise KeyError(f"Feedstock '{key}' not in library. Available: {available}")

    lib = FEEDSTOCK_LIBRARY[key]
    ash_dry = lib["ash_dry"]
    dry_factor = 1.0 - ash_dry / 100.0

    return FeedstockInput(
        name        = lib["description"],
        lab_report  = lib.get("source", ""),
        C_dry       = lib["C_daf"] * dry_factor,
        H_dry       = lib["H_daf"] * dry_factor,
        N_dry       = lib["N_daf"] * dry_factor,
        O_dry       = lib["O_daf"] * dry_factor,
        S_dry       = lib["S_daf"] * dry_factor,
        moisture_ar = lib["moisture_ar"],
        ash_ar      = ash_dry * (1.0 - lib["moisture_ar"] / 100.0),
        HHV_dry_kJ  = lib["HHV_dry"],
    )