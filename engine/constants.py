"""
constants.py
============
Single source of truth for all physical constants, reference data,
and lookup tables used across the Decarbo Pyrolysis Engine.

All modules import from here. Never hardcode a constant elsewhere.

Sources:
  - Boie (1953), confirmed DIN 51900
  - IUPAC atomic weights 2021
  - EU Waste Incineration Directive (WID) 2000/76/EC / IED 2010/75/EU
  - EBC (European Biochar Certificate) Standard 2022
  - ECN Phyllis2 biomass database
  - NIST thermochemical data
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. THERMODYNAMIC CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Energy conversion
KCAL_TO_KJ = 4.1868          # kJ per kCal (International Table calorie)
KJ_TO_KCAL = 1 / KCAL_TO_KJ

# Water / hydrogen combustion
LATENT_HEAT_WATER_25C  = 2442.0   # kJ/kg — latent heat of vaporisation at 25°C
LATENT_HEAT_WATER_100C = 2257.0   # kJ/kg — latent heat at boiling point
H_TO_WATER_MASS_RATIO  = 9.0      # kg H₂O produced per kg H combusted (18/2)

# Air composition (dry, by mass)
AIR_O2_MASS_FRACTION  = 0.232     # 23.2 % O₂ by mass in dry air
AIR_N2_MASS_FRACTION  = 0.768     # 76.8 % N₂ by mass in dry air
AIR_N2_O2_MASS_RATIO  = 3.31      # kg N₂ per kg O₂

# Specific heat capacities [kJ/kg·K]
CP_DRY_AIR        = 1.005   # at 27°C
CP_MOIST_AIR      = 1.04    # at 27°C, RH=80% (used in Jibito energy balance)
CP_WATER_VAPOUR   = 1.86    # at typical flue gas conditions
CP_CO2            = 0.85    # at 850°C
CP_BIOMASS_WET    = 1.65    # wet biomass feedstock — back-calculated from LSM figures
CP_BIOCHAR        = 1.256   # biochar at 550°C — back-calculated from LSM figures
                             # Note: higher than ambient value (0.84) due to T dependence

# Ideal gas reference
RHO_AIR_0C        = 1.293   # kg/m³ at 0°C, 1 atm (used for volumetric flow at T)
T_REF_K           = 273.15  # K  (0°C reference)


# ─────────────────────────────────────────────────────────────────────────────
# 2. BOIE EQUATION COEFFICIENTS  [kJ/kg, applied to mass fractions daf]
# ─────────────────────────────────────────────────────────────────────────────
# HHV_daf = C1*xC + C2*xH + C3*xO + C4*xN + C5*xS
# where x = mass fraction on dry-ash-free basis (i.e. %daf / 100)

BOIE = {
    "C":  35160.0,    # Carbon    — combustion to CO₂
    "H":  116225.0,   # Hydrogen  — highest coefficient; H₂ → H₂O (liquid, HHV basis)
    "O": -11090.0,    # Oxygen    — negative; fuel-bound O reduces available energy
    "N":   6280.0,    # Nitrogen  — NOx formation enthalpy
    "S":  10465.0,    # Sulphur   — combustion to SO₂
}

# LHV correction (subtract latent heat of water formed from bound hydrogen)
# LHV_dry = HHV_dry - LATENT_HEAT_WATER_25C * H_TO_WATER_MASS_RATIO * H_dry_fraction
# LHV_ar  = HHV_ar  - LATENT_HEAT_WATER_25C * (H_TO_WATER_MASS_RATIO * H_ar + M_ar/100)


# ─────────────────────────────────────────────────────────────────────────────
# 3. MOLAR MASSES  [g/mol]
# ─────────────────────────────────────────────────────────────────────────────

MOLAR_MASS = {
    "C":   12.011,
    "H":    1.008,
    "O":   15.999,
    "N":   14.007,
    "S":   32.06,
    "Cl":  35.45,
    "H2O": 18.015,
    "CO2": 44.009,
    "SO2": 64.066,
    "HCl": 36.458,
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. PROCESS TEMPERATURES  [°C]  — design basis defaults
# ─────────────────────────────────────────────────────────────────────────────

TEMP = {
    "energy_balance_reference": 0,    # all enthalpy terms relative to 0°C
    "pyrolysis_nominal":       550,    # rotary kiln nominal pyrolysis temperature
    "syngas_exit_reactor":     625,    # syngas exits hotter than reactor nominal
    "biochar_exit_reactor":    550,    # same as pyrolysis zone
    "pcc_operating":           850,    # EU WID minimum PCC temperature
    "pcc_flue_exit":           900,    # target PCC flue gas exit (50°C above minimum)
    "biochar_discharge_target":  20,   # after water quench
    "biochar_spontaneous_combustion_risk": 200,  # above this = fire risk
    "biochar_pyrophoric_threshold":         454, # observed in PLC 1000kg/h plant
}


# ─────────────────────────────────────────────────────────────────────────────
# 5. STEEL GRADES — thermal properties
# ─────────────────────────────────────────────────────────────────────────────
# thermal_conductivity: lambda [W/m·K] at ~500°C (operating range)
# max_service_temp:     continuous service limit [°C]
# density:              [kg/m³]

STEEL_GRADES = {
    "S235": {
        "description":          "Structural carbon steel — common, low cost",
        "thermal_conductivity": 50.0,   # W/m·K
        "max_service_temp":     400,    # °C — not suitable for pyrolysis drum
        "density":              7850,   # kg/m³
        "note":                 "Not recommended for reactor drum above 400°C"
    },
    "S355": {
        "description":          "High-strength structural steel",
        "thermal_conductivity": 48.0,
        "max_service_temp":     400,
        "density":              7850,
        "note":                 "Not recommended for reactor drum above 400°C"
    },
    "P265GH": {
        "description":          "Pressure vessel steel — boiler grade",
        "thermal_conductivity": 46.0,
        "max_service_temp":     450,
        "density":              7850,
        "note":                 "Suitable for moderate temperature pressure vessels"
    },
    "16Mo3": {
        "description":          "Creep-resistant boiler steel — elevated temperature",
        "thermal_conductivity": 42.0,
        "max_service_temp":     530,
        "density":              7850,
        "note":                 "Good choice for reactor drum up to ~530°C"
    },
    "13CrMo4-5": {
        "description":          "Chromium-molybdenum creep-resistant steel",
        "thermal_conductivity": 38.0,
        "max_service_temp":     560,
        "density":              7800,
        "note":                 "Common for high-temperature pressure vessels"
    },
    "SS304": {
        "description":          "Austenitic stainless steel 1.4301",
        "thermal_conductivity": 16.0,   # significantly lower than carbon steel
        "max_service_temp":     870,
        "density":              7900,
        "note":                 "Low thermal conductivity — reduces heat transfer through wall"
    },
    "SS310S": {
        "description":          "Heat-resistant austenitic stainless 1.4845",
        "thermal_conductivity": 14.0,
        "max_service_temp":    1050,
        "density":              7900,
        "note":                 "Excellent oxidation resistance; lowest conductivity in this table"
    },
    "SS253MA": {
        "description":          "High-temperature austenitic stainless (Ce-alloyed)",
        "thermal_conductivity": 15.0,
        "max_service_temp":    1100,
        "density":              7800,
        "note":                 "Premium option for combustion chamber liners"
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 6. HEAT TRANSFER COEFFICIENTS  [W/m²·K]  — typical ranges
# ─────────────────────────────────────────────────────────────────────────────
# Used as defaults in Module 4 — engineer can override per project

HTC = {
    # Combustion gas side (outside drum wall)
    "h_combustion_gas_min":  25.0,   # low gas velocity, poor impingement
    "h_combustion_gas_typ":  50.0,   # typical forced convection, rotating kiln exterior
    "h_combustion_gas_max":  80.0,   # high velocity, good impingement

    # Pyrolysis side (inside drum — tumbling bed)
    "h_pyrolysis_min":       15.0,   # low fill level, dry granular material
    "h_pyrolysis_typ":       25.0,   # typical for rotary kiln biomass
    "h_pyrolysis_max":       40.0,   # high fill, good tumbling action

    # Screw conveyor (different geometry — higher contact)
    "h_screw_conveyor_typ":  60.0,   # better solid-wall contact than rotary kiln
}

# Pyrolysis reaction enthalpy [kJ/kg dry feed] — endothermic
# Wide range depending on feedstock and temperature
PYROLYSIS_ENTHALPY = {
    "wood_chips":      400,   # kJ/kg dry
    "sugar_cane":      380,   # kJ/kg dry — BR-01 approximate
    "rice_husk":       360,   # kJ/kg dry
    "sewage_sludge":   520,   # kJ/kg dry — higher due to protein/fat content
    "default":         400,   # kJ/kg dry — conservative default for unknown biomass
}

# Radiation heat loss coefficient  [W/m²·K⁴ — Stefan-Boltzmann]
STEFAN_BOLTZMANN = 5.67e-8   # W/m²·K⁴
EMISSIVITY_BARE_STEEL    = 0.85
EMISSIVITY_INSULATED     = 0.92
EMISSIVITY_PAINTED_STEEL = 0.80


# ─────────────────────────────────────────────────────────────────────────────
# 7. REGULATORY LIMITS
# ─────────────────────────────────────────────────────────────────────────────

EU_WID = {
    "pcc_min_temperature_C":    850,   # °C — must be sustained continuously
    "pcc_min_residence_time_s":   2.0, # seconds at ≥850°C
    "HCl_limit_mg_Nm3":          10,   # mg/Nm³ at 11% O₂ reference
    "CO_limit_mg_Nm3":           50,
    "NOx_limit_mg_Nm3":         200,   # as NO₂
    "SO2_limit_mg_Nm3":          50,
    "TOC_limit_mg_Nm3":          10,
    "dust_limit_mg_Nm3":         10,
    "O2_reference_pct":          11,   # % O₂ for emission normalisation
}

EBC = {
    "H_C_max_premium":   0.7,   # mol/mol — H/C < 0.7 → EBC Premium
    "H_C_max_basic":     0.7,   # same threshold; tier differs on Corg
    "O_C_max":           0.4,   # mol/mol
    "Corg_min_basic":   50.0,   # % — minimum organic carbon for EBC Basic
    "Corg_min_premium": 50.0,   # % — same threshold, additional PAH/metal checks
    "carbon_permanence_factor": {
        # Fraction of sequestered C credited as permanent (EBC methodology)
        "H_C_below_0_4":  0.95,
        "H_C_below_0_7":  0.90,
        "H_C_above_0_7":  0.80,  # does not qualify for EBC
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# 8. FEEDSTOCK LIBRARY  (ECN Phyllis2 reference data)
# ─────────────────────────────────────────────────────────────────────────────
# All compositions on DRY-ASH-FREE (daf) basis [%]
# HHV_dry in kJ/kg
# Use as starting point when client has no lab data

FEEDSTOCK_LIBRARY = {
    "sugar_cane_brush": {
        "description":  "Broza de Caña — sugar cane leaves/tops (BR-01 type)",
        "C_daf":  43.5,    # LSM-corrected value for Jibito BR-01
        "H_daf":   6.49,
        "O_daf":  48.51,
        "N_daf":   1.05,
        "S_daf":   0.46,
        "ash_dry": 6.84,   # % dry basis
        "moisture_ar": 10.13,  # % as-received (pelletised)
        "HHV_dry": 16288,  # kJ/kg — lab measured, Jibito BR-01
        "source":  "LSM 2602TN-R0 / UBE-11/2023-0238",
    },
    "wood_chips_generic": {
        "description":  "Generic softwood chips — ECN Phyllis average",
        "C_daf":  51.0,
        "H_daf":   6.1,
        "O_daf":  42.2,
        "N_daf":   0.4,
        "S_daf":   0.05,
        "ash_dry": 1.5,
        "moisture_ar": 35.0,
        "HHV_dry": 19500,
        "source":  "ECN Phyllis2",
    },
    "rice_husk": {
        "description":  "Rice husk — high ash content",
        "C_daf":  49.0,
        "H_daf":   6.0,
        "O_daf":  44.2,
        "N_daf":   0.5,
        "S_daf":   0.1,
        "ash_dry": 19.0,   # high ash — reduces biochar yield significantly
        "moisture_ar": 12.0,
        "HHV_dry": 15800,
        "source":  "ECN Phyllis2",
    },
    "sewage_sludge": {
        "description":  "Dried sewage sludge — high N and S",
        "C_daf":  52.0,
        "H_daf":   7.2,
        "O_daf":  28.0,
        "N_daf":   8.5,
        "S_daf":   1.8,
        "ash_dry": 38.0,   # very high ash
        "moisture_ar": 10.0,
        "HHV_dry": 16500,
        "source":  "ECN Phyllis2 average",
    },
    "straw_wheat": {
        "description":  "Wheat straw",
        "C_daf":  48.5,
        "H_daf":   5.8,
        "O_daf":  44.8,
        "N_daf":   0.5,
        "S_daf":   0.1,
        "ash_dry": 7.0,
        "moisture_ar": 14.0,
        "HHV_dry": 17200,
        "source":  "ECN Phyllis2",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 9. VALIDATION REFERENCE VALUES  (Jibito project — LSM 2602TN-R0)
# ─────────────────────────────────────────────────────────────────────────────
# Used in tests/ to verify calculation engine against known-good results

JIBITO_REFERENCE = {
    # Feedstock
    "HHV_daf_kJ_kg":    17484,   # LSM HSC value
    "HHV_dry_kJ_kg":    16288,
    "LHV_dry_kJ_kg":    14720,
    "HHV_ar_kJ_kg":     14638,
    "LHV_ar_kJ_kg":     13204,
    "ash_dry_pct":       6.843,
    "biochar_yield_dry_pct": 17.69,

    # Mass balance — Scenario A (2000 kg/h)
    "feed_ar_kg_h":      2000,
    "biochar_dry_kg_h":   318,
    "syngas_kg_h":       1682,

    # Mass balance — Scenario B (2500 kg/h)
    "feed_ar_kg_h_B":    2500,
    "biochar_dry_kg_h_B": 397,
    "syngas_kg_h_B":     2103,

    # Mass balance — Scenario C (2800 kg/h)
    "feed_ar_kg_h_C":    2800,
    "biochar_dry_kg_h_C": 445,
    "syngas_kg_h_C":     2355,

    # Energy balance — Scenario A
    "feed_combustion_kW":  7316,
    "feed_sensible_kW":      32,
    "air_sensible_kW":      157,
    "total_in_kW":         7505,
    "flue_gas_loss_kW":    5909,
    "radiation_kW":          85,
    "biochar_combustion_kW": 1471,
    "biochar_sensible_kW":    61,
    "total_out_kW":        7532,

    # Thermal limit
    "thermal_limit_kg_h":  2800,   # maximum feed rate for this reactor geometry
}