KCAL_TO_KJ = 4.1868
KJ_TO_KCAL = 1 / KCAL_TO_KJ
LATENT_HEAT_WATER_25C = 2442.0
LATENT_HEAT_WATER_100C = 2257.0
H_TO_WATER_MASS_RATIO = 9.0
AIR_O2_MASS_FRACTION = 0.232
AIR_N2_MASS_FRACTION = 0.768
AIR_N2_O2_MASS_RATIO = 3.31
CP_DRY_AIR = 1.005
CP_MOIST_AIR = 1.04
CP_WATER_VAPOUR = 1.86
CP_CO2 = 0.85
CP_BIOMASS_WET = 1.65
CP_BIOCHAR = 1.256
RHO_AIR_0C = 1.293
T_REF_K = 273.15
STEFAN_BOLTZMANN = 5.67e-8
EMISSIVITY_BARE_STEEL = 0.85
EMISSIVITY_INSULATED = 0.92
EMISSIVITY_PAINTED_STEEL = 0.80

BOIE = {
    "C":  35160.0,
    "H":  116225.0,
    "O": -11090.0,
    "N":   6280.0,
    "S":  10465.0,
}

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

TEMP = {
    "energy_balance_reference": 0,
    "pyrolysis_nominal": 550,
    "syngas_exit_reactor": 625,
    "biochar_exit_reactor": 550,
    "pcc_operating": 850,
    "pcc_flue_exit": 900,
    "biochar_discharge_target": 20,
    "biochar_spontaneous_combustion_risk": 200,
    "biochar_pyrophoric_threshold": 454,
}

STEEL_GRADES = {
    "S235": {
        "description": "Structural carbon steel",
        "thermal_conductivity": 50.0,
        "max_service_temp": 400,
        "density": 7850,
        "note": "Not recommended above 400C"
    },
    "S355": {
        "description": "High-strength structural steel",
        "thermal_conductivity": 48.0,
        "max_service_temp": 400,
        "density": 7850,
        "note": "Not recommended above 400C"
    },
    "P265GH": {
        "description": "Pressure vessel steel boiler grade",
        "thermal_conductivity": 46.0,
        "max_service_temp": 450,
        "density": 7850,
        "note": "Suitable for moderate temperature vessels"
    },
    "16Mo3": {
        "description": "Creep-resistant boiler steel",
        "thermal_conductivity": 42.0,
        "max_service_temp": 530,
        "density": 7850,
        "note": "Good for reactor drum up to 530C"
    },
    "13CrMo4-5": {
        "description": "Chromium-molybdenum creep-resistant steel",
        "thermal_conductivity": 38.0,
        "max_service_temp": 560,
        "density": 7800,
        "note": "Common for high-temperature pressure vessels"
    },
    "SS304": {
        "description": "Austenitic stainless steel 1.4301",
        "thermal_conductivity": 16.0,
        "max_service_temp": 870,
        "density": 7900,
        "note": "Low conductivity reduces heat transfer through wall"
    },
    "SS310S": {
        "description": "Heat-resistant austenitic stainless 1.4845",
        "thermal_conductivity": 14.0,
        "max_service_temp": 1050,
        "density": 7900,
        "note": "Excellent oxidation resistance"
    },
    "SS253MA": {
        "description": "High-temperature austenitic stainless Ce-alloyed",
        "thermal_conductivity": 15.0,
        "max_service_temp": 1100,
        "density": 7800,
        "note": "Premium option for combustion chamber liners"
    },
}

HTC = {
    "h_combustion_gas_min": 25.0,
    "h_combustion_gas_typ": 50.0,
    "h_combustion_gas_max": 80.0,
    "h_pyrolysis_min": 15.0,
    "h_pyrolysis_typ": 25.0,
    "h_pyrolysis_max": 40.0,
    "h_screw_conveyor_typ": 60.0,
}

PYROLYSIS_ENTHALPY = {
    "wood_chips": 400,
    "sugar_cane": 380,
    "rice_husk": 360,
    "sewage_sludge": 520,
    "default": 400,
}

EU_WID = {
    "pcc_min_temperature_C": 850,
    "pcc_min_residence_time_s": 2.0,
    "HCl_limit_mg_Nm3": 10,
    "CO_limit_mg_Nm3": 50,
    "NOx_limit_mg_Nm3": 200,
    "SO2_limit_mg_Nm3": 50,
    "TOC_limit_mg_Nm3": 10,
    "dust_limit_mg_Nm3": 10,
    "O2_reference_pct": 11,
}

EBC = {
    "H_C_max_premium": 0.7,
    "H_C_max_basic": 0.7,
    "O_C_max": 0.4,
    "Corg_min_basic": 50.0,
    "Corg_min_premium": 50.0,
    "carbon_permanence_factor": {
        "H_C_below_0_4": 0.95,
        "H_C_below_0_7": 0.90,
        "H_C_above_0_7": 0.80,
    }
}

FEEDSTOCK_LIBRARY = {
    "sugar_cane_brush": {
        "description": "Broza de Cana BR-01 sugar cane brush",
        "C_daf": 43.5,
        "H_daf": 6.49,
        "O_daf": 48.51,
        "N_daf": 1.05,
        "S_daf": 0.46,
        "ash_dry": 6.84,
        "moisture_ar": 10.13,
        "HHV_dry": 16288,
        "source": "LSM 2602TN-R0",
    },
    "wood_chips_generic": {
        "description": "Generic softwood chips ECN Phyllis average",
        "C_daf": 51.0,
        "H_daf": 6.1,
        "O_daf": 42.2,
        "N_daf": 0.4,
        "S_daf": 0.05,
        "ash_dry": 1.5,
        "moisture_ar": 35.0,
        "HHV_dry": 19500,
        "source": "ECN Phyllis2",
    },
    "rice_husk": {
        "description": "Rice husk high ash content",
        "C_daf": 49.0,
        "H_daf": 6.0,
        "O_daf": 44.2,
        "N_daf": 0.5,
        "S_daf": 0.1,
        "ash_dry": 19.0,
        "moisture_ar": 12.0,
        "HHV_dry": 15800,
        "source": "ECN Phyllis2",
    },
    "sewage_sludge": {
        "description": "Dried sewage sludge high N and S",
        "C_daf": 52.0,
        "H_daf": 7.2,
        "O_daf": 28.0,
        "N_daf": 8.5,
        "S_daf": 1.8,
        "ash_dry": 38.0,
        "moisture_ar": 10.0,
        "HHV_dry": 16500,
        "source": "ECN Phyllis2 average",
    },
    "straw_wheat": {
        "description": "Wheat straw",
        "C_daf": 48.5,
        "H_daf": 5.8,
        "O_daf": 44.8,
        "N_daf": 0.5,
        "S_daf": 0.1,
        "ash_dry": 7.0,
        "moisture_ar": 14.0,
        "HHV_dry": 17200,
        "source": "ECN Phyllis2",
    },
}

JIBITO_REFERENCE = {
    "HHV_daf_kJ_kg": 17484,
    "HHV_dry_kJ_kg": 16288,
    "LHV_dry_kJ_kg": 14720,
    "HHV_ar_kJ_kg": 14638,
    "LHV_ar_kJ_kg": 13204,
    "ash_dry_pct": 6.843,
    "biochar_yield_dry_pct": 17.69,
    "feed_ar_kg_h": 2000,
    "biochar_dry_kg_h": 318,
    "syngas_kg_h": 1682,
    "feed_ar_kg_h_B": 2500,
    "biochar_dry_kg_h_B": 397,
    "syngas_kg_h_B": 2103,
    "feed_ar_kg_h_C": 2800,
    "biochar_dry_kg_h_C": 445,
    "syngas_kg_h_C": 2355,
    "feed_combustion_kW": 7316,
    "feed_sensible_kW": 32,
    "air_sensible_kW": 157,
    "total_in_kW": 7505,
    "flue_gas_loss_kW": 5909,
    "radiation_kW": 85,
    "biochar_combustion_kW": 1471,
    "biochar_sensible_kW": 61,
    "total_out_kW": 7532,
    "thermal_limit_kg_h": 2800,
}