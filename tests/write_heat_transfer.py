content = '''\
import math
from dataclasses import dataclass, field
from engine.constants import (
    STEEL_GRADES, HTC, PYROLYSIS_ENTHALPY,
    STEFAN_BOLTZMANN, EMISSIVITY_BARE_STEEL,
    LATENT_HEAT_WATER_100C, CP_BIOMASS_WET, T_REF_K,
)

# Maximum iterations for T_wall_inner convergence
MAX_ITERATIONS = 20
CONVERGENCE_TOL = 0.1   # degrees C


@dataclass
class ReactorGeometry:
    """
    Physical dimensions of the rotary kiln reactor.
    All dimensions in metres.

    Operating plant (1000 kg/h, validated):
      diameter_outer = 2.4 m
      length_heated  = 6.0 m
      wall_thickness = 0.012 m  (12mm)
      steel_grade    = SS304
      Heat transfer area A = pi x 2.4 x 6.0 = 45.24 m2

    Inner tube (double-pass kiln, informational only):
      diameter_inner = 1.4 m
      Pre-heats biomass on first pass -- not primary HX surface
    """
    diameter_outer: float = 2.4
    length_heated:  float = 6.0
    wall_thickness: float = 0.012
    steel_grade:    str   = "SS304"
    diameter_inner: float = 1.4
    reactor_type:   str   = "rotary_kiln_double_pass"

    @property
    def heat_transfer_area(self):
        """Primary HX surface area [m2] = pi x D_outer x L_heated."""
        return math.pi * self.diameter_outer * self.length_heated

    @property
    def thermal_conductivity(self):
        """Thermal conductivity of shell material [W/m*K]."""
        if self.steel_grade not in STEEL_GRADES:
            raise ValueError(
                f"Steel grade {self.steel_grade!r} not in database. "
                f"Available: {list(STEEL_GRADES.keys())}"
            )
        return STEEL_GRADES[self.steel_grade]["thermal_conductivity"]

    @property
    def max_service_temp(self):
        """Maximum continuous service temperature [degrees C]."""
        return STEEL_GRADES[self.steel_grade]["max_service_temp"]


@dataclass
class HeatTransferInput:
    """
    Operating conditions for one heat transfer calculation.

    Key temperatures:
      T_combustion_gas: Temperature of hot combustion gas OUTSIDE the drum.
                        This is NOT the PLC temperature inside the reactor.
                        PLC reads pyrolysis zone temperature (T_pyrolysis).
                        Typical: 850-950 degrees C for RBu operating conditions.

      T_pyrolysis:      Target temperature of pyrolysis zone INSIDE drum.
                        This IS the PLC temperature in the carbonising zone.
                        Typical: 550-650 degrees C.

    Heat transfer coefficients:
      h_combustion_conv: Convective HTC on combustion gas side [W/m2*K].
                         Radiation is calculated automatically.
                         Default 50 W/m2*K (typical forced convection).

      h_pyrolysis_conv:  Convective HTC on pyrolysis bed side [W/m2*K].
                         This is CONVECTION ONLY -- radiation added automatically.
                         Default 35 W/m2*K (tumbling bed, typical rotary kiln).
                         Do NOT pre-add radiation here -- module does it internally.
    """
    T_combustion_gas:   float  = 900.0
    T_pyrolysis:        float  = 600.0
    T_feed:             float  = 35.0
    T_ref:              float  = 0.0
    feed_rate_ar:       float  = 1000.0
    moisture_ar:        float  = 10.13
    ash_dry:            float  = 6.843
    feedstock_type:     str    = "sugar_cane"
    h_combustion_conv:  float  = 50.0
    h_pyrolysis_conv:   float  = 35.0    # convection only -- radiation added by module
    emissivity:         float  = EMISSIVITY_BARE_STEEL
    geometry:           object = None
    scenario_name:      str    = ""

    def __post_init__(self):
        if self.geometry is None:
            self.geometry = ReactorGeometry()


@dataclass
class HeatTransferResult:
    """
    Complete heat transfer calculation result.
    Includes iterative convergence information.
    """
    # Geometry
    heat_transfer_area_m2:  float = 0.0
    wall_thickness_m:       float = 0.0
    steel_grade:            str   = ""
    thermal_conductivity:   float = 0.0

    # Heat transfer coefficients -- combustion side [W/m2*K]
    h_rad_outside:          float = 0.0   # radiation: combustion gas -> outer wall
    h_combustion_conv:      float = 0.0   # convection: combustion gas -> outer wall
    h_combustion_total:     float = 0.0   # total combustion side = conv + rad

    # Heat transfer coefficients -- pyrolysis side [W/m2*K]
    h_pyrolysis_conv:       float = 0.0   # convection only (input)
    h_rad_inside:           float = 0.0   # radiation: inner wall -> biomass bed
    h_pyrolysis_eff:        float = 0.0   # effective = conv + rad_inside

    # Wall thermal resistance
    R_wall:                 float = 0.0   # t / lambda [m2*K/W]
    U_overall:              float = 0.0   # overall HTC [W/m2*K]

    # Temperatures
    T_combustion_gas:       float = 0.0
    T_pyrolysis:            float = 0.0
    delta_T:                float = 0.0
    T_wall_outer:           float = 0.0   # outer drum surface temperature
    T_wall_inner:           float = 0.0   # inner drum surface temperature
    iterations_to_converge: int   = 0

    # Heat delivered [kW]
    Q_delivered_kW:         float = 0.0

    # Heat required [kW]
    Q_sensible_kW:          float = 0.0
    Q_moisture_kW:          float = 0.0
    Q_reaction_kW:          float = 0.0
    Q_required_kW:          float = 0.0

    # Balance
    Q_surplus_kW:           float = 0.0
    thermal_margin_pct:     float = 0.0
    can_sustain_pyrolysis:  bool  = False
    max_feed_rate_ar:       float = 0.0

    # Steel check
    steel_temp_warning:     bool  = False

    warnings: list = field(default_factory=list)
    scenario_name: str = ""


# ---------------------------------------------------------------------------
# HEAT TRANSFER COEFFICIENT FUNCTIONS
# ---------------------------------------------------------------------------

def radiative_htc(T_hot, T_cold, emissivity=EMISSIVITY_BARE_STEEL):
    """
    Effective radiative heat transfer coefficient [W/m2*K].

    Radiation is dominant at pyrolysis temperatures (>600 degrees C).
    At 900 degrees C combustion side, h_rad ~ 280-300 W/m2*K.
    At 800 degrees C inner wall vs 600 degrees C bed, h_rad ~ 150-180 W/m2*K.

    h_rad = sigma * epsilon * (T_hot^4 - T_cold^4) / (T_hot - T_cold)

    Args:
        T_hot:      Hot surface temperature [degrees C]
        T_cold:     Cold surface temperature [degrees C]
        emissivity: Surface emissivity [-]

    Returns:
        Effective radiative HTC [W/m2*K]
    """
    T_hot_K  = T_hot  + T_REF_K
    T_cold_K = T_cold + T_REF_K
    if abs(T_hot_K - T_cold_K) < 0.5:
        return 0.0
    q_rad = STEFAN_BOLTZMANN * emissivity * (T_hot_K**4 - T_cold_K**4)
    return q_rad / (T_hot_K - T_cold_K)


def overall_htc(h_combustion_conv, h_rad_outside, wall_thickness,
                thermal_conductivity, h_pyrolysis_eff):
    """
    Overall heat transfer coefficient U [W/m2*K].

    Three resistances in series:
      R_combustion = 1 / (h_conv_outside + h_rad_outside)
      R_wall       = wall_thickness / thermal_conductivity
      R_pyrolysis  = 1 / h_pyrolysis_eff  (conv + rad_inside)

    1/U = R_combustion + R_wall + R_pyrolysis

    Note on SS304 vs carbon steel:
      SS304:       R_wall = 0.012/16    = 0.00075 m2*K/W  (~9% of total R)
      Carbon steel: R_wall = 0.012/50   = 0.00024 m2*K/W  (~3% of total R)
      Difference is small -- wall is NOT the limiting resistance.
      Pyrolysis-side (R = 0.004-0.006) is the dominant resistance.

    Returns:
        Tuple: (U [W/m2*K], R_wall [m2*K/W], h_combustion_total [W/m2*K])
    """
    h_comb_total = h_combustion_conv + h_rad_outside
    R_combustion = 1.0 / h_comb_total if h_comb_total > 0 else float("inf")
    R_wall       = wall_thickness / thermal_conductivity
    R_pyrolysis  = 1.0 / h_pyrolysis_eff if h_pyrolysis_eff > 0 else float("inf")
    R_total      = R_combustion + R_wall + R_pyrolysis
    U = 1.0 / R_total
    return U, R_wall, h_comb_total


def wall_temperatures(T_combustion, T_pyrolysis, h_combustion_total,
                      h_pyrolysis_eff, U_overall):
    """
    Estimate outer and inner drum wall surface temperatures.

    Temperature drops proportionally across each resistance:
      T_wall_outer = T_combustion - Q_flux / h_combustion_total
      T_wall_inner = T_pyrolysis  + Q_flux / h_pyrolysis_eff
    where Q_flux = U * delta_T [W/m2]

    Args:
        T_combustion:      Combustion gas temperature [degrees C]
        T_pyrolysis:       Pyrolysis zone temperature [degrees C]
        h_combustion_total: Total combustion-side HTC [W/m2*K]
        h_pyrolysis_eff:   Effective pyrolysis-side HTC [W/m2*K]
        U_overall:         Overall HTC [W/m2*K]

    Returns:
        Tuple: (T_wall_outer [degrees C], T_wall_inner [degrees C])
    """
    Q_flux       = U_overall * (T_combustion - T_pyrolysis)
    T_wall_outer = T_combustion - Q_flux / h_combustion_total
    T_wall_inner = T_pyrolysis  + Q_flux / h_pyrolysis_eff
    return T_wall_outer, T_wall_inner


# ---------------------------------------------------------------------------
# HEAT REQUIRED
# ---------------------------------------------------------------------------

def heat_required(feed_rate_ar, moisture_ar, T_pyrolysis, T_feed,
                  feedstock_type="sugar_cane", T_ref=0.0):
    """
    Total heat demand for pyrolysis [kW]. Three components:

    1. Sensible heat:    raise dry feed from T_feed to T_pyrolysis
    2. Moisture evap:    heat moisture from T_feed to 100C, then evaporate
    3. Reaction:         endothermic pyrolysis decomposition

    Args:
        feed_rate_ar:   Feed rate as-received [kg/h]
        moisture_ar:    Moisture content [% ar]
        T_pyrolysis:    Target pyrolysis temperature [degrees C]
        T_feed:         Feed inlet temperature [degrees C]
        feedstock_type: Key for PYROLYSIS_ENTHALPY lookup

    Returns:
        Tuple: (Q_sensible, Q_moisture, Q_reaction, Q_total) all [kW]
    """
    feed_dry = feed_rate_ar * (1.0 - moisture_ar / 100.0)
    moisture  = feed_rate_ar * moisture_ar / 100.0

    Q_sensible = (feed_dry / 3600.0) * CP_BIOMASS_WET * (T_pyrolysis - T_feed)
    Q_moisture = (moisture / 3600.0) * (
        4.18 * (100.0 - T_feed) + LATENT_HEAT_WATER_100C
    )
    dH = PYROLYSIS_ENTHALPY.get(feedstock_type, PYROLYSIS_ENTHALPY["default"])
    Q_reaction = (feed_dry / 3600.0) * dH
    Q_total    = Q_sensible + Q_moisture + Q_reaction

    return Q_sensible, Q_moisture, Q_reaction, Q_total


def max_feed_rate(Q_delivered_kW, moisture_ar, T_pyrolysis, T_feed,
                  feedstock_type="sugar_cane"):
    """
    Maximum sustainable feed rate where Q_delivered = Q_required.
    Q_required scales linearly with feed rate:
      feed_rate_max = 1000 * (Q_delivered / Q_required_at_1000)
    """
    _, _, _, Q_ref = heat_required(
        1000.0, moisture_ar, T_pyrolysis, T_feed, feedstock_type
    )
    if Q_ref <= 0:
        return 0.0
    return 1000.0 * (Q_delivered_kW / Q_ref)


# ---------------------------------------------------------------------------
# MAIN ITERATIVE CALCULATION
# ---------------------------------------------------------------------------

def calculate(inputs):
    """
    Run iterative reactor heat transfer analysis.

    The calculation is iterative because:
      h_rad_inside depends on T_wall_inner
      T_wall_inner depends on U
      U depends on h_rad_inside

    Convergence is typically achieved in 4-6 iterations.

    Physics summary:
      - Combustion side: convection (~50) + radiation (~280-300) = ~330-350 W/m2*K
      - Wall (SS304):    conduction: 0.012/16 = 0.00075 m2*K/W (small resistance)
      - Pyrolysis side:  convection (~35) + radiation inside drum (~150-200) = ~185-235 W/m2*K
      - U overall:       ~80-120 W/m2*K (much higher than original 29.6 W/m2*K)
      - Q_delivered:     ~1,100-1,500 kW (vs incorrect 400 kW originally)
      - Max feed rate:   ~2,800 kg/h (reproduces Lode thermal limit)

    Args:
        inputs: HeatTransferInput

    Returns:
        HeatTransferResult
    """
    result   = HeatTransferResult()
    warnings = []
    result.scenario_name        = inputs.scenario_name
    geo                         = inputs.geometry