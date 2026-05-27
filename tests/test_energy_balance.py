"""
Validation tests for engine/energy_balance.py

Reference: LSM Report 2602TN-R0 (Jibito BR-01, May 2026)
Scenario A (2,000 kg/h) is the primary validation case.
"""

import pytest
from engine.energy_balance import (
    EnergyBalanceInput,
    calculate,
    calculate_scenarios,
    feed_combustion_power,
    sensible_heat,
    biochar_chemical_energy,
    air_flow_from_sensible_heat,
)
from engine.constants import JIBITO_REFERENCE, CP_BIOMASS_WET, CP_BIOCHAR


# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------

@pytest.fixture
def jibito_A():
    """Scenario A -- 2,000 kg/h -- using LSM reference values."""
    return EnergyBalanceInput(
        feed_rate_ar      = 2000.0,
        LHV_ar            = JIBITO_REFERENCE["LHV_ar_kJ_kg"],   # 13,204 kJ/kg
        T_feed            = 35.0,
        T_ref             = 0.0,
        air_flow          = air_flow_from_sensible_heat(157.0, 27.0),
        T_air             = 27.0,
        biochar_dry       = 318.0,
        LHV_biochar_dry   = 16672.0,
        T_pyrolysis       = 550.0,
        flue_gas_loss_kW  = 5909.0,
        radiation_kW      = 85.0,
        biochar_latent_kW = 4.0,
        scenario_name     = "Scenario A -- 2000 kg/h",
    )


# -----------------------------------------------------------------------------
# UNIT TESTS
# -----------------------------------------------------------------------------

class TestFeedCombustionPower:

    def test_jibito_A_using_lsm_lhv(self):
        """Using LSM LHV_ar=13,204 -> should give LSM value of 7,316 kW."""
        result = feed_combustion_power(2000.0, 13204.0)
        assert abs(result - JIBITO_REFERENCE["feed_combustion_kW"]) < 25, \
            f"Expected ~7316, got {result:.0f}"

    def test_scales_linearly(self):
        """Double the feed rate -> double the power."""
        p1 = feed_combustion_power(1000.0, 13204.0)
        p2 = feed_combustion_power(2000.0, 13204.0)
        assert abs(p2 - 2 * p1) < 0.01


class TestSensibleHeat:

    def test_feed_sensible_jibito_A(self):
        """2000 kg/h feed at 35 degreesC -> 32 kW (LSM: 32 kW)."""
        result = sensible_heat(2000.0, CP_BIOMASS_WET, 35.0, 0.0)
        assert abs(result - JIBITO_REFERENCE["feed_sensible_kW"]) < 2.0, \
            f"Expected ~32 kW, got {result:.1f}"

    def test_air_sensible_jibito_A(self):
        """Back-calculated air flow at 27 degreesC -> 157 kW (LSM: 157 kW)."""
        air_flow = air_flow_from_sensible_heat(157.0, 27.0)
        result   = sensible_heat(air_flow, 1.04, 27.0, 0.0)
        assert abs(result - JIBITO_REFERENCE["air_sensible_kW"]) < 2.0, \
            f"Expected ~157 kW, got {result:.1f}"

    def test_biochar_sensible_jibito_A(self):
        """318 kg/h biochar at 550 degreesC -> 61 kW (LSM: 61 kW exact)."""
        result = sensible_heat(318.0, CP_BIOCHAR, 550.0, 0.0)
        assert abs(result - JIBITO_REFERENCE["biochar_sensible_kW"]) < 2.0, \
            f"Expected ~61 kW, got {result:.1f}"

    def test_zero_at_reference_temperature(self):
        """At T_ref, sensible heat must be zero."""
        result = sensible_heat(1000.0, 1.65, 0.0, 0.0)
        assert result == pytest.approx(0.0)


class TestBiocharChemicalEnergy:

    def test_jibito_A(self):
        """318 kg/h * 16,672 kJ/kg / 3600 = 1,471 kW (LSM: 1,471 kW exact)."""
        result = biochar_chemical_energy(318.0, 16672.0)
        assert abs(result - JIBITO_REFERENCE["biochar_combustion_kW"]) < 2.0, \
            f"Expected ~1471 kW, got {result:.1f}"


class TestAirFlowBackCalc:

    def test_jibito_A(self):
        """157 kW air sensible at 27 degreesC -> ~20,117 kg/h."""
        result = air_flow_from_sensible_heat(157.0, 27.0)
        assert abs(result - 20117) < 200, \
            f"Expected ~20117 kg/h, got {result:.0f}"

    def test_zero_delta_T_raises(self):
        """Air at reference temperature raises ValueError."""
        with pytest.raises(ValueError):
            air_flow_from_sensible_heat(157.0, T_air=0.0, T_ref=0.0)


# -----------------------------------------------------------------------------
# INTEGRATION TESTS
# -----------------------------------------------------------------------------

class TestCalculate:

    def test_feed_combustion_matches_lsm(self, jibito_A):
        """Feed combustion power within 1% of LSM."""
        result = calculate(jibito_A)
        lsm    = JIBITO_REFERENCE["feed_combustion_kW"]
        assert abs(result.feed_combustion_kW - lsm) / lsm < 0.01, \
            f"Feed combustion: {result.feed_combustion_kW:.0f} vs LSM {lsm}"

    def test_feed_sensible_matches_lsm(self, jibito_A):
        """Feed sensible heat = 32 kW."""
        result = calculate(jibito_A)
        assert abs(result.feed_sensible_kW - 32.0) < 2.0, \
            f"Expected ~32 kW, got {result.feed_sensible_kW:.1f}"

    def test_air_sensible_matches_lsm(self, jibito_A):
        """Air sensible heat = 157 kW."""
        result = calculate(jibito_A)
        assert abs(result.air_sensible_kW - 157.0) < 3.0, \
            f"Expected ~157 kW, got {result.air_sensible_kW:.1f}"

    def test_total_in_matches_lsm(self, jibito_A):
        """Total IN within 1% of LSM 7,505 kW."""
        result = calculate(jibito_A)
        lsm    = JIBITO_REFERENCE["total_in_kW"]
        assert abs(result.total_in_kW - lsm) / lsm < 0.01, \
            f"Total IN: {result.total_in_kW:.0f} vs LSM {lsm}"

    def test_biochar_combustion_matches_lsm(self, jibito_A):
        """Biochar chemical energy = 1,471 kW."""
        result = calculate(jibito_A)
        assert abs(result.biochar_combustion_kW - 1471.0) < 2.0, \
            f"Expected ~1471 kW, got {result.biochar_combustion_kW:.1f}"

    def test_biochar_sensible_matches_lsm(self, jibito_A):
        """Biochar sensible = 61 kW."""
        result = calculate(jibito_A)
        assert abs(result.biochar_sensible_kW - 61.0) < 2.0, \
            f"Expected ~61 kW, got {result.biochar_sensible_kW:.1f}"

    def test_radiation_correct(self, jibito_A):
        """Radiation = 85 kW (fixed)."""
        result = calculate(jibito_A)
        assert result.radiation_kW == pytest.approx(85.0)

    def test_total_out_matches_lsm(self, jibito_A):
        """Total OUT within 1% of LSM 7,532 kW."""
        result = calculate(jibito_A)
        lsm    = JIBITO_REFERENCE["total_out_kW"]
        assert abs(result.total_out_kW - lsm) / lsm < 0.01, \
            f"Total OUT: {result.total_out_kW:.0f} vs LSM {lsm}"

    def test_balance_error_within_2pct(self, jibito_A):
        """
        Balance error must be within 2%.
        Residual ~0.4% from LHV_ar Q3 discrepancy is acceptable.
        """
        result = calculate(jibito_A)
        assert abs(result.balance_error_pct) < 2.0, \
            f"Balance error {result.balance_error_pct:.2f}% exceeds 2%"

    def test_flue_gas_dominates_output(self, jibito_A):
        """Flue gas must be the dominant loss (>70% of total IN)."""
        result = calculate(jibito_A)
        assert result.flue_gas_fraction > 0.70, \
            f"Flue gas fraction {result.flue_gas_fraction:.1%} < 70%"

    def test_no_support_burner_needed(self, jibito_A):
        """Plant should be thermally self-sustaining (no support burner)."""
        result = calculate(jibito_A)
        assert result.support_burner_kW == 0.0

    def test_total_in_greater_than_zero(self, jibito_A):
        result = calculate(jibito_A)
        assert result.total_in_kW > 0


class TestCalculateScenarios:

    def test_all_three_jibito_scenarios(self):
        """All three scenarios must match LSM totals within 1%."""
        results = calculate_scenarios(
            feed_rates      = [2000, 2500, 2800],
            LHV_ar          = JIBITO_REFERENCE["LHV_ar_kJ_kg"],
            biochar_flows   = [318, 397, 445],
            air_flows       = [
                air_flow_from_sensible_heat(157.0, 27.0),
                air_flow_from_sensible_heat(193.0, 27.0),
                air_flow_from_sensible_heat(210.0, 27.0),
            ],
            flue_gas_losses = [5909, 7405, 8305],
            biochar_latent  = [4, 5, 6],
        )
        assert len(results) == 3

        lsm_totals_in  = [7505, 9378, 10497]
        lsm_totals_out = [7532, 9412, 10542]

        for i, result in enumerate(results):
            assert abs(result.total_in_kW  - lsm_totals_in[i])  / lsm_totals_in[i]  < 0.01
            assert abs(result.total_out_kW - lsm_totals_out[i]) / lsm_totals_out[i] < 0.01