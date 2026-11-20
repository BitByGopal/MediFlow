"""Plot key metrics by document quality -> results/metrics_chart.png"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
m = json.loads((ROOT / "results" / "metrics.json").read_text())
levels = [("clean", "Clean print"), ("scan", "Scanned"), ("hard_scan", "Low-quality photo")]
metrics = [("value_exact_match", "Value read\ncorrectly"), ("source_link_accuracy", "Evidence box\ncorrect"),
           ("error_catch_rate", "Wrong values\nflagged for review"), ("auto_verified_share", "Passed all checks\n(no review needed)")]
colors = ["#86b6ef", "#2a78d6", "#104281"]  # ordinal blue ramp: better -> worse quality

fig, ax = plt.subplots(figsize=(11, 5.2), dpi=160)
bw, gap = 0.24, 0.02
for li, ((lk, ll), c) in enumerate(zip(levels, colors)):
    for mi, (mk, _) in enumerate(metrics):
        v = m[lk][mk] * 100
        x = mi + (li - 1) * (bw + gap)
        ax.add_patch(FancyBboxPatch((x - bw / 2, 0), bw, v, boxstyle="round,pad=0,rounding_size=0.02",
                                    linewidth=0, facecolor=c, mutation_aspect=40))
        ax.text(x, v + 1.2, f"{v:.0f}", ha="center", va="bottom", fontsize=9, color="#3d3d3a")
    ax.bar([0], [0], color=c, label=ll)
ax.set_xlim(-0.5, len(metrics) - 0.5); ax.set_ylim(0, 112)
ax.set_xticks(range(len(metrics))); ax.set_xticklabels([t for _, t in metrics], fontsize=10, color="#3d3d3a")
ax.set_ylabel("%", color="#6b6a63")
ax.yaxis.grid(True, color="#e8e7e2", linewidth=0.8); ax.set_axisbelow(True)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#c9c8c1"); ax.tick_params(colors="#6b6a63", length=0)
ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 1.13), fontsize=10)
cfg = m["_config"]
ax.set_title(f"MediFlow extraction pipeline on {cfg['documents']} synthetic lab reports",
             loc="left", fontsize=13, color="#1f1f1d", pad=34)
fig.text(0.01, 0.01, "Synthetic data only; not a clinical validation. Wrong values that passed every check: "
         f"{m['clean']['silent_error_rate']*100:.1f}% / {m['scan']['silent_error_rate']*100:.1f}% / "
         f"{m['hard_scan']['silent_error_rate']*100:.1f}% of extracted values (clean / scanned / low-quality).",
         fontsize=8.5, color="#6b6a63")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(ROOT / "results" / "metrics_chart.png")
print("saved")
