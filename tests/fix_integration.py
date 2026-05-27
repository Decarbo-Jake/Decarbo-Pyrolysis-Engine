code = """from dataclasses import dataclass, field
from typing import Optional
from engine.feedstock import FeedstockInput, analyse, FeedstockResult
from engine.mass_balance import MassBalanceInput, calculate as mb_calculate
from engine.mass_balance import MassBalanceResult
from engine.energy_balance import EnergyBalanceInput, calculate as eb_calculate
from engine.energy_balance import EnergyBalanceResult
from engine.heat_transfer import (
    ReactorGeometry, HeatTransferInput, HeatTransferResult,
    calculate as ht_calculate, feed_rate_sweep,
)
from engine.combustion import (
    CombustionConfig, SyngasComposition, DualChamberResult,
    calculate_dual, calculate_envelope, EnvelopePoint,
)
from engine.constants import (
    JIBITO_REFERENCE, EBC, MOLAR_MASS, CP_MOIST_AIR,
)


# ---------------------------------------------------------------------------
# CARBON SEQUESTRATION
# ---------------------------------------------------------------------------

def co2_sequestered(
    biochar_dry_kg_h: float,
    C_organic_pct: float,
    H_C_molar: float,
    operating_hours_yr: float = 8000.0,
) -> dict:
    \"\"\"
    Calculate CO2 sequestration from biochar production.

    Carbon permanence factor from EBC methodology:
      H/C < 0.4  ->  95% of C is permanently sequestered
      H/C < 0.7  ->  90% of C is permanently sequestered
      H/C >= 0.7 ->  does not qualify as stable biochar

    Args:
        biochar_dry_kg_h:  Biochar production rate [kg/h dry]
        C_organic_pct:     Organic carbon content of biochar [% dry]
        H_C_molar:         H/C molar ratio of biochar [-]
        operating_hours_yr: Plant operating hours per year

    Returns:
        dict with C_sequestered_kg_h, CO2_kg_h, CO2_t_yr, permanence_factor
    \"\"\"
    perm = EBC["carbon_permanence_factor"]
    if H_C_molar < 0.4:
        permanence = perm["H_C_below_0_4"]
    elif H_C_molar < 0.7:
        permanence = perm["H_C_below_0_7"]
    else:
        permanence = perm["H_C_above_0_7"]

    C_seq_kg_h  = biochar_dry_kg_h * (C_organic_pct / 100.0) * permanence
    CO2_kg_h    = C_seq_kg_h * (44.009 / MOLAR_MASS["C"])
    CO2_t_yr    = CO2_kg_h * operating_hours_yr / 1000.0

    return {
        "permanence_factor":    permanence,
        "C_sequestered_kg_h":   C_seq_kg_h,
        "CO2_equivalent_kg_h":  CO2_kg_h,
        "CO2_equivalent_t_yr":  CO2_t_yr,
        "operating_hours_yr":   operating_hours_yr,
        "H_C_molar":            H_C_molar,
        "C_organic_pct":        C_organic_pct,
    }


# ---------------------------------------------------------------------------
# SYSTEM INTEGRATION INPUT
# ---------------------------------------------------------------------------

@dataclass
class SystemInput:
    \"\"\"
    Complete plant specification for the integrated system calculation.
    All modules are driven from this single input object.
    \"\"\"
    # Identity
    project_name: str = "Unnamed Project"
    scenario_name: str = ""

    # Feedstock (Module 1)
    feedstock: FeedstockInput = None

    # Operating point
    feed_rate_ar: float = 1000.0       # kg/h as-received

    # Biochar quality (for CO2 calculation -- from Eurofins or default)
    biochar_C_organic_pct: float = 54.1   # % dry  (Jibito Eurofins S01)
    biochar_H_C_molar: float = 0.26       # mol/mol (Jibito Eurofins S01)
    biochar_ash_ar: float = 38.68         # % ar    (Jibito Eurofins average)

    # Annual operation
    operating_hours_yr: float = 8000.0   # hours/year

    # Reactor geometry (Module 4)
    reactor: ReactorGeometry = None

    # Combustion configuration (Module 5)
    combustion: CombustionConfig = None

    # Syngas composition (Module 5)
    syngas_composition: SyngasComposition = None

    # Energy balance inputs
    air_sensible_kW: float = 157.0       # from LSM or measurement
    flue_gas_loss_kW: float = 5909.0     # from HSC model or measurement
    biochar_latent_kW: float = 4.0

    # Combustion gas temperature OUTSIDE drum (not PLC reading)
    T_combustion_gas: float = 900.0      # degrees C

    def __post_init__(self):
        if self.feedstock is None:
            from engine.feedstock import from_library
            self.feedstock = from_library("sugar_cane_brush")
        if self.reactor is None:
            self.reactor = ReactorGeometry()
        if self.combustion is None:
            self.combustion = CombustionConfig()
        if self.syngas_composition is None:
            self.syngas_composition = SyngasComposition()


# ---------------------------------------------------------------------------
# SYSTEM INTEGRATION RESULT
# ---------------------------------------------------------------------------

@dataclass
class SystemResult:
    \"\"\"
    Complete integrated system result.
    Contains sub-results from each module plus integration conclusions.
    \"\"\"
    # Module results
    feedstock: FeedstockResult = None
    mass_balance: MassBalanceResult = None
    energy_balance: EnergyBalanceResult = None
    heat_transfer: HeatTransferResult = None
    combustion: DualChamberResult = None

    # Carbon sequestration
    sequestration: dict = field(default_factory=dict)

    # Integration conclusions
    system_status: str = ""
    thermal_feasible: bool = False
    combustion_feasible: bool = False
    fully_feasible: bool = False

    # At recommended operating point
    recommended_split: float = 0.0
    split_min_valid: float = 0.0
    split_max_valid: float = 0.0
    rbu_residence_time: float = 0.0
    pcc_residence_time: float = 0.0
    rbu_air_kg_h: float = 0.0
    pcc_air_kg_h: float = 0.0
    total_air_kg_h: float = 0.0
    thermal_margin_pct: float = 0.0
    max_feed_rate_ar: float = 0.0

    # CO2
    CO2_t_yr: float = 0.0

    # All warnings from all modules
    all_warnings: list = field(default_factory=list)

    # Input echo
    project_name: str = ""
    scenario_name: str = ""
    feed_rate_ar: float = 0.0


# ---------------------------------------------------------------------------
# MAIN INTEGRATION FUNCTION
# ---------------------------------------------------------------------------

def calculate(inputs: SystemInput) -> SystemResult:
    \"\"\"
    Run complete integrated plant analysis.

    Executes all modules in sequence and checks cross-module consistency.

    Args:
        inputs: SystemInput with complete plant specification

    Returns:
        SystemResult with all module outputs and integration conclusions
    \"\"\"
    result = SystemResult()
    all_warnings = []
    result.project_name  = inputs.project_name
    result.scenario_name = inputs.scenario_name
    result.feed_rate_ar  = inputs.feed_rate_ar

    # ------------------------------------------------------------------
    # STEP 1: Feedstock characterisation
    # ------------------------------------------------------------------
    result.feedstock = analyse(inputs.feedstock)
    if not result.feedstock.composition_consistent:
        all_warnings.extend(result.feedstock.warnings)
    if result.feedstock.warnings:
        for w in result.feedstock.warnings:
            if w not in all_warnings:
                all_warnings.append(w)

    # ------------------------------------------------------------------
    # STEP 2: Mass balance
    # ------------------------------------------------------------------
    mb_input = MassBalanceInput(
        feed_rate_ar   = inputs.feed_rate_ar,
        moisture_ar    = inputs.feedstock.moisture_ar,
        ash_dry        = result.feedstock.ash_dry_pct,
        ash_biochar_ar = inputs.biochar_ash_ar,
        NCG_wt_frac    = inputs.syngas_composition.NCG_wt,
        tars_wt_frac   = inputs.syngas_composition.tars_wt,
        H2O_wt_frac    = inputs.syngas_composition.H2O_wt,
        scenario_name  = inputs.scenario_name,
    )
    result.mass_balance = mb_calculate(mb_input)
    if result.mass_balance.warnings:
        all_warnings.extend(result.mass_balance.warnings)

    # ------------------------------------------------------------------
    # STEP 3: Energy balance
    # ------------------------------------------------------------------
    from engine.energy_balance import air_flow_from_sensible_heat
    air_flow = air_flow_from_sensible_heat(
        inputs.air_sensible_kW, 27.0
    )
    eb_input = EnergyBalanceInput(
        feed_rate_ar      = inputs.feed_rate_ar,
        LHV_ar            = result.feedstock.LHV_ar,
        T_feed            = inputs.feedstock.moisture_ar,
        air_flow          = air_flow,
        biochar_dry       = result.mass_balance.biochar_dry,
        flue_gas_loss_kW  = inputs.flue_gas_loss_kW,
        radiation_kW      = 85.0,
        biochar_latent_kW = inputs.biochar_latent_kW,
        scenario_name     = inputs.scenario_name,
    )
    result.energy_balance = eb_calculate(eb_input)
    if result.energy_balance.warnings:
        all_warnings.extend(result.energy_balance.warnings)

    # ------------------------------------------------------------------
    # STEP 4: Kiln heat transfer
    # ------------------------------------------------------------------
    ht_input = HeatTransferInput(
        T_combustion_gas  = inputs.T_combustion_gas,
        T_pyrolysis       = 600.0,
        T_feed            = 35.0,
        feed_rate_ar      = inputs.feed_rate_ar,
        moisture_ar       = inputs.feedstock.moisture_ar,
        feedstock_type    = "sugar_cane",
        h_combustion_conv = 50.0,
        h_pyrolysis       = 35.0,
        geometry          = inputs.reactor,
        scenario_name     = inputs.scenario_name,
    )
    result.heat_transfer = ht_calculate(ht_input)
    result.thermal_feasible  = result.heat_transfer.can_sustain_pyrolysis
    result.thermal_margin_pct = result.heat_transfer.thermal_margin_pct
    result.max_feed_rate_ar   = result.heat_transfer.max_feed_rate_ar
    if result.heat_transfer.warnings:
        all_warnings.extend(result.heat_transfer.warnings)

    # ------------------------------------------------------------------
    # STEP 5: Combustion system
    # ------------------------------------------------------------------
    inputs.syngas_composition.validate()

    if inputs.combustion.dual_chamber:
        result.combustion = calculate_dual(
            total_syngas_kg_h = result.mass_balance.syngas,
            config            = inputs.combustion,
            composition       = inputs.syngas_composition,
            feed_rate_ar_kg_h = inputs.feed_rate_ar,
            scenario_name     = inputs.scenario_name,
        )
        result.combustion_feasible = result.combustion.has_valid_range
        if result.combustion.has_valid_range:
            result.recommended_split    = result.combustion.split_recommended
            result.split_min_valid      = result.combustion.split_min_valid
            result.split_max_valid      = result.combustion.split_max_valid
            result.rbu_air_kg_h         = result.combustion.rbu_air_kg_h
            result.pcc_air_kg_h         = result.combustion.pcc_air_kg_h
            result.total_air_kg_h       = result.combustion.total_air_kg_h
            if result.combustion.rbu_at_recommended:
                result.rbu_residence_time = result.combustion.rbu_at_recommended.residence_time_s
            if result.combustion.pcc_at_recommended:
                result.pcc_residence_time = result.combustion.pcc_at_recommended.residence_time_s
        if result.combustion.warnings:
            all_warnings.extend(result.combustion.warnings)
    else:
        # Single chamber
        from engine.combustion import calculate_chamber
        sc = calculate_chamber(
            syngas_kg_h     = result.mass_balance.syngas,
            chamber         = inputs.combustion.single_chamber,
            composition     = inputs.syngas_composition,
            T_operating     = inputs.combustion.T_pcc,
            excess_air      = inputs.combustion.excess_air_pcc,
            requires_eu_wid = True,
        )
        result.combustion_feasible  = sc.eu_wid_compliant
        result.pcc_residence_time   = sc.residence_time_s
        result.pcc_air_kg_h         = sc.air_demand["actual_air_kg_h"]
        result.total_air_kg_h       = sc.air_demand["actual_air_kg_h"]
        if sc.warnings:
            all_warnings.extend(sc.warnings)

    # ------------------------------------------------------------------
    # STEP 6: Integration check
    # ------------------------------------------------------------------
    result.fully_feasible = result.thermal_feasible and result.combustion_feasible

    if not result.thermal_feasible and not result.combustion_feasible:
        result.system_status = "EXCEEDS LIMIT -- thermal and combustion both exceeded"
    elif not result.thermal_feasible:
        result.system_status = "EXCEEDS THERMAL LIMIT -- reduce feed rate"
    elif not result.combustion_feasible:
        result.system_status = "EXCEEDS COMBUSTION LIMIT -- PCC undersized for this flow"
    elif result.thermal_margin_pct < 10.0:
        result.system_status = "TIGHT -- operating near thermal ceiling"
    elif (result.combustion.has_valid_range and
          result.split_max_valid - result.split_min_valid < 0.10):
        result.system_status = "TIGHT -- narrow valid split range"
    else:
        result.system_status = "FEASIBLE"

    # ------------------------------------------------------------------
    # STEP 7: Carbon sequestration
    # ------------------------------------------------------------------
    result.sequestration = co2_sequestered(
        biochar_dry_kg_h   = result.mass_balance.biochar_dry,
        C_organic_pct      = inputs.biochar_C_organic_pct,
        H_C_molar          = inputs.biochar_H_C_molar,
        operating_hours_yr = inputs.operating_hours_yr,
    )
    result.CO2_t_yr = result.sequestration["CO2_equivalent_t_yr"]

    result.all_warnings = all_warnings
    return result


# ---------------------------------------------------------------------------
# MULTI-SCENARIO RUNNER
# ---------------------------------------------------------------------------

def calculate_scenarios(
    base_inputs: SystemInput,
    feed_rates: list,
) -> list:
    \"\"\"
    Run integrated analysis across multiple feed rates.
    All other inputs remain constant -- only feed rate varies.

    Args:
        base_inputs: SystemInput template
        feed_rates:  List of feed rates to evaluate [kg/h ar]

    Returns:
        List of SystemResult
    \"\"\"
    results = []
    for fr in feed_rates:
        inp = SystemInput(
            project_name        = base_inputs.project_name,
            scenario_name       = f"{int(fr)} kg/h",
            feedstock           = base_inputs.feedstock,
            feed_rate_ar        = fr,
            biochar_C_organic_pct = base_inputs.biochar_C_organic_pct,
            biochar_H_C_molar   = base_inputs.biochar_H_C_molar,
            biochar_ash_ar      = base_inputs.biochar_ash_ar,
            operating_hours_yr  = base_inputs.operating_hours_yr,
            reactor             = base_inputs.reactor,
            combustion          = base_inputs.combustion,
            syngas_composition  = base_inputs.syngas_composition,
            air_sensible_kW     = base_inputs.air_sensible_kW,
            flue_gas_loss_kW    = base_inputs.flue_gas_loss_kW,
            biochar_latent_kW   = base_inputs.biochar_latent_kW,
            T_combustion_gas    = base_inputs.T_combustion_gas,
        )
        results.append(calculate(inp))
    return results


# ---------------------------------------------------------------------------
# PRINT SUMMARY
# ---------------------------------------------------------------------------

def print_summary(result: SystemResult) -> None:
    \"\"\"Print formatted single-scenario summary.\"\"\"
    w = 70
    print(f"\\n{'='*w}")
    print(f"SYSTEM INTEGRATION RESULT  |  {result.project_name}")
    print(f"Scenario: {result.scenario_name}  |  Feed rate: {result.feed_rate_ar:.0f} kg/h ar")
    print(f"{'='*w}")

    print(f"\\nFEEDSTOCK")
    fs = result.feedstock
    print(f"  HHV_dry:      {fs.HHV_dry:.0f} kJ/kg")
    print(f"  LHV_ar:       {fs.LHV_ar:.0f} kJ/kg")
    print(f"  Consistent:   {'YES' if fs.composition_consistent else 'NO -- see warnings'}")

    print(f"\\nMASS BALANCE")
    mb = result.mass_balance
    print(f"  Feed (ar):    {mb.feed_ar:.0f} kg/h")
    print(f"  Biochar:      {mb.biochar_dry:.0f} kg/h dry  ({mb.biochar_yield_dry_pct:.1f}% yield)")
    print(f"  Syngas:       {mb.syngas:.0f} kg/h")

    print(f"\\nKILN HEAT TRANSFER")
    ht = result.heat_transfer
    print(f"  U overall:    {ht.U_overall:.1f} W/m2*K")
    print(f"  Q delivered:  {ht.Q_delivered_kW:.0f} kW")
    print(f"  Q required:   {ht.Q_required_kW:.0f} kW")
    print(f"  Margin:       {ht.thermal_margin_pct:.1f}%")
    print(f"  Max feed:     {ht.max_feed_rate_ar:.0f} kg/h")
    print(f"  Thermal OK:   {'YES' if result.thermal_feasible else 'NO'}")

    print(f"\\nCOMBUSTION SYSTEM")
    print(f"  Syngas flow:  {mb.syngas:.0f} kg/h")
    if result.combustion_feasible:
        print(f"  Valid splits: {result.split_min_valid:.2f} - {result.split_max_valid:.2f} to RBu")
        print(f"  Recommended:  {result.recommended_split:.2f} to RBu")
        print(f"  RBu tau:      {result.rbu_residence_time:.2f} s")
        print(f"  PCC tau:      {result.pcc_residence_time:.2f} s (EU WID min: 2.0s)")
        print(f"  Air to RBu:   {result.rbu_air_kg_h:.0f} kg/h")
        print(f"  Air to PCC:   {result.pcc_air_kg_h:.0f} kg/h")
        print(f"  Total air:    {result.total_air_kg_h:.0f} kg/h")
    else:
        print(f"  NO VALID SPLIT -- PCC cannot meet EU WID at this feed rate")

    print(f"\\nCARBON SEQUESTRATION")
    seq = result.sequestration
    print(f"  Biochar:      {mb.biochar_dry:.0f} kg/h dry")
    print(f"  C permanent:  {seq['C_sequestered_kg_h']:.1f} kg/h")
    print(f"  CO2 removed:  {seq['CO2_equivalent_kg_h']:.1f} kg/h")
    print(f"  CO2/year:     {result.CO2_t_yr:.0f} t CO2/year  ({seq['operating_hours_yr']:.0f} h/yr)")
    print(f"  Permanence:   {seq['permanence_factor']*100:.0f}%  (H/C={seq['H_C_molar']:.2f})")

    print(f"\\nSYSTEM STATUS:  {result.system_status}")

    if result.all_warnings:
        print(f"\\nWARNINGS ({len(result.all_warnings)}):")
        for w_txt in result.all_warnings:
            print(f"  ! {w_txt}")

    print(f"{'='*w}\\n")


def print_envelope(results: list) -> None:
    \"\"\"Print multi-scenario operating envelope table.\"\"\"
    print(f"\\n{'='*110}")
    print("OPERATING ENVELOPE")
    print(f"{'='*110}")
    print(
        f"{'Feed':>8} {'Biochar':>8} {'Syngas':>8} {'Q_del':>7} {'Q_req':>7} "
        f"{'Margin':>7} {'Split':>12} {'RBu_tau':>8} {'PCC_tau':>8} "
        f"{'Air_tot':>8} {'CO2/yr':>8}  Status"
    )
    print(
        f"{'kg/h':>8} {'kg/h':>8} {'kg/h':>8} {'kW':>7} {'kW':>7} "
        f"{'%':>7} {'min-max':>12} {'s':>8} {'s':>8} "
        f"{'kg/h':>8} {'t':>8}"
    )
    print(f"{'-'*110}")

    for r in results:
        mb = r.mass_balance
        ht = r.heat_transfer
        split_str = (
            f"{r.split_min_valid:.2f}-{r.split_max_valid:.2f}"
            if r.combustion_feasible else "---"
        )
        rbu_tau = f"{r.rbu_residence_time:.2f}" if r.combustion_feasible else "---"
        pcc_tau = f"{r.pcc_residence_time:.2f}" if r.combustion_feasible else "---"
        print(
            f"{r.feed_rate_ar:>8.0f} {mb.biochar_dry:>8.0f} {mb.syngas:>8.0f} "
            f"{ht.Q_delivered_kW:>7.0f} {ht.Q_required_kW:>7.0f} "
            f"{ht.thermal_margin_pct:>7.1f} {split_str:>12} "
            f"{rbu_tau:>8} {pcc_tau:>8} "
            f"{r.total_air_kg_h:>8.0f} {r.CO2_t_yr:>8.0f}  {r.system_status}"
        )

    print(f"{'='*110}\\n")
"""

with open("engine/integration.py", "w", encoding="utf-8") as f:
    f.write(code)

lines = len(code.splitlines())
print(f"Written: {lines} lines")

with open("engine/integration.py", "r") as f:
    content = f.read()
print("calculate function:", "def calculate" in content)
print("co2_sequestered:", "def co2_sequestered" in content)
print("SystemInput:", "class SystemInput" in content)
print("SystemResult:", "class SystemResult" in content)
print("print_envelope:", "def print_envelope" in content)