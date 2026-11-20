"""OCR layer: Tesseract with word-level bounding boxes and simple deskew.

Every word keeps its pixel box in the ORIGINAL uploaded image, so any value
extracted later can be highlighted on the page the patient actually uploaded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from PIL import Image

import os
import shutil


def _find_tesseract():
    """Use TESSERACT_CMD if set, else PATH, else the usual Windows install folders."""
    if os.environ.get("TESSERACT_CMD"):
        return os.environ["TESSERACT_CMD"]
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(p):
            return p
    return None


TESSERACT_PATH = _find_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


@dataclass
class Word:
    text: str
    conf: float
    box: list          # [x0, y0, x1, y1] in original-image pixels
    line_key: tuple


@dataclass
class OCRResult:
    words: list
    lines: list        # list[list[Word]] in reading order
    angle: float
    size: tuple

    @property
    def text(self) -> str:
        return "\n".join(" ".join(w.text for w in ln) for ln in self.lines)


def estimate_skew(img: Image.Image, max_deg: float = 3.0, step: float = 0.1) -> float:
    """Projection-profile deskew: pick the angle whose row profile is sharpest."""
    g = np.asarray(img.convert("L").resize((img.width // 4, img.height // 4)))
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = bw.shape
    best, best_score = 0.0, -1.0
    for a in np.arange(-max_deg, max_deg + 1e-9, step):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(a), score
    return best


def _unrotate_box(box, angle, cx, cy):
    """Map a box from the deskewed image back to the original image."""
    a = math.radians(angle)  # inverse of the deskew rotation
    pts = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]
    out = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * math.cos(a) - dy * math.sin(a),
                    cy + dx * math.sin(a) + dy * math.cos(a)))
    xs, ys = zip(*out)
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def run_ocr(img: Image.Image, deskew: bool = True, lang: str = "eng") -> OCRResult:
    img = img.convert("RGB")
    angle = estimate_skew(img) if deskew else 0.0
    work = img.rotate(angle, resample=Image.BICUBIC, fillcolor="white") if abs(angle) > 0.05 else img
    data = pytesseract.image_to_data(work, lang=lang, config="--psm 6",
                                     output_type=pytesseract.Output.DICT)
    cx, cy = img.width / 2, img.height / 2
    words, lines = [], {}
    for i, t in enumerate(data["text"]):
        t = (t or "").strip()
        if not t:
            continue
        box = [data["left"][i], data["top"][i],
               data["left"][i] + data["width"][i], data["top"][i] + data["height"][i]]
        if abs(angle) > 0.05:
            box = _unrotate_box(box, angle, cx, cy)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        w = Word(t, float(data["conf"][i]), box, key)
        words.append(w)
        lines.setdefault(key, []).append(w)
    ordered = [sorted(v, key=lambda w: w.box[0]) for _, v in sorted(lines.items())]
    return OCRResult(words, ordered, angle, img.size)


def reread_region(img: Image.Image, box, numeric: bool = True, pad: int = 8) -> str:
    """Independent second read of a single region (used by the grounding check)."""
    x0, y0, x1, y1 = box
    crop = img.convert("L").crop((max(0, x0 - pad), max(0, y0 - pad),
                                  min(img.width, x1 + pad), min(img.height, y1 + pad)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.BICUBIC)
    cfg = "--psm 7"
    if numeric:
        cfg += " -c tessedit_char_whitelist=0123456789.<>"
    return pytesseract.image_to_string(crop, config=cfg).strip()
