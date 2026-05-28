"""
api/main.py
===========
FastAPI wrapper around the Decarbo Pyrolysis Engine.

Endpoints:
  POST /api/calculate        -- full system integration (all 6 modules)
  POST /api/feedstock        -- Module 1 only (feedstock characterisation)
  POST /api/mass_balance     -- Modules 1+2 (feedstock + mass balance)
  POST /api/heat_transfer    -- Module 4 only (reactor heat transfer)
  POST /api/combustion       -- Module 5 only (combustion chamber analysis)
  GET  /api/steel_grades     -- return steel grade database
  GET  /api/feedstock_library -- return feedstock library
  GET  /health               -- health check

Run locally:
  uvicorn api.main:app --reload --port 8000

Access at:
  http://localhost:8000
  http://localhost:8000/docs  (auto-generated API docs)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import traceback

from engine.feedstock import (
    FeedstockInput, analyse as feedstock_analyse, from_library
)
from engine.mass_balance import (
    MassBalanceInput, calculate as mb_calculate, calculate_scenarios as mb_scenarios
)
from engine.energy_balance import (
    EnergyBalanceInput, calculate as eb_calculate,
    air_flow_from_sensible_heat
)
from engine.heat_transfer import (
    ReactorGeometry, HeatTransferInput,
    calculate as ht_calculate, feed_rate_sweep
)
from engine.combustion import (
    ChamberGeometry, CombustionConfig, SyngasComposition,
    calculate_dual, calculate_envelope, rbu_default, pcc_default
)
from engine.integration import (
    SystemInput, calculate as sys_calculate,
    calculate_scenarios as sys_scenarios, co2_sequestered
)
from engine.constants import STEEL_GRADES, FEEDSTOCK_LIBRARY, EU_WID, EBC


# ---------------------------------------------------------------------------
# APP SETUP
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Decarbo Pyrolysis Engine API",
    description="Mass/energy balance, heat transfer, and combustion analysis for pyrolysis plants",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # restrict to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REQUEST MODELS (Pydantic)
# ---------------------------------------------------------------------------

class FeedstockParams(BaseModel):
    """Feedstock laboratory analysis data."""
    name: str = "BR-01"
    C_dry: float = Field(35.17, description="Carbon, dry basis [%wt]")
    H_dry: float = Field(6.05,  description="Hydrogen, dry basis [%wt]")
    N_dry: float = Field(0.98,  description="Nitrogen, dry basis [%wt]")
    O_dry: float = Field(50.55, description="Oxygen, dry basis [%wt]")
    S_dry: float = Field(0.431, description="Sulphur, dry basis [%wt]")
    Cl_dry: float = Field(0.05, description="Chlorine, dry basis [%wt] — default if not measured")
    moisture_ar: float = Field(10.13, description="Moisture, as-received [%wt]")
    ash_ar: float = Field(6.15,  description="Ash, as-received [%wt]")
    HHV_dry_kcal: Optional[float] = Field(3890.42, description="HHV dry from lab [kCal/kg]")
    HHV_dry_kJ: Optional[float] = Field(None, description="HHV dry from lab [kJ/kg] — use instead of kCal if available")
    library_key: Optional[str] = Field(None, description="Use a feedstock from the library instead of entering data")


class ReactorParams(BaseModel):
    """Rotary kiln geometry and operating conditions."""
    diameter_outer: float = Field(2.4,   description="Outer drum diameter [m]")
    length_heated: float  = Field(6.0,   description="Heated length [m]")
    wall_thickness: float = Field(0.012, description="Shell wall thickness [m]")
    steel_grade: str      = Field("SS304", description="Steel grade key from /api/steel_grades")
    T_combustion_gas: float = Field(900.0, description="Combustion gas temperature OUTSIDE drum [°C]")
    T_pyrolysis: float    = Field(600.0,  description="Target pyrolysis temperature INSIDE drum [°C]")
    h_combustion_conv: float = Field(50.0, description="Convective HTC combustion side [W/m²K]")
    h_pyrolysis_conv: float  = Field(35.0, description="Convective HTC pyrolysis side, CONVECTION ONLY [W/m²K]")


class ChamberParams(BaseModel):
    """Combustion chamber geometry."""
    is_cylindrical: bool = Field(False, description="True for RBu (cylindrical), False for PCC (rectangular)")
    length_ext: float = Field(0.0,   description="External length [m]")
    width_ext: float  = Field(0.0,   description="External width [m] — rectangular only")
    height_ext: float = Field(0.0,   description="External height [m] — rectangular only")
    diameter_ext: float = Field(0.0, description="External diameter [m] — cylindrical only")
    refractory_thickness: float = Field(0.10, description="Refractory lining thickness [m]")
    name: str = Field("Chamber", description="Label for reporting")


class CombustionParams(BaseModel):
    """Combustion system configuration."""
    dual_chamber: bool = Field(True,  description="True = RBu + PCC, False = single chamber")
    rbu: Optional[ChamberParams] = None
    pcc: Optional[ChamberParams] = None
    single_chamber: Optional[ChamberParams] = None
    T_rbu: float = Field(950.0, description="RBu operating temperature [°C]")
    T_pcc: float = Field(900.0, description="PCC operating temperature [°C]")
    excess_air_rbu: float = Field(1.30, description="Excess air factor RBu (1.3 = 30% excess)")
    excess_air_pcc: float = Field(1.20, description="Excess air factor PCC")
    syngas_split_rbu: float = Field(0.40, description="Fraction of syngas to RBu [0-1]")
    rbu_requires_eu_wid: bool = Field(False, description="Apply EU WID to RBu? Usually False (process heater).")


class SyngasParams(BaseModel):
    """Syngas composition weight fractions."""
    NCG_wt: float  = Field(0.543, description="Non-condensable gas fraction")
    tars_wt: float = Field(0.190, description="Tars / condensable fraction")
    H2O_wt: float  = Field(0.268, description="Moisture fraction")


class FullCalculationRequest(BaseModel):
    """Complete plant calculation request."""
    project_name: str = Field("Pyrolysis Plant", description="Project label")
    scenario_name: str = Field("", description="Scenario label")
    feed_rate_ar: float = Field(2000.0, description="Feed rate as-received [kg/h]")
    feedstock: FeedstockParams = FeedstockParams()
    reactor: ReactorParams = ReactorParams()
    combustion: CombustionParams = CombustionParams()
    syngas: SyngasParams = SyngasParams()
    biochar_ash_ar: float = Field(38.68, description="Biochar ash content a.r. [%] — from Eurofins or default")
    biochar_C_organic: float = Field(54.1, description="Biochar organic carbon [% dry]")
    biochar_H_C: float = Field(0.26,  description="Biochar H/C molar ratio")
    operating_hours_yr: float = Field(8000.0, description="Annual operating hours")
    air_sensible_kW: float = Field(157.0, description="Combustion air sensible heat [kW] — from HSC or measurement")
    flue_gas_loss_kW: float = Field(5909.0, description="Flue gas heat loss [kW] — from HSC or measurement")
    biochar_latent_kW: float = Field(4.0, description="Biochar latent heat [kW]")


class SweepRequest(BaseModel):
    """Feed rate sweep request — run calculation at multiple feed rates."""
    feed_rates: list = Field([1000, 1500, 2000, 2500, 2800, 3000], description="Feed rates to evaluate [kg/h ar]")
    feedstock: FeedstockParams = FeedstockParams()
    reactor: ReactorParams = ReactorParams()
    combustion: CombustionParams = CombustionParams()
    syngas: SyngasParams = SyngasParams()
    biochar_ash_ar: float = 38.68
    biochar_C_organic: float = 54.1
    biochar_H_C: float = 0.26
    operating_hours_yr: float = 8000.0


class HeatTransferRequest(BaseModel):
    """Module 4 only — heat transfer analysis at a single operating point."""
    feed_rate_ar: float = Field(2000.0)
    moisture_ar: float = Field(10.13)
    reactor: ReactorParams = ReactorParams()
    feedstock_type: str = Field("sugar_cane")


class HeatTransferSweepRequest(BaseModel):
    """Module 4 — heat transfer sweep across feed rates."""
    feed_rates: list = Field([500, 1000, 1500, 2000, 2500, 2800, 3000, 3500])
    moisture_ar: float = Field(10.13)
    reactor: ReactorParams = ReactorParams()


# ---------------------------------------------------------------------------
# HELPER: convert request models to engine inputs
# ---------------------------------------------------------------------------

def build_feedstock_input(p: FeedstockParams) -> FeedstockInput:
    if p.library_key:
        return from_library(p.library_key)
    return FeedstockInput(
        name         = p.name,
        C_dry        = p.C_dry,
        H_dry        = p.H_dry,
        N_dry        = p.N_dry,
        O_dry        = p.O_dry,
        S_dry        = p.S_dry,
        Cl_dry       = p.Cl_dry,
        moisture_ar  = p.moisture_ar,
        ash_ar       = p.ash_ar,
        HHV_dry_kcal = p.HHV_dry_kcal,
        HHV_dry_kJ   = p.HHV_dry_kJ,
    )


def build_reactor_geometry(p: ReactorParams) -> ReactorGeometry:
    return ReactorGeometry(
        diameter_outer = p.diameter_outer,
        length_heated  = p.length_heated,
        wall_thickness = p.wall_thickness,
        steel_grade    = p.steel_grade,
    )


def build_chamber(p: ChamberParams) -> ChamberGeometry:
    return ChamberGeometry(
        is_cylindrical       = p.is_cylindrical,
        length_ext           = p.length_ext,
        width_ext            = p.width_ext,
        height_ext           = p.height_ext,
        diameter_ext         = p.diameter_ext,
        refractory_thickness = p.refractory_thickness,
        name                 = p.name,
    )


def build_combustion_config(p: CombustionParams) -> CombustionConfig:
    rbu = build_chamber(p.rbu) if p.rbu else rbu_default()
    pcc = build_chamber(p.pcc) if p.pcc else pcc_default()
    single = build_chamber(p.single_chamber) if p.single_chamber else pcc_default()
    return CombustionConfig(
        dual_chamber         = p.dual_chamber,
        rbu                  = rbu,
        pcc                  = pcc,
        single_chamber       = single,
        T_rbu                = p.T_rbu,
        T_pcc                = p.T_pcc,
        excess_air_rbu       = p.excess_air_rbu,
        excess_air_pcc       = p.excess_air_pcc,
        split_min            = max(0.05, p.syngas_split_rbu - 0.25),
        split_max            = min(0.95, p.syngas_split_rbu + 0.25),
        rbu_requires_eu_wid  = p.rbu_requires_eu_wid,
    )


def build_system_input(req: FullCalculationRequest) -> SystemInput:
    return SystemInput(
        project_name          = req.project_name,
        scenario_name         = req.scenario_name,
        feedstock             = build_feedstock_input(req.feedstock),
        feed_rate_ar          = req.feed_rate_ar,
        biochar_C_organic_pct = req.biochar_C_organic,
        biochar_H_C_molar     = req.biochar_H_C,
        biochar_ash_ar        = req.biochar_ash_ar,
        operating_hours_yr    = req.operating_hours_yr,
        reactor               = build_reactor_geometry(req.reactor),
        combustion            = build_combustion_config(req.combustion),
        syngas_composition    = SyngasComposition(
            NCG_wt  = req.syngas.NCG_wt,
            tars_wt = req.syngas.tars_wt,
            H2O_wt  = req.syngas.H2O_wt,
        ),
        air_sensible_kW    = req.air_sensible_kW,
        flue_gas_loss_kW   = req.flue_gas_loss_kW,
        biochar_latent_kW  = req.biochar_latent_kW,
        T_combustion_gas   = req.reactor.T_combustion_gas,
    )


def serialise_result(result) -> dict:
    """Recursively convert a dataclass result to a JSON-safe dict."""
    import dataclasses
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        out = {}
        for f in dataclasses.fields(result):
            val = getattr(result, f.name)
            out[f.name] = serialise_result(val)
        return out
    elif isinstance(result, list):
        return [serialise_result(i) for i in result]
    elif isinstance(result, dict):
        return {k: serialise_result(v) for k, v in result.items()}
    elif isinstance(result, float):
        if result != result:  # NaN
            return None
        if result == float("inf") or result == float("-inf"):
            return None
        return round(result, 4)
    else:
        return result


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Health check — confirms the engine is running."""
    return {"status": "ok", "engine": "Decarbo Pyrolysis Engine v1.0"}


@app.get("/api/steel_grades")
def get_steel_grades():
    """Return the complete steel grade database with thermal properties."""
    return {
        grade: {
            "description":          data["description"],
            "thermal_conductivity": data["thermal_conductivity"],
            "max_service_temp":     data["max_service_temp"],
            "note":                 data["note"],
        }
        for grade, data in STEEL_GRADES.items()
    }


@app.get("/api/feedstock_library")
def get_feedstock_library():
    """Return the built-in feedstock reference library (ECN Phyllis data)."""
    return FEEDSTOCK_LIBRARY


@app.get("/api/constants")
def get_constants():
    """Return key regulatory limits and EBC standards."""
    return {
        "EU_WID":   EU_WID,
        "EBC":      EBC,
    }


@app.post("/api/feedstock")
def run_feedstock(params: FeedstockParams):
    """
    Module 1 — feedstock characterisation only.
    Returns HHV/LHV on all bases, daf composition, consistency check.
    """
    try:
        feedstock = build_feedstock_input(params)
        result    = feedstock_analyse(feedstock)
        return {
            "status": "ok",
            "result": serialise_result(result),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/heat_transfer")
def run_heat_transfer(req: HeatTransferRequest):
    """
    Module 4 — reactor heat transfer at one operating point.
    Iterative radiation model. Returns U, Q_delivered, Q_required,
    thermal margin, wall temperatures, max feed rate.
    """
    try:
        geo = build_reactor_geometry(req.reactor)
        inp = HeatTransferInput(
            T_combustion_gas  = req.reactor.T_combustion_gas,
            T_pyrolysis       = req.reactor.T_pyrolysis,
            T_feed            = 35.0,
            feed_rate_ar      = req.feed_rate_ar,
            moisture_ar       = req.moisture_ar,
            h_combustion_conv = req.reactor.h_combustion_conv,
            h_pyrolysis       = req.reactor.h_pyrolysis_conv,
            feedstock_type    = req.feedstock_type,
            geometry          = geo,
        )
        result = ht_calculate(inp)
        return {
            "status": "ok",
            "result": serialise_result(result),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/heat_transfer/sweep")
def run_heat_transfer_sweep(req: HeatTransferSweepRequest):
    """
    Module 4 sweep — heat transfer across a range of feed rates.
    Q_delivered is constant (fixed by geometry); Q_required rises linearly.
    Returns thermal limit as the crossover point.
    """
    try:
        geo     = build_reactor_geometry(req.reactor)
        results = feed_rate_sweep(
            geometry         = geo,
            T_combustion_gas = req.reactor.T_combustion_gas,
            T_pyrolysis      = req.reactor.T_pyrolysis,
            moisture_ar      = req.moisture_ar,
            feed_rates       = req.feed_rates,
            h_combustion_conv = req.reactor.h_combustion_conv,
            h_pyrolysis      = req.reactor.h_pyrolysis_conv,
        )
        thermal_limit = None
        for r in results:
            if not r.can_sustain_pyrolysis:
                thermal_limit = r.feed_rate_ar
                break
        return {
            "status":        "ok",
            "thermal_limit": thermal_limit,
            "results":       [serialise_result(r) for r in results],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calculate")
def run_full_calculation(req: FullCalculationRequest):
    """
    Full system integration — all 6 modules in sequence.
    Returns complete plant analysis: feedstock, mass balance,
    energy balance, heat transfer, combustion, CO2 sequestration.
    """
    try:
        sys_input = build_system_input(req)
        result    = sys_calculate(sys_input)

        return {
            "status":       "ok",
            "system_status": result.system_status,
            "fully_feasible": result.fully_feasible,
            "warnings":      result.all_warnings,

            "feedstock": {
                "HHV_dry_kJ":    result.feedstock.HHV_dry,
                "LHV_ar_kJ":     result.feedstock.LHV_ar,
                "ash_dry_pct":   round(result.feedstock.ash_dry_pct, 3),
                "consistent":    result.feedstock.composition_consistent,
                "warnings":      result.feedstock.warnings,
            },

            "mass_balance": {
                "feed_ar":              result.mass_balance.feed_ar,
                "feed_dry":             round(result.mass_balance.feed_dry, 1),
                "biochar_dry":          round(result.mass_balance.biochar_dry, 1),
                "biochar_yield_pct":    round(result.mass_balance.biochar_yield_dry_pct, 2),
                "syngas":               round(result.mass_balance.syngas, 1),
                "NCG":                  round(result.mass_balance.NCG, 1),
                "tars":                 round(result.mass_balance.tars, 1),
                "H2O_syngas":           round(result.mass_balance.H2O_syngas, 1),
            },

            "heat_transfer": {
                "U_overall":            round(result.heat_transfer.U_overall, 1),
                "h_rad_outside":        round(result.heat_transfer.h_rad_outside, 1),
                "h_rad_inside":         round(result.heat_transfer.h_rad_inside, 1),
                "h_pyrolysis_eff":      round(result.heat_transfer.h_pyrolysis_eff, 1),
                "T_wall_outer":         round(result.heat_transfer.T_wall_outer, 1),
                "T_wall_inner":         round(result.heat_transfer.T_wall_inner, 1),
                "Q_delivered_kW":       round(result.heat_transfer.Q_delivered_kW, 1),
                "Q_required_kW":        round(result.heat_transfer.Q_required_kW, 1),
                "thermal_margin_pct":   round(result.heat_transfer.thermal_margin_pct, 1),
                "can_sustain":          result.heat_transfer.can_sustain_pyrolysis,
                "max_feed_rate_ar":     round(result.heat_transfer.max_feed_rate_ar, 0),
                "steel_temp_warning":   result.heat_transfer.steel_temp_warning,
            },

            "combustion": {
                "recommended_split":    result.recommended_split,
                "split_min_valid":      result.split_min_valid,
                "split_max_valid":      result.split_max_valid,
                "rbu_residence_time_s": round(result.rbu_residence_time, 3),
                "pcc_residence_time_s": round(result.pcc_residence_time, 3),
                "pcc_eu_wid_compliant": result.pcc_residence_time >= 2.0,
                "rbu_air_kg_h":         round(result.rbu_air_kg_h, 0),
                "pcc_air_kg_h":         round(result.pcc_air_kg_h, 0),
                "total_air_kg_h":       round(result.total_air_kg_h, 0),
            },

            "sequestration": {
                "CO2_t_yr":             round(result.CO2_t_yr, 0),
                "CO2_kg_h":             round(result.sequestration.get("CO2_equivalent_kg_h", 0), 1),
                "C_sequestered_kg_h":   round(result.sequestration.get("C_sequestered_kg_h", 0), 1),
                "permanence_factor":    result.sequestration.get("permanence_factor", 0),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "error":     str(e),
            "traceback": traceback.format_exc(),
        })


@app.post("/api/calculate/sweep")
def run_sweep(req: SweepRequest):
    """
    Full system sweep — run complete calculation at multiple feed rates.
    Returns operating envelope: feasibility, split range, CO2, at each point.
    """
    try:
        base = SystemInput(
            project_name          = "Sweep",
            feedstock             = build_feedstock_input(req.feedstock),
            feed_rate_ar          = req.feed_rates[0],
            biochar_C_organic_pct = req.biochar_C_organic,
            biochar_H_C_molar     = req.biochar_H_C,
            biochar_ash_ar        = req.biochar_ash_ar,
            operating_hours_yr    = req.operating_hours_yr,
            reactor               = build_reactor_geometry(req.reactor),
            combustion            = build_combustion_config(req.combustion),
            syngas_composition    = SyngasComposition(
                NCG_wt  = req.syngas.NCG_wt,
                tars_wt = req.syngas.tars_wt,
                H2O_wt  = req.syngas.H2O_wt,
            ),
        )
        results = sys_scenarios(base, req.feed_rates)

        envelope = []
        for r in results:
            envelope.append({
                "feed_rate_ar":         r.feed_rate_ar,
                "system_status":        r.system_status,
                "fully_feasible":       r.fully_feasible,
                "thermal_margin_pct":   round(r.heat_transfer.thermal_margin_pct, 1),
                "max_feed_rate_ar":     round(r.heat_transfer.max_feed_rate_ar, 0),
                "pcc_residence_time_s": round(r.pcc_residence_time, 2),
                "recommended_split":    r.recommended_split,
                "total_air_kg_h":       round(r.total_air_kg_h, 0),
                "CO2_t_yr":             round(r.CO2_t_yr, 0),
                "biochar_dry_kg_h":     round(r.mass_balance.biochar_dry, 1),
            })

        return {
            "status":   "ok",
            "envelope": envelope,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))