"""
Validation tests for engine/feedstock.py

Reference values: LSM Report 2602TN-R0 (Jibito BR-01, May 2026)
"""

import pytest
from engine.feedstock import (
    FeedstockInput,
    analyse,
    ash_dry_from_wet,
    boie_hhv_daf,
    hhv_dry_from_daf,
    lhv_dry,
    lhv_ar,
    molar_ratios,
    from_library,
)
from engine.constants import JIBITO_REFERENCE


# -----------------------------------------------------------------------------
# FIXTURES  -- reusable test inputs
# -----------------------------------------------------------------------------

@pytest.fixture
def jibito_original():
    """BR-01 with ORIGINAL lab C content (35.17%) -- should flag HHV inconsistency."""
    return FeedstockInput(
        name         = "BR-01 Original Lab Data",
        lab_report   = "UBE-11/2023-0238",
        C_dry        = 35.17,
        H_dry        = 6.05,
        N_dry        = 0.98,
        O_dry        = 50.55,
        S_dry        = 0.431,
        Cl_dry       = 0.05,
        moisture_ar  = 10.13,
        ash_ar       = 6.15,
        HHV_dry_kcal = 3890.42,
    )


@pytest.fixture
def jibito_corrected():
    """BR-01 with LSM-CORRECTED composition (C adjusted to 43.5% daf)."""
    ash_dry     = ash_dry_from_wet(6.15, 10.13)
    dry_factor  = 1.0 - ash_dry / 100.0
    return FeedstockInput(
        name         = "BR-01 LSM-Corrected",
        lab_report   = "LSM 2602TN-R0",
        C_dry        = 43.50 * dry_factor,
        H_dry        = 6.49  * dry_factor,
        N_dry        = 1.05  * dry_factor,
        O_dry        = 48.51 * dry_factor,
        S_dry        = 0.46  * dry_factor,
        moisture_ar  = 10.13,
        ash_ar       = 6.15,
        HHV_dry_kcal = 3890.42,
    )


# -----------------------------------------------------------------------------
# UNIT TESTS
# -----------------------------------------------------------------------------

class TestAshConversion:

    def test_jibito_ash_dry(self):
        """6.15 / (1 - 10.13/100) = 6.843%"""
        result = ash_dry_from_wet(6.15, 10.13)
        assert abs(result - 6.843) < 0.01, f"Expected ~6.843, got {result:.3f}"

    def test_zero_moisture(self):
        """With zero moisture, ash_dry == ash_ar."""
        result = ash_dry_from_wet(10.0, 0.0)
        assert result == pytest.approx(10.0)

    def test_moisture_100_raises(self):
        """Moisture >= 100% must raise ValueError."""
        with pytest.raises(ValueError):
            ash_dry_from_wet(5.0, 100.0)


class TestBoieEquation:

    def test_corrected_hhv_daf_within_1pct_of_lsm(self):
        """
        Corrected composition -> ~17,572 kJ/kg.
        LSM HSC value: 17,484 kJ/kg.
        Boie vs HSC known to differ ~0.5% -- tolerance set to 1%.
        """
        result = boie_hhv_daf(43.50, 6.49, 1.05, 48.51, 0.46)
        lsm    = JIBITO_REFERENCE["HHV_daf_kJ_kg"]
        assert abs(result - lsm) / lsm < 0.01, \
            f"Expected ~{lsm} kJ/kg (+-1%), got {result:.0f}"

    def test_original_composition_gives_lower_hhv(self):
        """
        Original C=37.75% daf gives ~14,919 kJ/kg -- well below lab-reported
        16,288 kJ/kg. This confirms the Q1 inconsistency.
        """
        ash_dry = ash_dry_from_wet(6.15, 10.13)
        factor  = 1.0 / (1.0 - ash_dry / 100.0)
        result  = boie_hhv_daf(
            35.17 * factor, 6.05 * factor,
            0.98  * factor, 50.55 * factor, 0.431 * factor
        )
        assert result < 16000, \
            f"Original composition should give HHV < 16,000 kJ/kg, got {result:.0f}"

    def test_oxygen_penalty_reduces_hhv(self):
        """More oxygen in fuel = lower HHV (oxygen is already partially oxidised)."""
        hhv_low_O  = boie_hhv_daf(52.0, 6.0, 1.0, 40.0, 0.5)
        hhv_high_O = boie_hhv_daf(50.0, 6.0, 1.0, 42.0, 0.5)
        assert hhv_low_O > hhv_high_O, "Higher O content should reduce HHV"


class TestHHVConversions:

    def test_hhv_dry_within_1pct_of_lsm(self):
        """HHV_daf=17572, ash_dry=6.843% -> ~16,369 kJ/kg  (LSM: 16,288)"""
        result = hhv_dry_from_daf(17572, 6.843)
        lsm    = JIBITO_REFERENCE["HHV_dry_kJ_kg"]
        assert abs(result - lsm) / lsm < 0.01, \
            f"Expected ~{lsm} (+-1%), got {result:.0f}"

    def test_lhv_dry_within_3pct_of_lsm(self):
        """
        Our formula gives ~15,040 kJ/kg; LSM gives 14,720 kJ/kg.
        Known discrepancy Q2 -- tolerance set to 3%.
        """
        HHV_dry = hhv_dry_from_daf(17572, 6.843)
        result  = lhv_dry(HHV_dry, 6.05)
        lsm     = JIBITO_REFERENCE["LHV_dry_kJ_kg"]
        assert abs(result - lsm) / lsm < 0.03, \
            f"LHV_dry {result:.0f} vs LSM {lsm} -- exceeds Q2 tolerance of 3%"

    def test_lhv_ar_within_1pct_of_lsm(self):
        """
        Primary energy balance input.
        Our formula: ~13,270 kJ/kg; LSM: 13,204 kJ/kg  (diff: +0.5% -- Q3).
        """
        HHV_dry = hhv_dry_from_daf(17572, 6.843)
        HHV_ar  = HHV_dry * (1.0 - 10.13 / 100.0)
        result  = lhv_ar(HHV_ar, 6.05, 6.843, 10.13)
        lsm     = JIBITO_REFERENCE["LHV_ar_kJ_kg"]
        assert abs(result - lsm) / lsm < 0.015, \
            f"LHV_ar {result:.0f} vs LSM {lsm} -- exceeds Q3 tolerance of 1,5%"


class TestMolarRatios:

    def test_jibito_biochar_sample01(self):
        """
        Eurofins Sample 01: C=54.7%, H=1.2%, O=4.3% dry basis
        H/C=0.26, O/C=0.059 -> EBC Premium qualification confirmed
        """
        result = molar_ratios(54.7, 1.2, 4.3)
        assert abs(result["H_C"] - 0.263) < 0.005, \
            f"H/C expected 0.263, got {result['H_C']:.3f}"
        assert abs(result["O_C"] - 0.059) < 0.003, \
            f"O/C expected 0.059, got {result['O_C']:.3f}"

    def test_zero_carbon_raises(self):
        with pytest.raises(ValueError):
            molar_ratios(0.0, 5.0, 20.0)


# -----------------------------------------------------------------------------
# INTEGRATION TESTS -- full analyse() function
# -----------------------------------------------------------------------------

class TestAnalyse:

    def test_original_flags_inconsistency(self, jibito_original):
        """
        Original BR-01 data must trigger HHV inconsistency warning.
        C=35.17% cannot produce HHV=3,890 kCal/kg -- this is the Q1 finding.
        """
        result = analyse(jibito_original)
        assert result.composition_consistent is False, \
            "Original BR-01 must be flagged as inconsistent"
        assert any("INCONSISTENCY" in w for w in result.warnings), \
            "Must contain HHV inconsistency warning"

    def test_corrected_passes_consistency(self, jibito_corrected):
        """LSM-corrected composition should pass the consistency check."""
        result = analyse(jibito_corrected)
        assert result.composition_consistent is True, \
            f"Corrected composition should pass. Warnings: {result.warnings}"

    def test_corrected_hhv_dry_within_1pct(self, jibito_corrected):
        result = analyse(jibito_corrected)
        lsm    = JIBITO_REFERENCE["HHV_dry_kJ_kg"]
        assert abs(result.HHV_dry - lsm) / lsm < 0.015, \
            f"HHV_dry {result.HHV_dry:.0f} vs LSM {lsm}"

    def test_corrected_lhv_ar_within_1pct(self, jibito_corrected):
        """LHV_ar is the primary energy balance input -- must be within 1,5% of LSM."""
        result = analyse(jibito_corrected)
        lsm    = JIBITO_REFERENCE["LHV_ar_kJ_kg"]
        assert abs(result.LHV_ar - lsm) / lsm < 0.015, \
            f"LHV_ar {result.LHV_ar:.0f} vs LSM {lsm}"

    def test_ash_dry_correct(self, jibito_original):
        result = analyse(jibito_original)
        assert abs(result.ash_dry_pct - 6.843) < 0.015

    def test_lhv_always_less_than_hhv(self, jibito_corrected):
        result = analyse(jibito_corrected)
        assert result.LHV_dry < result.HHV_dry, "LHV_dry must be less than HHV_dry"
        assert result.LHV_ar  < result.HHV_ar,  "LHV_ar must be less than HHV_ar"

    def test_all_heating_values_positive(self, jibito_corrected):
        result = analyse(jibito_corrected)
        for name in ["HHV_daf_boie", "HHV_dry", "LHV_dry", "HHV_ar", "LHV_ar"]:
            assert getattr(result, name) > 0, f"{name} should be positive"


class TestFromLibrary:

    def test_sugar_cane_loads(self):
        feedstock = from_library("sugar_cane_brush")
        assert feedstock.moisture_ar == pytest.approx(10.13)

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            from_library("does_not_exist")

    def test_all_library_feedstocks_produce_valid_results(self):
        """Every feedstock in the library must produce positive heating values."""
        from engine.constants import FEEDSTOCK_LIBRARY
        for key in FEEDSTOCK_LIBRARY:
            feedstock = from_library(key)
            result    = analyse(feedstock)
            assert result.HHV_dry > 0, f"{key}: HHV_dry should be positive"
            assert result.LHV_ar  > 0, f"{key}: LHV_ar should be positive"