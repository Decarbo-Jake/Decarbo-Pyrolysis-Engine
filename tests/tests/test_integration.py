import pytest
from engine.integration import (
    SystemInput,
    SystemResult,
    calculate,
    calculate_scenarios,
    co2_sequestered,
    print_summary,
    print_envelope,
)
from engine.feedstock import FeedstockInput, from_library, ash_dry_from_wet
from engine.heat_transfer import ReactorGeometry
from engine.combustion import CombustionConfig, SyngasComposition
from engine.constants import JIBITO_REFERENCE


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def jibito_feedstock():
    """BR-01 LSM-corrected composition."""
    ash_dry    = ash_dry_from_wet(6.15, 10.13)
    dry_factor = 1.0 - ash_dry / 100.0
    return FeedstockInput(
        name         = "BR-01 LSM-Corrected",
        C_dry        = 43.50 * dry_factor,
        H_dry        = 6.49  * dry_factor,
        N_dry        = 1.05  * dry_factor,
        O_dry        = 48.51 * dry_factor,
        S_dry        = 0.46  * dry_factor,
        moisture_ar  = 10.13,
        ash_ar       = 6.15,
        HHV_dry_kcal = 3890.42,
    )


@pytest.fixture
def jibito_reactor():
    """Operating plant reactor geometry."""
    return ReactorGeometry(
        diameter_outer = 2.4,
        length_heated  = 6.0,
        wall_thickness = 0.012,
        steel_grade    = "SS304",
    )


@pytest.fixture
def jibito_combustion():
    """Jibito combustion configuration."""
    return CombustionConfig(
        dual_chamber = True,
        T_rbu        = 950.0,
        T_pcc        = 900.0,
        excess_air_rbu = 1.30,
        excess_air_pcc = 1.20,
    )


@pytest.fixture
def jibito_inputs_2000(jibito_feedstock, jibito_reactor, jibito_combustion):
    """Complete Jibito system at 2000 kg/h."""
    return SystemInput(
        project_name          = "Jibito Biochar Plant",
        scenario_name         = "2000 kg/h",
        feedstock             = jibito_feedstock,
        feed_rate_ar          = 2000.0,
        biochar_C_organic_pct = 54.1,
        biochar_H_C_molar     = 0.26,
        biochar_ash_ar        = 38.68,
        operating_hours_yr    = 8000.0,
        reactor               = jibito_reactor,
        combustion            = jibito_combustion,
        air_sensible_kW       = 157.0,
        flue_gas_loss_kW      = 5909.0,
        biochar_latent_kW     = 4.0,
        T_combustion_gas      = 900.0,
    )


# ---------------------------------------------------------------------------
# CO2 SEQUESTRATION TESTS
# ---------------------------------------------------------------------------

class TestCO2Sequestration:

    def test_high_stability_biochar(self):
        """H/C < 0.4 -> 95% permanence."""
        result = co2_sequestered(318.0, 54.1, 0.26, 8000.0)
        assert result["permanence_factor"] == 0.95

    def test_medium_stability_biochar(self):
        """H/C between 0.4 and 0.7 -> 90% permanence."""
        result = co2_sequestered(318.0, 54.1, 0.55, 8000.0)
        assert result["permanence_factor"] == 0.90

    def test_co2_greater_than_carbon(self):
        """CO2 mass > C mass (molar weight ratio 44/12)."""
        result = co2_sequestered(318.0, 54.1, 0.26, 8000.0)
        assert result["CO2_equivalent_kg_h"] > result["C_sequestered_kg_h"]

    def test_co2_ratio_correct(self):
        """CO2/C mass ratio = 44/12 = 3.667."""
        result = co2_sequestered(100.0, 100.0, 0.26, 8000.0)
        ratio = result["CO2_equivalent_kg_h"] / result["C_sequestered_kg_h"]
        assert abs(ratio - 44.009/12.011) < 0.01

    def test_annual_scales_with_hours(self):
        """Double operating hours = double annual CO2."""
        r1 = co2_sequestered(318.0, 54.1, 0.26, 4000.0)
        r2 = co2_sequestered(318.0, 54.1, 0.26, 8000.0)
        assert abs(r2["CO2_equivalent_t_yr"] / r1["CO2_equivalent_t_yr"] - 2.0) < 0.01

    def test_jibito_co2_estimate(self):
        """
        At 318 kg/h biochar dry, 54.1% Corg, 95% permanence:
        CO2/yr should be roughly 4000-6000 t at 8000 h/yr.
        """
        result = co2_sequestered(318.0, 54.1, 0.26, 8000.0)
        assert 3000 < result["CO2_equivalent_t_yr"] < 7000, \
            f"CO2/yr = {result['CO2_equivalent_t_yr']:.0f} t -- outside expected range"


# ---------------------------------------------------------------------------
# SYSTEM INTEGRATION TESTS
# ---------------------------------------------------------------------------

class TestCalculate:

    def test_result_has_all_modules(self, jibito_inputs_2000):
        """All module sub-results must be populated."""
        result = calculate(jibito_inputs_2000)
        assert result.feedstock     is not None
        assert result.mass_balance  is not None
        assert result.energy_balance is not None
        assert result.heat_transfer is not None

    def test_feedstock_lhv_ar_close_to_lsm(self, jibito_inputs_2000):
        """LHV_ar within 2% of LSM reference value."""
        result = calculate(jibito_inputs_2000)
        lsm    = JIBITO_REFERENCE["LHV_ar_kJ_kg"]
        assert abs(result.feedstock.LHV_ar - lsm) / lsm < 0.02, \
            f"LHV_ar {result.feedstock.LHV_ar:.0f} vs LSM {lsm}"

    def test_biochar_matches_lsm(self, jibito_inputs_2000):
        """Biochar flow within 1 kg/h of LSM Scenario A."""
        result = calculate(jibito_inputs_2000)
        lsm    = JIBITO_REFERENCE["biochar_dry_kg_h"]
        assert abs(result.mass_balance.biochar_dry - lsm) <= 1.0, \
            f"Biochar {result.mass_balance.biochar_dry:.0f} vs LSM {lsm}"

    def test_syngas_matches_lsm(self, jibito_inputs_2000):
        """Syngas flow within 1 kg/h of LSM Scenario A."""
        result = calculate(jibito_inputs_2000)
        lsm    = JIBITO_REFERENCE["syngas_kg_h"]
        assert abs(result.mass_balance.syngas - lsm) <= 1.0, \
            f"Syngas {result.mass_balance.syngas:.0f} vs LSM {lsm}"

    def test_thermal_feasible_at_2000(self, jibito_inputs_2000):
        """Plant should be thermally feasible at 2000 kg/h."""
        result = calculate(jibito_inputs_2000)
        assert result.thermal_feasible, \
            f"Thermal: Q_del={result.heat_transfer.Q_delivered_kW:.0f} " \
            f"vs Q_req={result.heat_transfer.Q_required_kW:.0f} kW"

    def test_system_status_not_empty(self, jibito_inputs_2000):
        """System status must always be set."""
        result = calculate(jibito_inputs_2000)
        assert result.system_status != ""

    def test_co2_positive(self, jibito_inputs_2000):
        """CO2 sequestration must be positive."""
        result = calculate(jibito_inputs_2000)
        assert result.CO2_t_yr > 0

    def test_total_air_positive(self, jibito_inputs_2000):
        """Total combustion air demand must be positive."""
        result = calculate(jibito_inputs_2000)
        assert result.total_air_kg_h > 0

    def test_max_feed_rate_above_2000(self, jibito_inputs_2000):
        """Max sustainable feed rate must exceed current 2000 kg/h."""
        result = calculate(jibito_inputs_2000)
        assert result.max_feed_rate_ar > 2000.0, \
            f"Max feed rate {result.max_feed_rate_ar:.0f} should exceed 2000 kg/h"

    def test_pcc_tau_positive(self, jibito_inputs_2000):
        """PCC residence time must be calculated."""
        result = calculate(jibito_inputs_2000)
        assert result.pcc_residence_time >= 0


# ---------------------------------------------------------------------------
# MULTI-SCENARIO TESTS
# ---------------------------------------------------------------------------

class TestCalculateScenarios:

    def test_three_jibito_scenarios(self, jibito_inputs_2000):
        """Run 2000/2500/2800 kg/h and check all produce results."""
        results = calculate_scenarios(
            base_inputs = jibito_inputs_2000,
            feed_rates  = [2000, 2500, 2800],
        )
        assert len(results) == 3

    def test_biochar_increases_with_feed(self, jibito_inputs_2000):
        """More feed = more biochar."""
        results = calculate_scenarios(jibito_inputs_2000, [1000, 2000, 3000])
        bc = [r.mass_balance.biochar_dry for r in results]
        assert bc[0] < bc[1] < bc[2]

    def test_co2_increases_with_feed(self, jibito_inputs_2000):
        """More biochar = more CO2 sequestered."""
        results = calculate_scenarios(jibito_inputs_2000, [1000, 2000])
        assert results[1].CO2_t_yr > results[0].CO2_t_yr

    def test_q_required_increases_with_feed(self, jibito_inputs_2000):
        """Heat demand grows linearly with feed rate."""
        results = calculate_scenarios(jibito_inputs_2000, [1000, 2000])
        assert results[1].heat_transfer.Q_required_kW > \
               results[0].heat_transfer.Q_required_kW

    def test_q_delivered_constant_across_scenarios(self, jibito_inputs_2000):
        """Q_delivered is fixed by geometry -- must not change with feed rate."""
        results = calculate_scenarios(jibito_inputs_2000, [1000, 2000, 3000])
        Q_vals = [r.heat_transfer.Q_delivered_kW for r in results]
        spread = max(Q_vals) - min(Q_vals)
        assert spread < 1.0, \
            f"Q_delivered should be constant, spread = {spread:.1f} kW"

    def test_status_assigned_all_scenarios(self, jibito_inputs_2000):
        """Every scenario must have a system status."""
        results = calculate_scenarios(jibito_inputs_2000, [1000, 2000, 3000])
        for r in results:
            assert r.system_status != ""

    def test_print_functions_run_without_error(self, jibito_inputs_2000):
        """print_summary and print_envelope must not raise exceptions."""
        results = calculate_scenarios(jibito_inputs_2000, [2000, 2500])
        print_summary(results[0])
        print_envelope(results)