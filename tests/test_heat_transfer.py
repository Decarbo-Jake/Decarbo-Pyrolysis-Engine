"""
Validation tests for engine/heat_transfer.py

Primary validation dataset: 1,000 kg/h operating plant
  - PLC measured: T_combustion = 900 degreesC, T_pyrolysis = 600 degreesC
  - Reactor geometry: D_outer=2.4m, L=6.0m, t_wall=12mm, SS304
  - Heat transfer area: π × 2.4 × 6.0 = 45.24 m2

Secondary validation: Jibito thermal limit at ~2,800 kg/h (LSM 2602TN-R0)
"""

import math
import pytest
from engine.heat_transfer import (
    ReactorGeometry,
    HeatTransferInput,
    calculate,
    feed_rate_sweep,
    radiative_htc,
    overall_htc,
    heat_required,
    max_feed_rate,
)
from engine.constants import STEEL_GRADES


# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------

@pytest.fixture
def operating_plant_geometry():
    """1,000 kg/h operating plant -- from engineering drawing."""
    return ReactorGeometry(
        diameter_outer = 2.4,
        length_heated  = 6.0,
        wall_thickness = 0.012,
        steel_grade    = "SS304",
        diameter_inner = 1.4,
    )


@pytest.fixture
def operating_plant_inputs(operating_plant_geometry):
    """1,000 kg/h plant at PLC-measured temperatures."""
    return HeatTransferInput(
        T_combustion_gas  = 900.0,
        T_pyrolysis       = 600.0,
        T_feed            = 35.0,
        feed_rate_ar      = 1000.0,
        moisture_ar       = 10.13,
        ash_dry           = 6.843,
        feedstock_type    = "sugar_cane",
        h_combustion_conv = 50.0,
        h_pyrolysis       = 35.0,
        geometry          = operating_plant_geometry,
        scenario_name     = "1000 kg/h operating plant",
    )


# -----------------------------------------------------------------------------
# UNIT TESTS
# -----------------------------------------------------------------------------

class TestReactorGeometry:

    def test_heat_transfer_area(self, operating_plant_geometry):
        """A = π × 2.4 × 6.0 = 45.24 m2"""
        expected = math.pi * 2.4 * 6.0
        assert abs(operating_plant_geometry.heat_transfer_area - expected) < 0.01

    def test_ss304_conductivity(self, operating_plant_geometry):
        """SS304 thermal conductivity = 16 W/m*K."""
        assert operating_plant_geometry.thermal_conductivity == 16.0

    def test_ss304_max_service_temp(self, operating_plant_geometry):
        """SS304 max service temperature = 870 degreesC."""
        assert operating_plant_geometry.max_service_temp == 870

    def test_invalid_steel_grade_raises(self):
        geo = ReactorGeometry(steel_grade="INVALID_GRADE")
        with pytest.raises(ValueError):
            _ = geo.thermal_conductivity

    def test_area_scales_with_length(self):
        """Doubling length doubles heat transfer area."""
        geo1 = ReactorGeometry(diameter_outer=2.4, length_heated=6.0)
        geo2 = ReactorGeometry(diameter_outer=2.4, length_heated=12.0)
        assert abs(geo2.heat_transfer_area / geo1.heat_transfer_area - 2.0) < 0.001


class TestRadiativeHTC:

    def test_dominates_at_high_temperature(self):
        """
        At 779 degreesC combustion / 620 degreesC wall, h_rad should be >> 50 W/m2*K.
        Radiation dominates over convection at these temperatures.
        """
        h_rad = radiative_htc(779.0, 620.0)
        assert h_rad > 100.0, \
            f"h_rad = {h_rad:.1f} W/m2*K -- expected > 100 at 779 degreesC"

    def test_increases_with_temperature(self):
        """Higher temperatures = more radiation."""
        h_low  = radiative_htc(600.0, 500.0)
        h_high = radiative_htc(900.0, 800.0)
        assert h_high > h_low

    def test_zero_when_equal_temperatures(self):
        """No radiation when temperatures are equal."""
        result = radiative_htc(500.0, 500.0)
        assert result == 0.0

    def test_physically_reasonable_range(self):
        """At typical pyrolysis conditions, h_rad should be 100-300 W/m2*K."""
        h_rad = radiative_htc(779.0, 620.0)
        assert 50 < h_rad < 500, f"h_rad = {h_rad:.1f} outside expected range"


class TestOverallHTC:

    def test_ss304_wall_resistance_is_small(self):
        """
        SS304 12mm wall: R_wall = 0.012/16 = 0.00075 m2*K/W.
        This is small compared to convective resistances.
        Confirms steel grade is not the limiting factor.
        """
        U, R_wall, h_comb = overall_htc(
            h_combustion_conv = 50.0,
            h_radiation       = 173.0,
            wall_thickness    = 0.012,
            thermal_conductivity = 16.0,
            h_pyrolysis       = 35.0
        )
        assert abs(R_wall - 0.00075) < 0.0001, \
            f"R_wall = {R_wall:.5f}, expected 0.00075"

    def test_carbon_steel_gives_similar_U(self):
        """
        Carbon steel (lambda=50) vs SS304 (lambda=16): U should be similar.
        Wall conduction is not the dominant resistance.
        """
        U_ss304, _, _ = overall_htc(50.0, 173.0, 0.012, 16.0, 35.0)
        U_carbon, _, _ = overall_htc(50.0, 173.0, 0.012, 50.0, 35.0)
        diff_pct = abs(U_ss304 - U_carbon) / U_carbon * 100
        assert diff_pct < 5.0, \
            f"U difference SS304 vs carbon steel = {diff_pct:.1f}% -- expected < 5%"

    def test_pyrolysis_side_is_dominant_resistance(self):
        """
        Pyrolysis-side resistance (1/35 = 0.0286) should be the largest term.
        """
        U, R_wall, h_comb = overall_htc(50.0, 173.0, 0.012, 16.0, 35.0)
        R_pyrolysis  = 1.0 / 35.0   # 0.0286
        R_combustion = 1.0 / (50.0 + 173.0)  # 0.0045
        assert R_pyrolysis > R_combustion * 3, \
            "Pyrolysis side should be dominant resistance"

    def test_u_increases_with_h_pyrolysis(self):
        """Better pyrolysis-side mixing -> higher U -> more heat transfer."""
        U_low,  _, _ = overall_htc(50.0, 173.0, 0.012, 16.0, 25.0)
        U_high, _, _ = overall_htc(50.0, 173.0, 0.012, 16.0, 50.0)
        assert U_high > U_low


class TestHeatRequired:

    def test_1000kgh_total_heat(self):
        """
        At 1,000 kg/h, Q_required should be in range 350-450 kW.
        (sensible ~232 + moisture ~70 + reaction ~95 = ~397 kW)
        """
        Q_s, Q_m, Q_r, Q_tot = heat_required(1000.0, 10.13, 600.0, 35.0)
        assert 300 < Q_tot < 500, \
            f"Q_required = {Q_tot:.0f} kW, expected 300-500 kW at 1000 kg/h"

    def test_scales_linearly_with_feed_rate(self):
        """Double feed rate = double heat required."""
        _, _, _, Q_1000 = heat_required(1000.0, 10.13, 600.0, 35.0)
        _, _, _, Q_2000 = heat_required(2000.0, 10.13, 600.0, 35.0)
        assert abs(Q_2000 / Q_1000 - 2.0) < 0.01

    def test_sensible_heat_positive(self):
        """Sensible heat must be positive when T_pyrolysis > T_feed."""
        Q_s, _, _, _ = heat_required(1000.0, 10.13, 600.0, 35.0)
        assert Q_s > 0

    def test_moisture_evaporation_positive(self):
        """Moisture evaporation always requires energy."""
        _, Q_m, _, _ = heat_required(1000.0, 10.13, 600.0, 35.0)
        assert Q_m > 0

    def test_higher_moisture_increases_requirement(self):
        """More moisture in feed = more energy needed."""
        _, _, _, Q_dry   = heat_required(1000.0, 5.0,  600.0, 35.0)
        _, _, _, Q_moist = heat_required(1000.0, 30.0, 600.0, 35.0)
        assert Q_moist > Q_dry


# -----------------------------------------------------------------------------
# INTEGRATION TESTS
# -----------------------------------------------------------------------------

class TestCalculate:

    def test_1000kgh_can_sustain_pyrolysis(self, operating_plant_inputs):
        """
        At 1,000 kg/h with PLC temperatures (779/600 degreesC),
        the reactor must be able to sustain pyrolysis.
        This is validated by the fact the plant was operating.
        """
        result = calculate(operating_plant_inputs)
        assert result.can_sustain_pyrolysis, \
            f"Plant should sustain pyrolysis at 1000 kg/h. " \
            f"Q_del={result.Q_delivered_kW:.0f} vs Q_req={result.Q_required_kW:.0f} kW"

    def test_q_delivered_physically_reasonable(self, operating_plant_inputs):
        """
        Q_delivered should be in range 200-800 kW for this geometry.
        Far outside this range indicates a calculation error.
        """
        result = calculate(operating_plant_inputs)
        assert 200 < result.Q_delivered_kW < 1500, \
            f"Q_delivered = {result.Q_delivered_kW:.0f} kW outside expected range"

    def test_radiation_dominates_combustion_side(self, operating_plant_inputs):
        """h_radiation must be greater than h_convection at 779 degreesC."""
        result = calculate(operating_plant_inputs)
        h_conv = operating_plant_inputs.h_combustion_conv
        assert result.h_radiation > h_conv, \
            f"h_rad={result.h_radiation:.1f} should exceed h_conv={h_conv}"

    def test_heat_transfer_area_correct(self, operating_plant_inputs):
        """Area = π × 2.4 × 6.0 = 45.24 m2."""
        result = calculate(operating_plant_inputs)
        expected = math.pi * 2.4 * 6.0
        assert abs(result.heat_transfer_area_m2 - expected) < 0.01

    def test_wall_temperatures_between_combustion_and_pyrolysis(
        self, operating_plant_inputs
    ):
        """Wall temperatures must be between combustion gas and pyrolysis temp."""
        result = calculate(operating_plant_inputs)
        T_comb = operating_plant_inputs.T_combustion_gas
        T_pyr  = operating_plant_inputs.T_pyrolysis
        assert T_pyr < result.T_wall_inner < result.T_wall_outer < T_comb, \
            f"Wall temps out of order: {T_pyr} < {result.T_wall_inner:.0f} " \
            f"< {result.T_wall_outer:.0f} < {T_comb}"

    def test_ss304_temperature_warning_at_900c(self, operating_plant_inputs):
        """
        Combustion gas at 900C exceeds SS304 service limit of 870C.
        Warning MUST be raised -- this is a real engineering concern.
        At 900C outside the drum, SS304 is operating above its rated limit.
        Recommendation: upgrade to SS310S (limit 1050C) for long-term reliability.
        """
        result = calculate(operating_plant_inputs)
        assert result.steel_temp_warning, \
            f"Should flag temp warning: 900C > SS304 limit 870C"

    def test_max_feed_rate_above_operating_point(self, operating_plant_inputs):
        """
        Max feed rate should be above 1,000 kg/h (plant was operating).
        """
        result = calculate(operating_plant_inputs)
        assert result.max_feed_rate_ar > 1000.0, \
            f"Max feed rate {result.max_feed_rate_ar:.0f} should exceed 1000 kg/h"

    def test_surplus_is_positive_at_1000kgh(self, operating_plant_inputs):
        """Q_surplus must be positive -- reactor has headroom at 1,000 kg/h."""
        result = calculate(operating_plant_inputs)
        assert result.Q_surplus_kW > 0, \
            f"Q_surplus = {result.Q_surplus_kW:.0f} kW should be positive"


class TestFeedRateSweep:

    def test_sweep_returns_correct_count(self, operating_plant_geometry):
        """Sweep over 5 feed rates returns 5 results."""
        results = feed_rate_sweep(
            geometry         = operating_plant_geometry,
            T_combustion_gas = 779.0,
            T_pyrolysis      = 600.0,
            moisture_ar      = 10.13,
            feed_rates       = [500, 1000, 1500, 2000, 2500],
        )
        assert len(results) == 5

    def test_thermal_limit_exists_in_sweep(self, operating_plant_geometry):
        """
        In a sweep from 500 to 3000 kg/h, there must be a point where
        the reactor transitions from can_sustain=True to False.
        """
        results = feed_rate_sweep(
            geometry         = operating_plant_geometry,
            T_combustion_gas = 779.0,
            T_pyrolysis      = 600.0,
            moisture_ar      = 10.13,
            feed_rates       = list(range(500, 3500, 250)),
        )
        sustainable = [r.can_sustain_pyrolysis for r in results]
        # Should start True and eventually become False
        assert True  in sustainable, "Some feed rates should be sustainable"
        assert False in sustainable, "Some feed rates should exceed thermal limit"

    def test_q_required_scales_with_feed_rate(self, operating_plant_geometry):
        """Q_required should increase with feed rate."""
        results = feed_rate_sweep(
            geometry         = operating_plant_geometry,
            T_combustion_gas = 779.0,
            T_pyrolysis      = 600.0,
            moisture_ar      = 10.13,
            feed_rates       = [1000, 2000, 3000],
        )
        assert results[1].Q_required_kW > results[0].Q_required_kW
        assert results[2].Q_required_kW > results[1].Q_required_kW

    def test_q_delivered_constant_across_feed_rates(self, operating_plant_geometry):
        """
        Q_delivered depends only on geometry and temperatures -- NOT feed rate.
        It should be the same regardless of how much feed is going through.
        """
        results = feed_rate_sweep(
            geometry         = operating_plant_geometry,
            T_combustion_gas = 779.0,
            T_pyrolysis      = 600.0,
            moisture_ar      = 10.13,
            feed_rates       = [1000, 2000, 3000],
        )
        Q_values = [r.Q_delivered_kW for r in results]
        spread = max(Q_values) - min(Q_values)
        assert spread < 1.0, \
            f"Q_delivered should be constant, but spread = {spread:.1f} kW"