"""Reference catalog of lab tests supported by the MVP.

The catalog is used in two places:
  * synth.py  - to generate synthetic reports with realistic values
  * extract.py - to recognise test names in OCR output

`plausible` is a *technical* sanity range used only to flag likely OCR errors
(e.g. a decimal point lost). It is NOT a clinical reference range and is never
used to interpret a patient's result.
"""

TESTS = {
    "HEMOGLOBIN": {
        "names": ["Hemoglobin", "Haemoglobin", "Hb"],
        "unit": "g/dL", "ref": "13.0 - 17.0",
        "gen": (9.0, 18.0, 1), "plausible": (2.0, 25.0),
    },
    "FBS": {
        "names": ["Fasting Blood Glucose", "Fasting Blood Sugar", "FBS"],
        "unit": "mg/dL", "ref": "70 - 100",
        "gen": (65, 260, 0), "plausible": (20, 800),
    },
    "HBA1C": {
        "names": ["HbA1c", "Glycated Hemoglobin"],
        "unit": "%", "ref": "4.0 - 5.6",
        "gen": (4.5, 11.5, 1), "plausible": (3.0, 20.0),
    },
    "TOTAL_CHOLESTEROL": {
        "names": ["Total Cholesterol", "Serum Cholesterol"],
        "unit": "mg/dL", "ref": "< 200",
        "gen": (120, 320, 0), "plausible": (50, 700),
    },
    "TRIGLYCERIDES": {
        "names": ["Triglycerides"],
        "unit": "mg/dL", "ref": "< 150",
        "gen": (60, 400, 0), "plausible": (20, 3000),
    },
    "CREATININE": {
        "names": ["Serum Creatinine", "Creatinine"],
        "unit": "mg/dL", "ref": "0.7 - 1.3",
        "gen": (0.5, 3.5, 2), "plausible": (0.1, 20.0),
    },
    "UREA": {
        "names": ["Blood Urea", "Urea"],
        "unit": "mg/dL", "ref": "15 - 40",
        "gen": (10, 90, 0), "plausible": (2, 400),
    },
    "TSH": {
        "names": ["TSH", "Thyroid Stimulating Hormone"],
        "unit": "uIU/mL", "ref": "0.4 - 4.0",
        "gen": (0.1, 12.0, 2), "plausible": (0.005, 150.0),
    },
    "WBC": {
        "names": ["Total WBC Count", "WBC Count", "Total Leucocyte Count"],
        "unit": "cells/uL", "ref": "4000 - 11000",
        "gen": (3000, 16000, -2), "plausible": (500, 100000),
    },
    "PLATELETS": {
        "names": ["Platelet Count", "Platelets"],
        "unit": "lakh/uL", "ref": "1.5 - 4.5",
        "gen": (0.8, 5.0, 2), "plausible": (0.05, 15.0),
    },
    "VITAMIN_D": {
        "names": ["Vitamin D (25-OH)", "Vitamin D"],
        "unit": "ng/mL", "ref": "30 - 100",
        "gen": (6, 70, 1), "plausible": (1, 300),
    },
    "SGPT": {
        "names": ["SGPT (ALT)", "SGPT", "ALT"],
        "unit": "U/L", "ref": "7 - 56",
        "gen": (8, 140, 0), "plausible": (1, 5000),
    },
}

UNITS = sorted({t["unit"] for t in TESTS.values()}, key=len, reverse=True)

# Every alias -> canonical code, longest first so "Total WBC Count" wins over "WBC Count".
ALIASES = sorted(
    ((name, code) for code, t in TESTS.items() for name in t["names"]),
    key=lambda p: len(p[0]), reverse=True,
)
