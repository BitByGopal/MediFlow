"""MediFlow prototype demo (synthetic data only).

Run from the repository root:
    streamlit run demo/app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine"))
from mediflow.extract import extract_document  # noqa: E402
from mediflow.record import PatientRecord  # noqa: E402
from mediflow.intake import QUESTIONS, LANGS, build_answers  # noqa: E402

DATA = ROOT / "datasets" / "synthetic"
RESULTS = ROOT / "results"
UPLOADS = ROOT / "demo" / "_uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
from mediflow.ocr import TESSERACT_PATH  # noqa: E402
if not TESSERACT_PATH:
    st.error("Tesseract OCR is not installed. Install it from "
             "https://github.com/UB-Mannheim/tesseract/wiki (default folder), then restart the app.")
    st.stop()

st.set_page_config(page_title="MediFlow prototype", page_icon="🩺", layout="wide")

TIER_BADGE = {
    "patient_reported": "🟣 Patient-reported",
    "machine_extracted": "🔵 Machine-extracted",
    "clinician_confirmed": "🟢 Clinician-confirmed",
}
REVIEW_BADGE = {
    "auto_verified": "✅ checks passed",
    "needs_review": "⚠️ needs review",
    "accepted": "✔ accepted",
    "edited": "✎ edited",
    "rejected": "✖ rejected",
    "pending": "… pending",
}

# ------------------------------------------------------------------ state
if "record" not in st.session_state:
    st.session_state.record = PatientRecord("DEMO")
rec: PatientRecord = st.session_state.record


@st.cache_data(show_spinner=False)
def process(path: str, doc_id: str) -> dict:
    return extract_document(Image.open(path), doc_id)


def draw_evidence(img_path, items, selected=None, width=900):
    img = Image.open(img_path).convert("RGB")
    d = ImageDraw.Draw(img)
    for it in items:
        b = it["source"]["bbox"]
        col = {"auto_verified": (22, 163, 74), "needs_review": (234, 88, 12)}.get(
            it.get("review"), (100, 116, 139))
        w = 4
        if selected and it["id"] == selected:
            col, w = (37, 99, 235), 7
        d.rectangle([b[0] - 6, b[1] - 6, b[2] + 6, b[3] + 6], outline=col, width=w)
    scale = width / img.width
    return img.resize((width, int(img.height * scale)))


def crop_evidence(img_path, it, pad=18):
    img = Image.open(img_path).convert("RGB")
    b = it["source"].get("row_bbox") or it["source"]["bbox"]
    c = img.crop((max(0, b[0] - pad), max(0, b[1] - pad), b[2] + pad, b[3] + pad))
    d = ImageDraw.Draw(c)
    v = it["source"]["bbox"]
    d.rectangle([v[0] - b[0] + pad - 4, v[1] - b[1] + pad - 4,
                 v[2] - b[0] + pad + 4, v[3] - b[1] + pad + 4], outline=(37, 99, 235), width=3)
    return c


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🩺 MediFlow")
st.sidebar.caption("Research prototype · synthetic data only · not for clinical use")
page = st.sidebar.radio("Go to", ["1 · Patient intake", "2 · Upload documents",
                                  "3 · Doctor review", "4 · Timeline & summary",
                                  "5 · Evaluation results"])
st.sidebar.divider()
n_items = len(rec.items)
st.sidebar.metric("Record items", n_items)
st.sidebar.metric("Needs review", sum(i.get("review") == "needs_review" for i in rec.items))
st.sidebar.metric("Conflicts", len(rec.conflicts()))
if st.sidebar.button("Reset demo"):
    st.session_state.record = PatientRecord("DEMO")
    st.rerun()

# ------------------------------------------------------------------ 1 intake
if page.startswith("1"):
    st.header("Guided patient intake")
    st.caption("Closed questions are stored as language-independent codes. Free-text answers are kept "
               "exactly as typed, in the patient's language, and are not machine-translated. "
               "Hindi and Telugu wording is a draft and still needs validation by a qualified reviewer.")
    lang = st.selectbox("Language / भाषा / భాష", list(LANGS), format_func=lambda k: LANGS[k])
    with st.form("intake"):
        raw = {}
        for q in QUESTIONS:
            label = q["text"][lang]
            if q["type"] == "text":
                raw[q["id"]] = st.text_input(label)
            elif q["type"] == "single":
                opts = list(q["options"])
                raw[q["id"]] = st.radio(label, opts, index=None,
                                        format_func=lambda o, q=q: q["options"][o][lang], horizontal=True)
            else:
                opts = list(q["options"])
                raw[q["id"]] = st.multiselect(label, opts,
                                              format_func=lambda o, q=q: q["options"][o][lang])
        if st.form_submit_button("Submit answers"):
            answers = build_answers(raw, lang)
            rec.add_intake(answers, lang)
            st.success(f"Saved {sum(1 for a in answers if a['value'])} answers as patient-reported items.")
    mine = [i for i in rec.items if i["tier"] == "patient_reported"]
    if mine:
        st.subheader("Stored patient-reported items")
        st.dataframe(pd.DataFrame([{"question": i["label"], "stored value": str(i["value"]),
                                    "as typed": i["source"].get("text"),
                                    "language": i["source"]["language"]} for i in mine]),
                     hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ 2 upload
elif page.startswith("2"):
    st.header("Upload medical documents")
    st.caption("MVP scope: printed laboratory reports (PNG/JPG). Handwriting is out of scope.")
    tab1, tab2 = st.tabs(["Load a synthetic patient", "Upload your own image"])
    with tab1:
        man_path = DATA / "manifest.json"
        if not man_path.exists():
            st.warning("No synthetic dataset yet. Run `python ai-engine/scripts/run_pipeline.py` first.")
        else:
            man = json.loads(man_path.read_text())
            pats = sorted({(m["patient_id"], m["patient_name"]) for m in man})
            groups = {m["pair_group"] for m in man}
            has_conf = {p for p, _ in pats
                        if len({g for g in groups if g.startswith(p)}) >
                        len({g.rsplit('-', 1)[0] for g in groups if g.startswith(p)})}
            choice = st.selectbox("Patient", pats, format_func=lambda p: f"{p[0]} · {p[1]}" +
                                  ("  (has a same-day report from another lab)" if p[0] in has_conf else ""))
            quality = st.radio("Document quality", ["clean", "scan", "hard_scan"], horizontal=True,
                               format_func={"clean": "Clean print", "scan": "Scanned",
                                            "hard_scan": "Low-quality phone photo"}.get)
            if st.button("Load and process this patient's reports", type="primary"):
                docs = [m for m in man if m["patient_id"] == choice[0] and m["variant"] == quality]
                rec.patient_id, rec.name = choice
                prog = st.progress(0.0)
                for k, m in enumerate(sorted(docs, key=lambda m: m["date"])):
                    if m["report_id"] in rec.documents:
                        continue
                    path = str(DATA / m["image"])
                    doc = process(path, m["report_id"])
                    rec.add_document(doc, path)
                    prog.progress((k + 1) / len(docs))
                st.success(f"Processed {len(docs)} reports.")
    with tab2:
        up = st.file_uploader("Lab report image", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        if up and st.button("Process uploaded files"):
            for f in up:
                p = UPLOADS / f.name
                p.write_bytes(f.getbuffer())
                doc_id = f"U-{p.stem[:20]}"
                rec.add_document(process(str(p), doc_id), str(p))
            st.success("Done.")
    if rec.documents:
        st.subheader("Processed documents")
        st.dataframe(pd.DataFrame([{
            "document": k, "report date": v.get("date") or "⚠️ not found",
            "deskew angle°": v.get("ocr_angle"),
            "items": sum(1 for i in rec.items if i["source"].get("doc_id") == k),
            "need review": sum(1 for i in rec.items if i["source"].get("doc_id") == k
                               and i.get("review") == "needs_review"),
        } for k, v in rec.documents.items()]), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ 3 review
elif page.startswith("3"):
    st.header("Doctor review: every value linked to its evidence")
    if not rec.documents:
        st.info("Load or upload documents first (page 2).")
    else:
        doc_id = st.selectbox("Document", list(rec.documents),
                              format_func=lambda k: f"{k} · {rec.documents[k].get('date') or 'no date'}")
        meta = rec.documents[doc_id]
        items = [i for i in rec.items if i["source"].get("doc_id") == doc_id]
        only_flag = st.toggle("Show only items that need review", value=False)
        shown = [i for i in items if not only_flag or i.get("review") == "needs_review"]
        left, right = st.columns([1.15, 1])
        with right:
            if not shown:
                st.success("Nothing to review on this document.")
                sel = None
            else:
                sel = st.radio("Extracted items", [i["id"] for i in shown], format_func=lambda x: (
                    lambda i: f"{i['label']}: {i['value']} {i['unit'] or ''} · "
                              f"{REVIEW_BADGE.get(i.get('review'), '')}")(rec.get(x)))
                it = rec.get(sel)
                st.markdown(f"**{it['label']}**: printed as *{it['name_as_printed']}* · "
                            f"{TIER_BADGE[it['tier']]}")
                st.image(crop_evidence(meta["image_path"], it), caption="Evidence on the original page")
                c1, c2, c3 = st.columns(3)
                c1.metric("Value", f"{it['value']}")
                c2.metric("OCR confidence", f"{it['source'].get('ocr_conf') or 0:.0f}")
                c3.metric("Second read", it["source"].get("second_read") or "-")
                st.caption(f"Unit: {it['unit']} · Reference range (as printed): {it['reference_range']} · "
                           f"Flag (as printed): {it['flag_as_printed'] or '-'} · Report date: {it.get('date')}")
                if it["reasons"]:
                    st.warning("Why this needs review: " + "; ".join(it["reasons"]))
                if it.get("original_value"):
                    st.info(f"Edited by clinician, machine value was {it['original_value']}")
                b1, b2, b3 = st.columns(3)
                if b1.button("✔ Accept", key=f"a{sel}", use_container_width=True):
                    rec.review(sel, "accept", "Dr. Demo"); st.rerun()
                if b3.button("✖ Reject", key=f"r{sel}", use_container_width=True):
                    rec.review(sel, "reject", "Dr. Demo"); st.rerun()
                with b2.popover("✎ Edit", use_container_width=True):
                    nv = st.text_input("Correct value", value=it["value"] or "", key=f"e{sel}")
                    if st.button("Save", key=f"s{sel}"):
                        rec.review(sel, "edit", "Dr. Demo", nv); st.rerun()
        with left:
            st.image(draw_evidence(meta["image_path"], items, sel),
                     caption="Green: all checks passed · Orange: needs review · Blue: selected")

# ------------------------------------------------------------------ 4 timeline
elif page.startswith("4"):
    st.header(f"Longitudinal record · {rec.name or rec.patient_id}")
    conf = rec.conflicts()
    if conf:
        st.error(f"{len(conf)} conflict(s): different documents report different values for the same "
                 "test on the same date. MediFlow keeps both; the clinician decides.")
        for c in conf:
            cols = st.columns(len(c["items"]))
            for col, iid in zip(cols, c["items"]):
                it = rec.get(iid)
                meta = rec.documents[it["source"]["doc_id"]]
                col.image(crop_evidence(meta["image_path"], it),
                          caption=f"{it['source']['doc_id']} · {meta.get('lab', '')} {it['value']} {it['unit'] or ''}")
    tl = rec.timeline()
    if not tl:
        st.info("No record items yet.")
    else:
        st.subheader("Draft summary (each line links to its sources)")
        st.caption("Generated from templates over record items only, so it cannot introduce new facts. "
                   "It stays a DRAFT until a clinician confirms it.")
        for s in rec.draft_summary():
            with st.expander(f"{TIER_BADGE[s['tier']].split()[0]} {s['text']}"):
                for iid in s["sources"]:
                    it = rec.get(iid)
                    if it["source"]["type"] == "document":
                        meta = rec.documents[it["source"]["doc_id"]]
                        st.image(crop_evidence(meta["image_path"], it),
                                 caption=f"{it['source']['doc_id']} · {it.get('date')} · "
                                         f"{REVIEW_BADGE.get(it.get('review'), '')}")
                    else:
                        st.write(f"Intake answer ({it['source']['language']}): "
                                 f"{it['source'].get('text') or it['value']}")

        st.subheader("Trend view")
        codes = sorted({i["code"] for i in tl if i["kind"] == "lab_result"})
        if codes:
            code = st.selectbox("Test", codes)
            ser = rec.series(code)
            try:
                df = pd.DataFrame({"date": [i["date"] for i in ser],
                                   "value": [float(i["value"]) for i in ser]})
                st.line_chart(df.groupby("date").mean(), y="value")
            except (TypeError, ValueError):
                st.caption("Some values are not numeric; review them first.")

        st.subheader("Timeline")
        st.dataframe(pd.DataFrame([{
            "date": i.get("date"), "item": i["label"],
            "value": str(i["value"]) + (f" {i['unit']}" if i.get("unit") else ""),
            "provenance": TIER_BADGE[i["tier"]],
            "status": REVIEW_BADGE.get(i.get("review"), ""),
            "source": i["source"].get("doc_id") or f"intake ({i['source'].get('language')})",
        } for i in tl]), hide_index=True, use_container_width=True)

        with st.expander("Audit log"):
            st.dataframe(pd.DataFrame(rec.audit), hide_index=True, use_container_width=True)
        st.download_button("Download record (JSON)", json.dumps(rec.to_json(), indent=2),
                           file_name=f"{rec.patient_id}_record.json")

# ------------------------------------------------------------------ 5 results
else:
    st.header("Evaluation on synthetic lab reports")
    mp = RESULTS / "metrics.json"
    if not mp.exists():
        st.warning("Run `python ai-engine/scripts/run_pipeline.py` to produce results.")
    else:
        m = json.loads(mp.read_text())
        cfg = m.pop("_config", {})
        reasons = m.pop("review_reasons", {})
        st.caption(f"{cfg.get('documents')} synthetic report images from {cfg.get('patients')} synthetic "
                   f"patients (seed {cfg.get('seed')}). No real patient data. Not a clinical validation.")
        if (RESULTS / "metrics_chart.png").exists():
            st.image(str(RESULTS / "metrics_chart.png"))
        order = [k for k in ("clean", "scan", "hard_scan", "ALL") if k in m]
        df = pd.DataFrame({k: m[k] for k in order})
        st.dataframe(df, use_container_width=True)
        st.subheader("Why items were sent to review")
        st.bar_chart(pd.DataFrame({"reason": list(reasons), "count": list(reasons.values())}),
                     x="reason", y="count", horizontal=True)
