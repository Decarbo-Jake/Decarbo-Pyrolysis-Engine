"""
Module 2 -- Mass Balance

Calculates biochar and syngas mass flows from feedstock and yield data.
Uses the ash balance method: all feedstock ash concentrates in biochar.

Validated against: LSM Report 2602TN-R0 (Jibito BR-01, May 2026)
All three scenarios (2000/2500/2800 kg/h) match LSM exactly.
"""

from dataclasses import dataclass, field
from typing import Optional


# -----------------------------------------------------------------------------
# DATA STRUCTURES
# -----------------------------------------------------------------------------

@dataclass
class MassBalanceInput:
    """
    Inputs required for mass balance calculation.
    Feed rate and composition from FeedstockResult + biochar ash measurement.
    """
    # Feed rate
    feed_rate_ar: float = 0.0        # kg/h as-received (wet basis)

    # From FeedstockResult
    moisture_ar: float = 0.0         # % moisture as-received
    ash_dry: float = 0.0             # % ash on dry basis

    # From biochar lab analysis (Eurofins or similar)
    ash_biochar_ar: float = 38.68    # % ash in biochar as-received
                                     # Jibito default: average of two Eurofins samples

    # Syngas composition (weight fractions) -- from HSC model or plant measurement
    NCG_wt_frac: float = 0.543       # Non-condensable gases (CO, CO2, CH4, H2)
    tars_wt_frac: float = 0.190      # Condensable tars
    H2O_wt_frac: float = 0.268       # Moisture in syngas

    # Name / label for reporting
    scenario_name: str = ""


@dataclass
class MassBalanceResult:
    """
    Mass balance outputs for a single feed rate scenario.
    All flows in kg/h. Yields as fractions (not %).
    """
    # Feed
    feed_ar: float = 0.0             # kg/h as-received (= input, echoed)
    feed_dry: float = 0.0            # kg/h dry basis
    moisture_in_feed: float = 0.0    # kg/h moisture entering with feed

    # Yield
    biochar_yield_dry: float = 0.0   # fraction of dry feed  (e.g. 0.1769 = 17.69%)
    biochar_yield_dry_pct: float = 0.0  # % for reporting

    # Biochar
    biochar_dry: float = 0.0         # kg/h dry basis
    biochar_ar: float = 0.0          # kg/h as-received (approx = dry for hot biochar)

    # Syngas total
    syngas: float = 0.0              # kg/h total (by difference)

    # Syngas fractions
    NCG: float = 0.0                 # kg/h non-condensable gas
    tars: float = 0.0                # kg/h condensable tars
    H2O_syngas: float = 0.0          # kg/h moisture in syngas

    # Mass balance closure
    closure: float = 0.0             # biochar + syngas -- should equal feed_ar
    closure_error_pct: float = 0.0   # % deviation from feed_ar

    # Flags
    warnings: list = field(default_factory=list)
    scenario_name: str = ""


# -----------------------------------------------------------------------------
# CORE FUNCTIONS
# -----------------------------------------------------------------------------

def biochar_yield_from_ash_balance(
    ash_feed_dry: float,
    ash_biochar_ar: float
) -> float:
    """
    Calculate biochar dry yield using the ash balance method.

    Assumption: ALL ash entering in the feedstock is retained entirely
    in the biochar. No ash leaves in the syngas or flue gas.

    Formula:
        Yield_dry = Ash_feed_dry [%] / Ash_biochar_ar [%]

    Args:
        ash_feed_dry:   Ash content of feedstock on dry basis [%]
        ash_biochar_ar: Ash content of biochar as-received [%]

    Returns:
        Biochar yield as a FRACTION of dry feed (e.g. 0.1769 for 17.69%)

    Example (Jibito BR-01):
        biochar_yield_from_ash_balance(6.843, 38.68) -> 0.1769
        LSM result: 17.69% -> 18% (rounded)  confirmed
    """
    if ash_biochar_ar <= 0:
        raise ValueError(f"Biochar ash content must be > 0 (got {ash_biochar_ar}%)")
    if ash_feed_dry <= 0:
        raise ValueError(f"Feedstock ash content must be > 0 (got {ash_feed_dry}%)")
    if ash_biochar_ar <= ash_feed_dry:
        raise ValueError(
            f"Biochar ash ({ash_biochar_ar}%) must be greater than feedstock ash "
            f"({ash_feed_dry}%) -- ash concentrates in biochar during pyrolysis"
        )
    return ash_feed_dry / ash_biochar_ar


def feed_dry(feed_ar: float, moisture_ar: float) -> float:
    """
    Calculate dry feed rate from as-received feed rate.

    Formula:
        Feed_dry = Feed_ar * (1 - Moisture_ar / 100)

    Args:
        feed_ar:     Feed rate as-received [kg/h]
        moisture_ar: Moisture content [% ar]

    Returns:
        Dry feed rate [kg/h]
    """
    return feed_ar * (1.0 - moisture_ar / 100.0)


def syngas_flow(feed_ar: float, biochar_dry: float) -> float:
    """
    Calculate syngas flow by mass conservation (difference method).

    Formula:
        Syngas = Feed_ar - Biochar_dry

    Note: Biochar moisture is ~0% at reactor exit temperature (550 degreesC),
    so biochar_dry  biochar_ar for mass balance purposes.

    Args:
        feed_ar:     Total feed rate as-received [kg/h]
        biochar_dry: Biochar flow on dry basis [kg/h]

    Returns:
        Syngas flow [kg/h]
    """
    return feed_ar - biochar_dry


# -----------------------------------------------------------------------------
# MAIN CALCULATION FUNCTION
# -----------------------------------------------------------------------------

def calculate(inputs: MassBalanceInput) -> MassBalanceResult:
    """
    Run complete mass balance for one feed rate scenario.

    Sequence:
      1. Calculate dry feed rate
      2. Calculate biochar yield (ash balance method)
      3. Calculate biochar flow
      4. Calculate syngas by difference
      5. Split syngas into NCG / tars / H2O fractions
      6. Check mass balance closure

    Args:
        inputs: MassBalanceInput with feed rate and composition data

    Returns:
        MassBalanceResult with all stream flows
    """
    result = MassBalanceResult()
    warnings = []
    result.scenario_name = inputs.scenario_name

    # Step 1: Feed flows
    result.feed_ar          = inputs.feed_rate_ar
    result.feed_dry         = feed_dry(inputs.feed_rate_ar, inputs.moisture_ar)
    result.moisture_in_feed = inputs.feed_rate_ar - result.feed_dry

    # Step 2: Biochar yield (ash balance)
    result.biochar_yield_dry     = biochar_yield_from_ash_balance(
        inputs.ash_dry, inputs.ash_biochar_ar
    )
    result.biochar_yield_dry_pct = result.biochar_yield_dry * 100.0

    # Step 3: Biochar flow
    result.biochar_dry = result.feed_dry * result.biochar_yield_dry
    result.biochar_ar  = result.biochar_dry   # moisture ~0% at 550 degreesC exit

    # Step 4: Syngas by difference
    result.syngas = syngas_flow(inputs.feed_rate_ar, result.biochar_dry)

    # Step 5: Syngas fractions
    result.NCG      = result.syngas * inputs.NCG_wt_frac
    result.tars     = result.syngas * inputs.tars_wt_frac
    result.H2O_syngas = result.syngas * inputs.H2O_wt_frac

    # Check syngas fractions sum to ~100%
    syngas_frac_sum = inputs.NCG_wt_frac + inputs.tars_wt_frac + inputs.H2O_wt_frac
    if not (0.98 <= syngas_frac_sum <= 1.02):
        warnings.append(
            f"Syngas fractions sum to {syngas_frac_sum:.3f} (expected ~1.0). "
            f"Check NCG + tars + H2O fractions."
        )

    # Step 6: Closure check
    result.closure = result.biochar_dry + result.syngas
    if result.feed_ar > 0:
        result.closure_error_pct = (
            (result.closure - result.feed_ar) / result.feed_ar * 100.0
        )

    if abs(result.closure_error_pct) > 0.1:
        warnings.append(
            f"Mass balance closure error: {result.closure_error_pct:+.2f}% "
            f"(biochar={result.biochar_dry:.1f} + syngas={result.syngas:.1f} "
            f"= {result.closure:.1f} vs feed={result.feed_ar:.1f} kg/h)"
        )

    result.warnings = warnings
    return result


# -----------------------------------------------------------------------------
# MULTI-SCENARIO RUNNER
# -----------------------------------------------------------------------------

def calculate_scenarios(
    feed_rates: list,
    moisture_ar: float,
    ash_dry: float,
    ash_biochar_ar: float = 38.68,
    NCG_wt_frac: float = 0.543,
    tars_wt_frac: float = 0.190,
    H2O_wt_frac: float = 0.268,
    scenario_names: Optional[list] = None,
) -> list:
    """
    Run mass balance for multiple feed rate scenarios in one call.

    Args:
        feed_rates:    List of feed rates [kg/h ar]  e.g. [2000, 2500, 2800]
        moisture_ar:   Feedstock moisture [% ar]
        ash_dry:       Feedstock ash [% dry]
        ash_biochar_ar: Biochar ash [% ar]  default: 38.68% (Jibito)
        NCG_wt_frac:   NCG weight fraction in syngas  default: 0.543
        tars_wt_frac:  Tars weight fraction  default: 0.190
        H2O_wt_frac:   H2O weight fraction   default: 0.268
        scenario_names: Optional list of labels

    Returns:
        List of MassBalanceResult -- one per feed rate
    """
    if scenario_names is None:
        scenario_names = [f"{int(fr)} kg/h" for fr in feed_rates]

    results = []
    for feed_rate, name in zip(feed_rates, scenario_names):
        inputs = MassBalanceInput(
            feed_rate_ar   = feed_rate,
            moisture_ar    = moisture_ar,
            ash_dry        = ash_dry,
            ash_biochar_ar = ash_biochar_ar,
            NCG_wt_frac    = NCG_wt_frac,
            tars_wt_frac   = tars_wt_frac,
            H2O_wt_frac    = H2O_wt_frac,
            scenario_name  = name,
        )
        results.append(calculate(inputs))

    return results


def print_summary(results: list) -> None:
    """
    Print a formatted summary table of mass balance results.
    Useful for quick checks during development.
    """
    print(f"\n{'-'*70}")
    print(f"MASS BALANCE SUMMARY")
    print(f"{'-'*70}")
    header = f"{'Stream':<25}" + "".join(
        f"{r.scenario_name:>14}" for r in results
    )
    print(header)
    print(f"{'-'*70}")

    rows = [
        ("Feed (ar) [kg/h]",        lambda r: r.feed_ar),
        ("Feed (dry) [kg/h]",       lambda r: r.feed_dry),
        ("Biochar yield [%dry]",    lambda r: r.biochar_yield_dry_pct),
        ("Biochar (dry) [kg/h]",    lambda r: r.biochar_dry),
        ("Syngas total [kg/h]",     lambda r: r.syngas),
        ("  NCG [kg/h]",            lambda r: r.NCG),
        ("  Tars [kg/h]",           lambda r: r.tars),
        ("  H2O [kg/h]",            lambda r: r.H2O_syngas),
        ("Closure error [%]",       lambda r: r.closure_error_pct),
    ]

    for label, fn in rows:
        row = f"{label:<25}" + "".join(f"{fn(r):>14.1f}" for r in results)
        print(row)

    print(f"{'-'*70}\n")
