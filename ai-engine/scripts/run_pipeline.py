"""Generate the synthetic dataset and evaluate the pipeline.

Usage (from ai-engine/):
    python scripts/run_pipeline.py --patients 20 --out ../datasets/synthetic
Writes results to ../results/metrics.json and ../results/per_document.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mediflow.evaluate import run  # noqa: E402
from mediflow.synth import generate_dataset  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--patients", type=int, default=20)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--out", default="../datasets/synthetic")
ap.add_argument("--results", default="../results")
ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
a = ap.parse_args()

out, res = Path(a.out), Path(a.results)
res.mkdir(parents=True, exist_ok=True)
t0 = time.time()
m = generate_dataset(out, n_patients=a.patients, seed=a.seed)
print(f"generated {len(m)} report images in {time.time() - t0:.1f}s")
t0 = time.time()
per_doc, summary = run(out, workers=a.workers)
print(f"evaluated in {time.time() - t0:.1f}s")
summary["_config"] = {"patients": a.patients, "seed": a.seed, "documents": len(m)}
(res / "metrics.json").write_text(json.dumps(summary, indent=2))
(res / "per_document.json").write_text(json.dumps(per_doc, indent=2))
print(json.dumps(summary, indent=2))
