"""Synthetic lab-report generator.

Produces PNG images of printed laboratory reports together with a ground-truth
JSON file that records every value *and the exact pixel box where it was drawn*.
That lets us evaluate both extraction accuracy and source-link (evidence)
accuracy without any real patient data.

All names, IDs and lab names are fictional.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .catalog import TESTS

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONTS = {
    "sans": (FONT_DIR / "DejaVuSans.ttf", FONT_DIR / "DejaVuSans-Bold.ttf"),
    "serif": (FONT_DIR / "DejaVuSerif.ttf", FONT_DIR / "DejaVuSerif-Bold.ttf"),
    "mono": (FONT_DIR / "DejaVuSansMono.ttf", FONT_DIR / "DejaVuSansMono-Bold.ttf"),
}

FIRST = ["Aarav", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Karthik", "Meera",
         "Arjun", "Divya", "Rohan", "Lakshmi", "Suresh", "Kavya", "Imran", "Harpreet"]
LAST = ["Sharma", "Reddy", "Singh", "Iyer", "Verma", "Naidu", "Gupta", "Kaur",
        "Rao", "Patel", "Khan", "Menon"]
LABS = ["Sunrise Diagnostics", "CarePoint Pathology Lab", "Medilink Clinical Lab"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

W, H = 1654, 2339  # A4 at ~200 dpi


@dataclass
class FieldGT:
    code: str
    name: str
    value: str
    unit: str
    ref: str
    flag: str
    bbox_value: list
    bbox_row: list


@dataclass
class ReportGT:
    report_id: str
    patient_id: str
    patient_name: str
    age: int
    sex: str
    date: str          # ISO yyyy-mm-dd
    date_text: str     # as printed
    bbox_date: list
    lab: str
    template: str
    variant: str
    image: str
    fields: list = field(default_factory=list)
    lines: list = field(default_factory=list)


# ---------------------------------------------------------------- helpers

def _fmt_value(code: str, rng: random.Random, base: float | None = None) -> str:
    lo, hi, dec = TESTS[code]["gen"]
    if base is None:
        v = rng.uniform(lo, hi)
    else:  # drift from previous visit for a plausible longitudinal series
        v = min(hi, max(lo, base * rng.uniform(0.85, 1.15)))
    if dec < 0:
        v = round(v, dec)
        return str(int(v))
    if dec == 0:
        return str(int(round(v)))
    return f"{v:.{dec}f}"


def _flag(code: str, value: str) -> str:
    ref = TESTS[code]["ref"].replace(" ", "")
    v = float(value)
    if ref.startswith("<"):
        return "H" if v >= float(ref[1:]) else ""
    lo, hi = (float(x) for x in ref.split("-"))
    return "H" if v > hi else "L" if v < lo else ""


def _date_text(d: date, style: str) -> str:
    if style == "dmy":
        return d.strftime("%d/%m/%Y")
    if style == "dmon":
        return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"
    return d.isoformat()


def _draw(draw, xy, text, font, boxes: list | None = None):
    draw.text(xy, text, font=font, fill=(20, 20, 20))
    bb = list(draw.textbbox(xy, text, font=font))
    if boxes is not None:
        boxes.append(bb)
    return bb


# ---------------------------------------------------------------- templates

TEMPLATES = {
    #        font,   date style, label,               columns x (test, result, flag, unit, ref)
    "A": ("sans", "dmy", "Sample Collected:", (110, 760, None, 980, 1250)),
    "B": ("serif", "dmon", "Collection Date :", (110, 700, 900, 1010, 1270)),
    "C": ("mono", "iso", "Date:", (110, 820, 1000, 1080, 1330)),
}


def render_report(gt: ReportGT, values: dict, rng: random.Random) -> Image.Image:
    font_name, _, date_label, cols = TEMPLATES[gt.template]
    reg, bold = FONTS[font_name]
    f_title = ImageFont.truetype(str(bold), 54)
    f_head = ImageFont.truetype(str(bold), 34)
    f_body = ImageFont.truetype(str(reg), 34)
    f_small = ImageFont.truetype(str(reg), 26)

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    lines = []

    _draw(d, (110, 90), gt.lab, f_title); lines.append(gt.lab)
    sub = "Department of Laboratory Medicine"
    _draw(d, (110, 165), sub, f_small); lines.append(sub)
    d.line((110, 220, W - 110, 220), fill=(0, 0, 0), width=3)

    y = 260
    t = f"Patient Name: {gt.patient_name}"; _draw(d, (110, y), t, f_body); lines.append(t)
    t = f"Patient ID: {gt.patient_id}"; _draw(d, (1000, y), t, f_body); lines.append(t)
    y += 60
    t = f"Age/Sex: {gt.age} Y / {gt.sex}"; _draw(d, (110, y), t, f_body); lines.append(t)
    lab_x = 1000
    lb = _draw(d, (lab_x, y), date_label, f_body)
    db = _draw(d, (lb[2] + 14, y), gt.date_text, f_body)
    gt.bbox_date = db
    lines.append(f"{date_label} {gt.date_text}")
    y += 90
    d.line((110, y, W - 110, y), fill=(0, 0, 0), width=2)
    y += 25

    xt, xr, xf, xu, xref = cols
    for x, h in ((xt, "Test"), (xr, "Result"), (xu, "Unit"), (xref, "Reference Range")):
        _draw(d, (x, y), h, f_head)
    if xf:
        _draw(d, (xf, y), "Flag", f_head)
    lines.append("Test Result " + ("Flag " if xf else "") + "Unit Reference Range")
    y += 70
    d.line((110, y - 12, W - 110, y - 12), fill=(120, 120, 120), width=1)

    for code, (name, value) in values.items():
        spec = TESTS[code]
        flag = _flag(code, value)
        row_boxes = []
        _draw(d, (xt, y), name, f_body, row_boxes)
        vb = _draw(d, (xr, y), value, f_body, row_boxes)
        line = f"{name} {value}"
        if xf:
            if flag:
                _draw(d, (xf, y), flag, f_body, row_boxes)
                line += f" {flag}"
        else:  # template A prints the flag inline after the value
            if flag:
                _draw(d, (vb[2] + 12, y), f"({flag})", f_body, row_boxes)
                line += f" ({flag})"
        _draw(d, (xu, y), spec["unit"], f_body, row_boxes)
        _draw(d, (xref, y), spec["ref"], f_body, row_boxes)
        line += f" {spec['unit']} {spec['ref']}"
        lines.append(line)
        row = [min(b[0] for b in row_boxes), min(b[1] for b in row_boxes),
               max(b[2] for b in row_boxes), max(b[3] for b in row_boxes)]
        gt.fields.append(asdict(FieldGT(code, name, value, spec["unit"], spec["ref"], flag, vb, row)))
        y += 64

    y += 60
    foot = "This is a computer generated report. Results relate to the sample tested."
    _draw(d, (110, y), foot, f_small); lines.append(foot)
    foot2 = "SYNTHETIC TEST DOCUMENT - NOT A REAL PATIENT"
    _draw(d, (110, H - 140), foot2, f_small); lines.append(foot2)
    gt.lines = lines
    return img


# ---------------------------------------------------------------- scan noise

def _rot_box(box, angle_deg, cx, cy):
    a = math.radians(-angle_deg)  # PIL rotates counter-clockwise for positive angles
    pts = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]
    out = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * math.cos(a) - dy * math.sin(a),
                    cy + dx * math.sin(a) + dy * math.cos(a)))
    xs, ys = zip(*out)
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


NOISE = {  # level: (max tilt deg, downscale range, blur range, noise sigma, jpeg quality)
    "scan": (1.5, (0.55, 0.70), (0.6, 1.2), 9, 45),
    "hard_scan": (3.0, (0.36, 0.45), (1.2, 1.7), 16, 30),
}


def scanify(img: Image.Image, gt: ReportGT, rng: random.Random, level: str = "scan") -> Image.Image:
    """Simulate a phone photo / cheap scan: tilt, blur, noise, low-res, JPEG."""
    tilt, sc, bl, sigma, _ = NOISE[level]
    angle = rng.uniform(-tilt, tilt)
    img = img.rotate(angle, resample=Image.BICUBIC, fillcolor="white")
    cx, cy = W / 2, H / 2
    for f in gt.fields:
        f["bbox_value"] = _rot_box(f["bbox_value"], angle, cx, cy)
        f["bbox_row"] = _rot_box(f["bbox_row"], angle, cx, cy)
    gt.bbox_date = _rot_box(gt.bbox_date, angle, cx, cy)

    scale = rng.uniform(*sc)
    small = img.resize((int(W * scale), int(H * scale)), Image.BILINEAR)
    img = small.resize((W, H), Image.BILINEAR)
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(*bl)))
    arr = np.asarray(img).astype(np.float32)
    arr = arr * rng.uniform(0.85, 0.95) + rng.uniform(5, 20)  # greyish paper
    arr += np.random.default_rng(rng.randint(0, 10**6)).normal(0, sigma, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return img


# ---------------------------------------------------------------- dataset

def generate_dataset(out_dir: Path, n_patients: int = 12, seed: int = 7,
                     conflict_rate: float = 0.15) -> list[dict]:
    """Generate a longitudinal synthetic dataset.

    Each patient gets 2-4 reports over ~18 months. Every report is saved in
    three quality levels: clean, scan, and hard_scan (low-res phone photo). With probability `conflict_rate` a patient
    also gets a second report from a different lab on the same date with a
    disagreeing value, so conflict handling can be demonstrated and tested.
    """
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    rid = 0
    for p in range(n_patients):
        pid = f"MF-{1000 + p}"
        pname = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        age, sex = rng.randint(24, 78), rng.choice(["M", "F"])
        panel = rng.sample(list(TESTS), k=rng.randint(5, 8))
        names = {c: rng.choice(TESTS[c]["names"]) for c in panel}
        prev = {}
        d0 = date(2025, 1, 1) + timedelta(days=rng.randint(0, 120))
        n_reports = rng.randint(2, 4)
        plan = []
        for r in range(n_reports):
            dt = d0 + timedelta(days=r * rng.randint(90, 180))
            plan.append((dt, rng.choice(LABS), None))
        if rng.random() < conflict_rate:
            dt, lab, _ = plan[-1]
            plan.append((dt, rng.choice([l for l in LABS if l != lab]), "conflict"))

        for dt, lab, kind in plan:
            if kind == "conflict":
                # same sample date, another lab: identical except ONE disagreeing test
                vals = dict(last_vals)
                c0 = panel[0]
                v = last_vals[c0][1]
                while v == last_vals[c0][1]:
                    v = _fmt_value(c0, rng)
                vals[c0] = (names[c0], v)
            else:
                vals = {}
                for c in panel:
                    base = float(prev[c]) if c in prev else None
                    vals[c] = (names[c], _fmt_value(c, rng, base))
                prev.update({c: v for c, (_, v) in vals.items()})
                last_vals = vals
            tpl = rng.choice(list(TEMPLATES))
            for variant in ("clean", "scan", "hard_scan"):
                rid += 1
                rep_id = f"R{rid:04d}"
                gt = ReportGT(rep_id, pid, pname, age, sex, dt.isoformat(),
                              _date_text(dt, TEMPLATES[tpl][1]), [], lab, tpl, variant,
                              f"{rep_id}.png")
                img = render_report(gt, vals, rng)
                if variant != "clean":
                    img = scanify(img, gt, rng, variant)
                    img.save(out_dir / gt.image.replace(".png", ".jpg"), quality=NOISE[variant][4])
                    gt.image = gt.image.replace(".png", ".jpg")
                else:
                    img.save(out_dir / gt.image)
                rec = asdict(gt)
                rec["pair_group"] = f"{pid}-{dt.isoformat()}-{lab}"
                (out_dir / f"{rep_id}.json").write_text(json.dumps(rec, indent=2))
                manifest.append(rec)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
