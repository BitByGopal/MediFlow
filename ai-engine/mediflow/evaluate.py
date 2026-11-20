"""Evaluation of the extraction + evidence pipeline against synthetic ground truth.

Metrics (reported per document-quality level):
  CER                    character error rate of full-page OCR vs rendered text
  test P / R / F1        did we find the right tests on each report
  value exact match      extracted value == printed value (of matched tests)
  unit / date accuracy   unit string and normalised report date
  source-link accuracy   evidence box overlaps the true value box (IoU >= 0.5)
  error catch rate       of wrong values, % sent to needs_review
  false alarm rate       of correct values, % sent to needs_review
  silent error rate      wrong value AND auto_verified (the dangerous case)
"""
from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image
from rapidfuzz.distance import Levenshtein

from .extract import extract_document


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def _norm(s: str) -> str:
    return " ".join(s.split())


def _num_eq(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def evaluate_one(args):
    data_dir, gt = args
    img = Image.open(Path(data_dir) / gt["image"])
    doc = extract_document(img, gt["report_id"])
    ref_text = _norm(" ".join(gt["lines"]))
    hyp_text = _norm(doc["ocr_text"])
    cer = Levenshtein.distance(ref_text, hyp_text) / max(1, len(ref_text))

    gt_by_code = {f["code"]: f for f in gt["fields"]}
    rows = []
    seen = set()
    for it in doc["items"]:
        g = gt_by_code.get(it["code"])
        dup = it["code"] in seen
        seen.add(it["code"])
        rows.append({
            "tp": bool(g) and not dup,
            "value_ok": bool(g) and _num_eq(it["value"], g["value"]),
            "unit_ok": bool(g) and it["unit"] == g["unit"],
            "link_ok": bool(g) and iou(it["source"]["bbox"], g["bbox_value"]) >= 0.5,
            "flagged": it["review"] == "needs_review",
            "reasons": it["reasons"],
        })
    return {
        "report_id": gt["report_id"], "variant": gt["variant"], "template": gt["template"],
        "cer": cer, "n_gt": len(gt["fields"]), "rows": rows,
        "date_ok": doc["date"] == gt["date"],
        "date_link_ok": bool(doc["date_source"]) and iou(doc["date_source"]["bbox"], gt["bbox_date"]) >= 0.3,
    }


def summarise(results: list[dict]) -> dict:
    by = defaultdict(list)
    for r in results:
        by[r["variant"]].append(r)
        by["ALL"].append(r)
    out = {}
    for v, rs in by.items():
        rows = [x for r in rs for x in r["rows"]]
        tp = sum(x["tp"] for x in rows)
        n_pred = len(rows)
        n_gt = sum(r["n_gt"] for r in rs)
        matched = [x for x in rows if x["tp"]]
        wrong = [x for x in matched if not x["value_ok"]]
        right = [x for x in matched if x["value_ok"]]
        p = tp / n_pred if n_pred else 0
        rc = tp / n_gt if n_gt else 0
        out[v] = {
            "documents": len(rs),
            "fields_in_ground_truth": n_gt,
            "CER_mean": round(sum(r["cer"] for r in rs) / len(rs), 4),
            "test_precision": round(p, 4),
            "test_recall": round(rc, 4),
            "test_F1": round(2 * p * rc / (p + rc), 4) if p + rc else 0,
            "value_exact_match": round(len(right) / len(matched), 4) if matched else 0,
            "unit_accuracy": round(sum(x["unit_ok"] for x in matched) / len(matched), 4) if matched else 0,
            "date_accuracy": round(sum(r["date_ok"] for r in rs) / len(rs), 4),
            "source_link_accuracy": round(sum(x["link_ok"] for x in matched) / len(matched), 4) if matched else 0,
            "wrong_values": len(wrong),
            "error_catch_rate": round(sum(x["flagged"] for x in wrong) / len(wrong), 4) if wrong else None,
            "false_alarm_rate": round(sum(x["flagged"] for x in right) / len(right), 4) if right else None,
            "silent_error_rate": round(sum(not x["flagged"] for x in wrong) / len(matched), 4) if matched else 0,
            "auto_verified_share": round(sum(not x["flagged"] for x in matched) / len(matched), 4) if matched else 0,
        }
    reasons = defaultdict(int)
    for r in results:
        for x in r["rows"]:
            for why in x["reasons"]:
                reasons[why.split(" (")[0].split(" '")[0]] += 1
    out["review_reasons"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1]))
    return out


def run(data_dir: Path, workers: int = 4) -> tuple[list, dict]:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    with ProcessPoolExecutor(workers) as ex:
        results = list(ex.map(evaluate_one, [(str(data_dir), g) for g in manifest]))
    return results, summarise(results)
