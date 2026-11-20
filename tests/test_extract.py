"""Run from repo root:  python -m pytest tests -q"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-engine"))

from mediflow.extract import _canon, _clean_token, _parse_date
from mediflow.record import PatientRecord


def test_ocr_confusables():
    assert _canon("HbAlc") == _canon("HbA1c")


def test_trailing_dot_is_stripped():
    assert _clean_token("137.") == "137"


def test_dates_normalised():
    assert _parse_date("Sample Collected: 31/01/2025")[0] == "2025-01-31"
    assert _parse_date("Collection Date : 08-May-2025")[0] == "2025-05-08"
    assert _parse_date("Date: 2025-05-08")[0] == "2025-05-08"


def _lab(doc, value, d="2025-05-08", code="FBS"):
    return {"id": f"{doc}-{code}", "kind": "lab_result", "code": code, "label": code,
            "value": value, "unit": "mg/dL", "date": d, "tier": "machine_extracted",
            "review": "auto_verified", "reasons": [], "source": {"type": "document", "doc_id": doc}}


def test_conflict_kept_not_resolved():
    r = PatientRecord("T")
    r.items += [_lab("A", "120"), _lab("B", "160")]
    c = r.conflicts()
    assert len(c) == 1 and c[0]["values"] == ["120", "160"]
    assert len(r.active()) == 2  # both values remain in the record


def test_clinician_edit_keeps_original():
    r = PatientRecord("T")
    r.items.append(_lab("A", "1332"))
    r.review("A-FBS", "edit", "Dr. X", "133")
    it = r.get("A-FBS")
    assert it["value"] == "133" and it["original_value"] == "1332"
    assert it["tier"] == "clinician_confirmed"
    assert r.audit[-1]["action"] == "review_edit"
