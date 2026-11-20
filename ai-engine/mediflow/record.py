"""Longitudinal, provenance-aware patient record.

Three provenance tiers (shown separately in the UI, never merged silently):
    patient_reported     - answers from guided intake
    machine_extracted    - values read from uploaded documents
    clinician_confirmed  - anything a clinician accepted or edited

Conflicts (same test, same date, different values from different sources) are
detected and *kept* side by side for the clinician; the system never picks one.
The draft summary is built from templates, so every sentence is generated from
specific record items and lists their ids. It cannot add facts that are not in
the record.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TIERS = ("patient_reported", "machine_extracted", "clinician_confirmed")


class PatientRecord:
    def __init__(self, patient_id: str, name: str | None = None):
        self.patient_id = patient_id
        self.name = name
        self.items: list[dict] = []
        self.documents: dict[str, dict] = {}
        self.audit: list[dict] = []

    # ------------------------------------------------------------ ingestion
    def add_document(self, doc: dict, image_path: str | None = None):
        meta = {k: v for k, v in doc.items() if k not in ("items", "ocr_text")}
        meta["image_path"] = image_path
        self.documents[doc["doc_id"]] = meta
        self.items.extend(doc["items"])
        self._log("system", "document_ingested", doc["doc_id"], f"{len(doc['items'])} items")

    def add_intake(self, answers: list[dict], language: str):
        """answers: [{question_id, kind, label, value, answer_text}]"""
        when = datetime.now().date().isoformat()
        for a in answers:
            if a.get("value") in (None, "", []):
                continue
            self.items.append({
                "id": uuid.uuid4().hex[:10],
                "kind": a["kind"], "code": a["question_id"], "label": a["label"],
                "value": a["value"], "unit": None, "date": when,
                "tier": "patient_reported", "review": "pending",
                "reasons": [],
                "source": {"type": "intake", "question_id": a["question_id"],
                           "language": language, "text": a.get("answer_text")},
            })
        self._log("patient", "intake_submitted", None, language)

    # ------------------------------------------------------------ clinician review
    def review(self, item_id: str, action: str, reviewer: str, new_value: str | None = None):
        it = self.get(item_id)
        if action == "accept":
            it["tier"], it["review"] = "clinician_confirmed", "accepted"
        elif action == "edit":
            it["original_value"] = it.get("original_value", it["value"])
            it["value"] = new_value
            it["tier"], it["review"] = "clinician_confirmed", "edited"
        elif action == "reject":
            it["review"] = "rejected"
        it["reviewed_by"] = reviewer
        it["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        self._log(reviewer, f"review_{action}", item_id, new_value or "")

    # ------------------------------------------------------------ views
    def get(self, item_id):
        return next(i for i in self.items if i["id"] == item_id)

    def active(self):
        return [i for i in self.items if i.get("review") != "rejected"]

    def conflicts(self) -> list[dict]:
        groups = defaultdict(list)
        for it in self.active():
            if it["kind"] == "lab_result" and it.get("value") and it.get("date"):
                groups[(it["code"], it["date"])].append(it)
        out = []
        for (code, d), its in groups.items():
            vals = {i["value"] for i in its}
            docs = {i["source"].get("doc_id") for i in its}
            if len(vals) > 1 and len(docs) > 1:
                out.append({"code": code, "date": d, "items": [i["id"] for i in its],
                            "values": sorted(vals)})
        return out

    def timeline(self) -> list[dict]:
        return sorted(self.active(), key=lambda i: (i.get("date") or "9999", i["kind"], i["code"]))

    def series(self, code: str):
        pts = [i for i in self.active() if i["code"] == code and i.get("date")]
        return sorted(pts, key=lambda i: i["date"])

    # ------------------------------------------------------------ draft summary
    def draft_summary(self) -> list[dict]:
        """Template-based summary. Each sentence lists the record items it came from."""
        sents = []
        rep = [i for i in self.active() if i["tier"] == "patient_reported"
               or i["source"]["type"] == "intake"]
        for it in rep:
            sents.append({"text": f"Patient reports {it['label'].lower()}: {_fmt(it['value'])}.",
                          "sources": [it["id"]], "tier": it["tier"]})
        labs = [i for i in self.active() if i["kind"] == "lab_result" and i.get("value")]
        conflict_ids = {x for c in self.conflicts() for x in c["items"]}
        by_code = defaultdict(list)
        for it in labs:
            by_code[it["code"]].append(it)
        for code, its in sorted(by_code.items()):
            its = sorted(its, key=lambda i: i.get("date") or "")
            latest = its[-1]
            parts = [f"{i['value']} {i['unit'] or ''}".strip() + f" on {i.get('date') or 'unknown date'}"
                     for i in its]
            text = f"{latest['label']}: " + "; ".join(parts) + "."
            if any(i["id"] in conflict_ids for i in its):
                text += " CONFLICT: sources disagree for the same date - clinician to resolve."
            if any(i.get("review") == "needs_review" for i in its):
                text += " Some values are unverified."
            tier = "clinician_confirmed" if all(i["tier"] == "clinician_confirmed" for i in its) \
                else "machine_extracted"
            sents.append({"text": text, "sources": [i["id"] for i in its], "tier": tier})
        return sents

    # ------------------------------------------------------------ persistence
    def _log(self, actor, action, target, detail):
        self.audit.append({"at": datetime.now().isoformat(timespec="seconds"),
                           "actor": actor, "action": action, "target": target, "detail": detail})

    def to_json(self) -> dict:
        return {"patient_id": self.patient_id, "name": self.name, "items": self.items,
                "documents": self.documents, "audit": self.audit}

    @classmethod
    def from_json(cls, d: dict) -> "PatientRecord":
        r = cls(d["patient_id"], d.get("name"))
        r.items, r.documents, r.audit = d["items"], d["documents"], d["audit"]
        return r

    def save(self, path: Path):
        path.write_text(json.dumps(self.to_json(), indent=2))


def _fmt(v):
    return ", ".join(v) if isinstance(v, list) else str(v)
