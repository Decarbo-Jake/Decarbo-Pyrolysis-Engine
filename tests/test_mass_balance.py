"""
Validation tests for engine/mass_balance.py

Reference: LSM Report 2602TN-R0 (Jibito BR-01)
All three scenarios must match LSM flow diagrams exactly (within 1 kg/h).
"""

import pytest
from engine.mass_balance import (
    MassBalanceInput,
    calculate,
    calculate_scenarios,
    biochar_yield_from_ash_balance,
    feed_dry,
    syngas_flow,
)
from engine.constants import JIBITO_REFERENCE


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def jibito_A():
    return MassBalanceInput(
        feed_rate_ar   = 2000.0,
        moisture_ar    = 10.13,
        ash_dry        = 6.843,
        ash_biochar_ar = 38.68,
        scenario_name  = "Scenario A — 2000 kg/h",
    )

@pytest.fixture
def jibito_B():
    return MassBalanceInput(
        feed_rate_ar   = 2500.0,
        moisture_ar    = 10.13,
        ash_dry        = 6.843,
        ash_biochar_ar = 38.68,
        scenario_name  = "Scenario B — 2500 kg/h",
    )

@pytest.fixture
def jibito_C():
    return MassBalanceInput(
        feed_rate_ar   = 2800.0,
        moisture_ar    = 10.13,
        ash_dry        = 6.843,
        ash_biochar_ar = 38.68,
        scenario_name  = "Scenario C — 2800 kg/h",
    )


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAshBalance:

    def test_jibito_yield(self):
        """6.843 / 38.68 = 17.69% dry yield — matches LSM exactly."""
        result = biochar_yield_from_ash_balance(6.843, 38.68)
        expected = JIBITO_REFERENCE["biochar_yield_dry_pct"]
        assert abs(result * 100 - expected) < 0.01, \
            f"Expected {expected}%, got {result*100:.2f}%"

    def test_biochar_ash_must_exceed_feed_ash(self):
        """Biochar ash must be higher than feedstock ash."""
        with pytest.raises(ValueError):
            biochar_yield_from_ash_balance(ash_feed_dry=40.0, ash_biochar_ar=20.0)

    def test_zero_biochar_ash_raises(self):
        with pytest.raises(ValueError):
            biochar_yield_from_ash_balance(6.84, 0.0)

    def test_higher_feed_ash_gives_higher_yield(self):
        """Higher ash feedstock -> more biochar."""
        yield_low  = biochar_yield_from_ash_balance(5.0,  38.68)
        yield_high = biochar_yield_from_ash_balance(10.0, 38.68)
        assert yield_high > yield_low


class TestFeedDry:

    def test_jibito_2000(self):
        """2000 * (1 - 10.13/100) = 1,797.4 kg/h dry."""
        result = feed_dry(2000.0, 10.13)
        assert abs(result - 1797.4) < 1.0, f"Expected ~1797.4, got {result:.1f}"

    def test_zero_moisture(self):
        """Zero moisture: dry feed = wet feed."""
        assert feed_dry(1000.0, 0.0) == pytest.approx(1000.0)


class TestSyngasFlow:

    def test_jibito_A(self):
        """2000 - 318 = 1,682 kg/h."""
        assert syngas_flow(2000.0, 318.0) == pytest.approx(1682.0)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculate:

    def test_scenario_A_biochar(self, jibito_A):
        """Biochar at 2,000 kg/h: LSM = 318 kg/h."""
        result = calculate(jibito_A)
        assert abs(result.biochar_dry - JIBITO_REFERENCE["biochar_dry_kg_h"]) <= 1.0, \
            f"Expected 318, got {result.biochar_dry:.1f}"

    def test_scenario_A_syngas(self, jibito_A):
        """Syngas at 2,000 kg/h: LSM = 1,682 kg/h."""
        result = calculate(jibito_A)
        assert abs(result.syngas - JIBITO_REFERENCE["syngas_kg_h"]) <= 1.0, \
            f"Expected 1682, got {result.syngas:.1f}"

    def test_scenario_B_biochar(self, jibito_B):
        """Biochar at 2,500 kg/h: LSM = 397 kg/h."""
        result = calculate(jibito_B)
        assert abs(result.biochar_dry - JIBITO_REFERENCE["biochar_dry_kg_h_B"]) <= 1.0, \
            f"Expected 397, got {result.biochar_dry:.1f}"

    def test_scenario_B_syngas(self, jibito_B):
        """Syngas at 2,500 kg/h: LSM = 2,103 kg/h."""
        result = calculate(jibito_B)
        assert abs(result.syngas - JIBITO_REFERENCE["syngas_kg_h_B"]) <= 1.0, \
            f"Expected 2103, got {result.syngas:.1f}"

    def test_scenario_C_biochar(self, jibito_C):
        """Biochar at 2,800 kg/h: LSM = 445 kg/h."""
        result = calculate(jibito_C)
        assert abs(result.biochar_dry - JIBITO_REFERENCE["biochar_dry_kg_h_C"]) <= 1.0, \
            f"Expected 445, got {result.biochar_dry:.1f}"

    def test_scenario_C_syngas(self, jibito_C):
        """Syngas at 2,800 kg/h: LSM = 2,355 kg/h."""
        result = calculate(jibito_C)
        assert abs(result.syngas - JIBITO_REFERENCE["syngas_kg_h_C"]) <= 1.0, \
            f"Expected 2355, got {result.syngas:.1f}"

    def test_mass_balance_closure(self, jibito_A):
        """Biochar + Syngas must equal Feed_ar exactly."""
        result = calculate(jibito_A)
        assert abs(result.closure_error_pct) < 0.01, \
            f"Closure error: {result.closure_error_pct:.4f}%"

    def test_syngas_fractions_sum_correctly(self, jibito_A):
        """NCG + Tars + H2O must sum to total syngas."""
        result = calculate(jibito_A)
        fraction_sum = result.NCG + result.tars + result.H2O_syngas
        assert abs(fraction_sum - result.syngas) < 2.0, \
            f"Fractions {fraction_sum:.1f} != syngas {result.syngas:.1f}"

    def test_biochar_less_than_feed(self, jibito_A):
        """Biochar must always be less than feed rate."""
        result = calculate(jibito_A)
        assert result.biochar_dry < result.feed_ar

    def test_syngas_greater_than_biochar(self, jibito_A):
        """Syngas flow must be larger than biochar flow."""
        result = calculate(jibito_A)
        assert result.syngas > result.biochar_dry


class TestCalculateScenarios:

    def test_all_three_scenarios(self):
        """Run all three LSM scenarios and verify all outputs."""
        results = calculate_scenarios(
            feed_rates     = [2000, 2500, 2800],
            moisture_ar    = 10.13,
            ash_dry        = 6.843,
            ash_biochar_ar = 38.68,
        )
        assert len(results) == 3
        assert abs(results[0].biochar_dry - 318)  <= 1.0
        assert abs(results[1].biochar_dry - 397)  <= 1.0
        assert abs(results[2].biochar_dry - 445)  <= 1.0
        assert abs(results[0].syngas - 1682) <= 1.0
        assert abs(results[1].syngas - 2103) <= 1.0
        assert abs(results[2].syngas - 2355) <= 1.0

    def test_yield_constant_across_feed_rates(self):
        """Yield fraction must be identical regardless of feed rate."""
        results = calculate_scenarios(
            feed_rates     = [1000, 2000, 5000],
            moisture_ar    = 10.13,
            ash_dry        = 6.843,
            ash_biochar_ar = 38.68,
        )
        yields = [r.biochar_yield_dry for r in results]
        assert max(yields) - min(yields) < 0.0001, \
            "Yield should be constant across feed rates"

    def test_scenario_names_assigned(self):
        """Default scenario names should be assigned automatically."""
        results = calculate_scenarios(
            feed_rates  = [2000, 2500],
            moisture_ar = 10.13,
            ash_dry     = 6.843,
        )
        assert results[0].scenario_name == "2000 kg/h"
        assert results[1].scenario_name == "2500 kg/h"