"""Evidence-linked extraction from printed lab reports.

Design rule: the extractor never produces a value that it cannot point to.
Every item carries `source.bbox` (where on the page it was read) and
`source.text` (the exact OCR text). It then goes through independent checks;
any failed check marks the item `needs_review` instead of silently "fixing" it.

Nothing here interprets results clinically. The H/L flag is copied from the
report as printed; it is never computed by MediFlow.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from PIL import Image
from rapidfuzz import fuzz

from .catalog import ALIASES, TESTS, UNITS
from .ocr import OCRResult, reread_region, run_ocr

NUM_RE = re.compile(r"^[<>]?\d+(?:[.,]\d+)?$")
FLAG_RE = re.compile(r"^\(?([HL])\)?$")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_PATTERNS = [
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "dmy"),
    (re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})"), "dmon"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "iso"),
]
DATE_LABELS = ("date", "collected", "collection")

CONF_THRESHOLD = 80.0


def _clean_token(t: str) -> str:
    return t.strip().strip(":;|").rstrip(".").replace(",", ".")


def _is_unit(tok: str) -> bool:
    return max(fuzz.ratio(tok, u) for u in UNITS) >= 80


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


_CONFUSABLE = str.maketrans({"l": "1", "i": "1", "|": "1", "o": "0"})


def _canon(s: str) -> str:
    """Collapse characters OCR commonly confuses (HbA1c vs HbAlc, 0 vs O)."""
    return s.lower().translate(_CONFUSABLE)


def _match_test(words):
    """Match the start of an OCR line against known test aliases."""
    best = None
    for alias, code in ALIASES:
        k = len(alias.split())
        if len(words) <= k:
            continue
        cand = " ".join(w.text for w in words[:k])
        score = fuzz.ratio(_canon(cand), _canon(alias))
        if score >= 85 and (best is None or score > best[2] or
                            (score == best[2] and k > best[1])):
            best = (code, k, score, alias)
    return best


def _parse_date(text: str):
    for rx, style in DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        try:
            if style == "dmy":
                d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            elif style == "dmon":
                d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            else:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.isoformat(), m.group(0)
        except (ValueError, KeyError):
            return None, m.group(0)
    return None, None


def extract_document(img: Image.Image, doc_id: str, ocr: OCRResult | None = None) -> dict:
    ocr = ocr or run_ocr(img)
    doc = {"doc_id": doc_id, "doc_type": "lab_report", "ocr_angle": round(ocr.angle, 2),
           "ocr_text": ocr.text, "date": None, "date_source": None,
           "patient": {}, "items": []}

    for words in ocr.lines:
        line = " ".join(w.text for w in words)
        low = line.lower()

        # ---- report date (the anchor for the timeline)
        if doc["date"] is None and any(lbl in low for lbl in DATE_LABELS):
            iso, raw = _parse_date(line)
            if raw:
                ws = [w for w in words if w.text in raw or raw.startswith(w.text)] or words
                doc["date"] = iso
                doc["date_source"] = {"text": raw, "bbox": _union([w.box for w in ws]),
                                      "parsed": iso is not None}

        # ---- patient identifiers (kept for record matching, minimised later)
        m = re.search(r"Patient ID[:\s]+([A-Z]{2}-\d+)", line)
        if m:
            doc["patient"]["id"] = m.group(1)
        m = re.search(r"Patient Name[:\s]+(.+?)(?:\s+Patient ID|$)", line)
        if m:
            doc["patient"]["name"] = m.group(1).strip()

        # ---- lab result rows
        hit = _match_test(words)
        if not hit:
            continue
        code, k, score, alias = hit
        rest = words[k:]
        # The result must appear BEFORE the unit; numbers after it belong to the
        # reference range and must never be taken as the patient's value.
        unit_pos = next((i for i, w in enumerate(rest) if _is_unit(w.text)), len(rest))
        val_i = next((i for i, w in enumerate(rest[:unit_pos])
                      if NUM_RE.match(_clean_token(w.text))), None)
        if val_i is None:
            doc["items"].append(_item(code, words[:k], None, None, None, None, None, doc_id,
                                      reasons=["value not found on line"]))
            continue
        vw = rest[val_i]
        tail = rest[val_i + 1:]
        flag, unit, unit_w = None, None, None
        # Look at the next few tokens: skip OCR junk, pick up a printed flag, then the unit.
        j = 0
        while j < min(len(tail), 4) and unit is None:
            tok = tail[j].text
            core = re.sub(r"[^A-Za-z()]", "", tok)
            s, u = max((fuzz.ratio(tok, u), u) for u in UNITS)
            if s >= 80:
                unit, unit_w = u, tail[j]
            elif flag is None and FLAG_RE.match(core):
                flag = FLAG_RE.match(core).group(1)
            elif flag is None and tok[:1] in "HL" and len(tok) > 2:
                # flag glued to the unit by OCR, e.g. "Lng/mL" or "Lsong/mL"
                s2, u2 = max((fuzz.partial_ratio(u, tok[1:]), u) for u in UNITS if len(u) > 2)
                if s2 >= 80:
                    flag, unit, unit_w = tok[0], u2, tail[j]
            elif re.fullmatch(r"[\W_]{1,3}", tok):
                pass  # stray punctuation from the scan
            j += 1
        tail = tail[j:] if unit else tail
        ref = " ".join(w.text for w in tail) or None
        doc["items"].append(_item(code, words[:k], vw, flag, unit, unit_w, ref, doc_id,
                                  name_score=score))

    _verify(img, doc)
    return doc


def _item(code, name_words, vw, flag, unit, unit_w, ref, doc_id, name_score=None, reasons=None):
    value = _clean_token(vw.text) if vw else None
    return {
        "id": uuid.uuid4().hex[:10],
        "kind": "lab_result",
        "code": code,
        "label": TESTS[code]["names"][0],
        "name_as_printed": " ".join(w.text for w in name_words),
        "value": value,
        "unit": unit,
        "reference_range": ref,
        "flag_as_printed": flag,
        "tier": "machine_extracted",          # -> clinician_confirmed only via review
        "source": {
            "type": "document", "doc_id": doc_id, "page": 1,
            "bbox": vw.box if vw else _union([w.box for w in name_words]),
            "row_bbox": _union([w.box for w in name_words] + ([vw.box] if vw else [])
                               + ([unit_w.box] if unit_w else [])),
            "text": vw.text if vw else None,
            "ocr_conf": vw.conf if vw else None,
        },
        "name_match_score": name_score,
        "review": "needs_review" if reasons else None,
        "reasons": list(reasons or []),
    }


def _verify(img: Image.Image, doc: dict) -> None:
    """Independent checks. Failing any one sends the item to the review queue."""
    for it in doc["items"]:
        if it["value"] is None:
            continue
        reasons = it["reasons"]
        src = it["source"]
        spec = TESTS[it["code"]]

        # 1. OCR confidence for the value token
        if src["ocr_conf"] is not None and src["ocr_conf"] < CONF_THRESHOLD:
            reasons.append(f"low OCR confidence ({src['ocr_conf']:.0f})")

        # 2. Second independent read of the evidence region must agree
        second = reread_region(img, src["bbox"])
        src["second_read"] = second
        if second.replace(",", ".") != it["value"]:
            reasons.append(f"second read disagrees ('{second}')")

        # 3. Technical plausibility (catches lost decimal points etc.)
        try:
            v = float(it["value"].lstrip("<>"))
            lo, hi = spec["plausible"]
            if not lo <= v <= hi:
                reasons.append("value outside technically plausible range")
        except ValueError:
            reasons.append("value is not numeric")

        # 4. Unit must be present and match the catalog
        if it["unit"] is None:
            reasons.append("unit not recognised")
        elif it["unit"] != spec["unit"]:
            reasons.append(f"unexpected unit {it['unit']}")

        # 5. Document date must be readable for the item to sit on the timeline
        if not doc["date"]:
            reasons.append("document date not found")

        it["date"] = doc["date"]
        it["review"] = "needs_review" if reasons else "auto_verified"
