import math
import pytest
from engine.combustion import (
    ChamberGeometry,
    CombustionConfig,
    SyngasComposition,
    SingleChamberResult,
    DualChamberResult,
    EnvelopePoint,
    rbu_default,
    pcc_default,
    calculate_chamber,
    calculate_dual,
    calculate_envelope,
    gas_density,
    volumetric_flow_m3s,
    residence_time_s,
    combustion_air_demand,
    min_volume_for_compliance,
)
from engine.constants import EU_WID


# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------

@pytest.fixture
def rbu():
    return rbu_default()


@pytest.fixture
def pcc():
    return pcc_default()


@pytest.fixture
def composition():
    return SyngasComposition()


@pytest.fixture
def config_dual(rbu, pcc):
    return CombustionConfig(
        dual_chamber = True,
        rbu          = rbu,
        pcc          = pcc,
        T_rbu        = 950.0,
        T_pcc        = 900.0,
    )


@pytest.fixture
def config_single(pcc):
    return CombustionConfig(
        dual_chamber   = False,
        single_chamber = pcc,
        T_pcc          = 900.0,
    )


# -----------------------------------------------------------------------------
# GEOMETRY TESTS
# -----------------------------------------------------------------------------

class TestChamberGeometry:

    def test_rbu_internal_volume(self, rbu):
        """
        RBu: external D=1500mm, L=3000mm, refractory=100mm
        Internal: D=1300mm, L=2800mm
        Volume = pi x 0.65^2 x 2.8 = 3.72 m3
        """
        expected = math.pi * 0.65**2 * 2.8
        assert abs(rbu.internal_volume - expected) < 0.01, \
            f"RBu volume: expected {expected:.2f}, got {rbu.internal_volume:.2f}"

    def test_rbu_internal_diameter(self, rbu):
        """Internal diameter = 1500 - 2x100 = 1300mm = 1.3m"""
        assert abs(rbu.internal_diameter - 1.3) < 0.001

    def test_pcc_internal_volume(self, pcc):
        """
        PCC: internal 2000x4000x4000mm = 32.0 m3
        External = internal + 2x100mm refractory each side
        """
        assert abs(pcc.internal_volume - 32.0) < 0.1, \
            f"PCC volume: expected 32.0 m3, got {pcc.internal_volume:.2f}"

    def test_refractory_reduces_volume(self):
        """Thicker refractory = smaller internal volume."""
        geo1 = ChamberGeometry(
            length_ext=4.0, width_ext=2.2, height_ext=4.2,
            refractory_thickness=0.05
        )
        geo2 = ChamberGeometry(
            length_ext=4.0, width_ext=2.2, height_ext=4.2,
            refractory_thickness=0.15
        )
        assert geo1.internal_volume > geo2.internal_volume

    def test_zero_internal_dimension_raises(self):
        """Refractory thicker than half the chamber raises ValueError."""
        geo = ChamberGeometry(
            length_ext=0.1, width_ext=2.0, height_ext=2.0,
            refractory_thickness=0.10
        )
        with pytest.raises(ValueError):
            _ = geo.internal_volume


# -----------------------------------------------------------------------------
# GAS PHYSICS TESTS
# -----------------------------------------------------------------------------

class TestGasPhysics:

    def test_density_at_0c(self):
        assert abs(gas_density(0.0) - 1.293) < 0.001

    def test_density_decreases_with_temperature(self):
        assert gas_density(900.0) < gas_density(200.0)

    def test_density_at_850c(self):
        """EU WID operating temperature."""
        rho = gas_density(850.0)
        assert 0.25 < rho < 0.40

    def test_volumetric_flow_increases_with_temperature(self):
        """Same mass flow gives higher volumetric flow at higher temperature."""
        Q_low  = volumetric_flow_m3s(10000.0, 400.0)
        Q_high = volumetric_flow_m3s(10000.0, 900.0)
        assert Q_high > Q_low


# -----------------------------------------------------------------------------
# COMBUSTION AIR TESTS
# -----------------------------------------------------------------------------

class TestCombustionAir:

    def test_air_demand_positive(self, composition):
        result = combustion_air_demand(1000.0, composition, 1.3)
        assert result["actual_air_kg_h"] > 0
        assert result["theoretical_air_kg_h"] > 0

    def test_actual_air_exceeds_theoretical(self, composition):
        result = combustion_air_demand(1000.0, composition, 1.3)
        assert result["actual_air_kg_h"] > result["theoretical_air_kg_h"]

    def test_excess_air_factor_applied_correctly(self, composition):
        r1 = combustion_air_demand(1000.0, composition, 1.0)
        r2 = combustion_air_demand(1000.0, composition, 1.3)
        assert abs(r2["actual_air_kg_h"] / r1["actual_air_kg_h"] - 1.3) < 0.001

    def test_flue_gas_equals_syngas_plus_air(self, composition):
        r = combustion_air_demand(1000.0, composition, 1.3)
        assert abs(r["flue_gas_kg_h"] - (1000.0 + r["actual_air_kg_h"])) < 0.1

    def test_air_scales_with_syngas_flow(self, composition):
        r1 = combustion_air_demand(1000.0, composition, 1.3)
        r2 = combustion_air_demand(2000.0, composition, 1.3)
        assert abs(r2["actual_air_kg_h"] / r1["actual_air_kg_h"] - 2.0) < 0.001

    def test_syngas_composition_validation(self):
        bad = SyngasComposition(NCG_wt=0.6, tars_wt=0.3, H2O_wt=0.3)
        with pytest.raises(ValueError):
            bad.validate()


# -----------------------------------------------------------------------------
# SINGLE CHAMBER TESTS
# -----------------------------------------------------------------------------

class TestCalculateChamber:

    def test_pcc_at_1000kgh_compliant(self, pcc, composition):
        """
        PCC (32 m3) at 1000 kg/h syngas should be well within EU WID.
        Syngas flow ~706 kg/h at 1000 kg/h feed.
        """
        result = calculate_chamber(
            syngas_kg_h     = 706.0,
            chamber         = pcc,
            composition     = composition,
            T_operating     = 900.0,
            excess_air      = 1.2,
            requires_eu_wid = True,
        )
        assert result.eu_wid_compliant, \
            f"PCC should be compliant at 706 kg/h syngas, tau={result.residence_time_s:.2f}s"
        assert result.residence_time_s > 2.0

    def test_pcc_at_2500kgh_compliance(self, pcc, composition):
        """
        PCC (32 m3) at 2500 kg/h -- syngas ~2103 kg/h.
        Check whether PCC remains compliant.
        """
        result = calculate_chamber(
            syngas_kg_h     = 2103.0,
            chamber         = pcc,
            composition     = composition,
            T_operating     = 900.0,
            excess_air      = 1.2,
            requires_eu_wid = True,
        )
        # Report result -- compliance depends on actual geometry
        print(f"\nPCC at 2500 kg/h: tau={result.residence_time_s:.2f}s, "
              f"compliant={result.eu_wid_compliant}")

    def test_rbu_residence_time_at_1000kgh(self, rbu, composition):
        """
        RBu (3.72 m3) at 1000 kg/h -- 50% syngas split = 353 kg/h syngas to RBu.
        This is a small chamber -- residence time will be short.
        """
        result = calculate_chamber(
            syngas_kg_h     = 353.0,
            chamber         = rbu,
            composition     = composition,
            T_operating     = 950.0,
            excess_air      = 1.3,
            requires_eu_wid = False,
        )
        print(f"\nRBu at 353 kg/h syngas: tau={result.residence_time_s:.2f}s")
        assert result.residence_time_s > 0

    def test_residence_time_inversely_proportional_to_flow(self, pcc, composition):
        """Double syngas flow = half residence time."""
        r1 = calculate_chamber(706.0,  pcc, composition, 900.0, 1.2)
        r2 = calculate_chamber(1412.0, pcc, composition, 900.0, 1.2)
        ratio = r1.residence_time_s / r2.residence_time_s
        assert abs(ratio - 2.0) < 0.05, \
            f"Expected 2x ratio, got {ratio:.2f}"

    def test_min_volume_calculated(self, pcc, composition):
        result = calculate_chamber(2103.0, pcc, composition, 900.0, 1.2)
        assert result.min_volume_required_m3 > 0

    def test_non_compliant_triggers_warning(self, composition):
        """A tiny chamber must trigger EU WID warning."""
        tiny = ChamberGeometry(
            length_ext=1.5, width_ext=1.5, height_ext=1.5,
            refractory_thickness=0.10,
            name="Tiny"
        )
        result = calculate_chamber(
            syngas_kg_h     = 2000.0,
            chamber         = tiny,
            composition     = composition,
            T_operating     = 900.0,
            excess_air      = 1.2,
            requires_eu_wid = True,
        )
        assert not result.eu_wid_compliant
        assert len(result.warnings) > 0
        assert any("NON-COMPLIANT" in w for w in result.warnings)


# -----------------------------------------------------------------------------
# DUAL CHAMBER TESTS
# -----------------------------------------------------------------------------

class TestCalculateDual:

    def test_has_valid_range_at_low_feed(self, config_dual, composition):
        """At 1000 kg/h (706 kg/h syngas), PCC should have valid splits."""
        result = calculate_dual(
            total_syngas_kg_h = 706.0,
            config            = config_dual,
            composition       = composition,
            feed_rate_ar_kg_h = 1000.0,
        )
        assert result.has_valid_range, \
            f"Should have valid splits at 1000 kg/h. Warnings: {result.warnings}"

    def test_valid_split_range_makes_sense(self, config_dual, composition):
        """Valid split min must be less than valid split max."""
        result = calculate_dual(706.0, config_dual, composition, 1000.0)
        if result.has_valid_range:
            assert result.split_min_valid < result.split_max_valid

    def test_recommended_split_within_valid_range(self, config_dual, composition):
        """Recommended split must be within the valid range."""
        result = calculate_dual(706.0, config_dual, composition, 1000.0)
        if result.has_valid_range:
            assert result.split_min_valid <= result.split_recommended <= result.split_max_valid

    def test_air_demand_calculated_at_recommended(self, config_dual, composition):
        """Air demand must be positive at recommended split."""
        result = calculate_dual(706.0, config_dual, composition, 1000.0)
        if result.has_valid_range:
            assert result.rbu_air_kg_h > 0
            assert result.pcc_air_kg_h > 0
            assert result.total_air_kg_h > result.rbu_air_kg_h

    def test_split_fractions_sum_to_one(self, config_dual, composition):
        """At every split point, RBu + PCC fractions must sum to 1."""
        result = calculate_dual(706.0, config_dual, composition, 1000.0)
        for sr in result.split_results:
            total = sr.split_fraction_rbu + sr.split_fraction_pcc
            assert abs(total - 1.0) < 0.001, \
                f"Split fractions sum to {total:.3f}"

    def test_pcc_tau_increases_as_less_gas_to_pcc(self, config_dual, composition):
        """More gas to RBu (higher split) = less to PCC = longer PCC residence time."""
        result = calculate_dual(1682.0, config_dual, composition, 2000.0)
        # Find two split results
        low_split  = [sr for sr in result.split_results if sr.split_fraction_rbu == 0.30]
        high_split = [sr for sr in result.split_results if sr.split_fraction_rbu == 0.60]
        if low_split and high_split:
            tau_low  = low_split[0].pcc.residence_time_s
            tau_high = high_split[0].pcc.residence_time_s
            assert tau_high > tau_low, \
                "More gas to RBu should give longer PCC residence time"

    def test_no_valid_range_triggers_warning(self, config_dual, composition):
        """Extremely high syngas flow should produce no valid range and warnings."""
        result = calculate_dual(
            total_syngas_kg_h = 50000.0,  # unrealistically high
            config            = config_dual,
            composition       = composition,
            feed_rate_ar_kg_h = 99999.0,
        )
        assert not result.has_valid_range
        assert len(result.warnings) > 0


# -----------------------------------------------------------------------------
# OPERATING ENVELOPE TESTS
# -----------------------------------------------------------------------------

class TestCalculateEnvelope:

    def test_envelope_length_matches_inputs(self, config_dual, composition):
        """One envelope point per feed rate."""
        envelope = calculate_envelope(
            feed_rates   = [1000, 1500, 2000, 2500, 2800],
            syngas_flows = [706,  1059, 1412, 1765, 1978],
            config       = config_dual,
            composition  = composition,
        )
        assert len(envelope) == 5

    def test_low_feed_rates_feasible(self, config_dual, composition):
        """1000 kg/h should be feasible with valid split range."""
        envelope = calculate_envelope(
            feed_rates   = [1000],
            syngas_flows = [706],
            config       = config_dual,
        )
        assert envelope[0].has_valid_range, \
            f"1000 kg/h should be feasible. Status: {envelope[0].status}"

    def test_status_labels_assigned(self, config_dual, composition):
        """Every envelope point must have a non-empty status."""
        envelope = calculate_envelope(
            feed_rates   = [1000, 2000, 5000],
            syngas_flows = [706,  1412, 3531],
            config       = config_dual,
        )
        for pt in envelope:
            assert pt.status != "", f"Missing status at {pt.feed_rate_ar} kg/h"

    def test_single_chamber_envelope(self, config_single, composition):
        """Single chamber envelope should work without split calculations."""
        envelope = calculate_envelope(
            feed_rates   = [1000, 2000],
            syngas_flows = [706,  1412],
            config       = config_single,
        )
        assert len(envelope) == 2
        for pt in envelope:
            assert pt.pcc_tau_at_rec >= 0

    def test_jibito_three_scenarios(self, config_dual):
        """
        Jibito three LSM scenarios -- check PCC compliance at each.
        Uses actual syngas flows from mass balance (all syngas to PCC).
        """
        envelope = calculate_envelope(
            feed_rates   = [2000,  2500,  2800],
            syngas_flows = [1682,  2103,  2355],
            config       = config_dual,
        )
        print("\nJibito Operating Envelope:")
        for pt in envelope:
            print(f"  {pt.feed_rate_ar:.0f} kg/h: "
                  f"valid={pt.has_valid_range}, "
                  f"split={pt.split_min_valid:.2f}-{pt.split_max_valid:.2f}, "
                  f"PCC tau={pt.pcc_tau_at_rec:.2f}s, "
                  f"status={pt.status}")
        assert len(envelope) == 3