import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

with open(os.path.join(RESULTS_DIR, "results.json")) as f:
    R = json.load(f)

rows = R["overhead_scaling"]
ns = [r["n"] for r in rows]
mean_lat = [r["mean_latency_ms"] for r in rows]
p99_lat = [r["p99_latency_ms"] for r in rows]
throughput = [r["throughput_records_per_sec"] for r in rows]
bytes_per_record = [r["bytes_per_record"] for r in rows]

# Larger, more legible defaults for a document/print figure (not a slide-sized
# 3-across layout, which becomes unreadably small once embedded at document
# width). Stacked vertically instead, each panel full-width.
plt.rcParams.update({
    "font.size": 15,
    "axes.titlesize": 17,
    "axes.labelsize": 15,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 14,
})

fig, axes = plt.subplots(3, 1, figsize=(10, 15))

axes[0].plot(ns, mean_lat, marker="o", markersize=9, linewidth=2.5, label="mean")
axes[0].plot(ns, p99_lat, marker="s", markersize=9, linewidth=2.5, label="p99")
axes[0].set_xlabel("Simulated transaction volume (records)")
axes[0].set_ylabel("Per-record append\nlatency (ms)")
axes[0].set_title("Record append latency vs. volume\n(single process, synthetic data)", pad=14)
axes[0].legend(loc="best", frameon=True)
axes[0].grid(alpha=0.35)
axes[0].tick_params(width=1.5, length=6)

axes[1].plot(ns, throughput, marker="o", markersize=9, linewidth=2.5, color="darkorange")
axes[1].set_xlabel("Simulated transaction volume (records)")
axes[1].set_ylabel("Throughput\n(records/sec)")
axes[1].set_title("Ledger append throughput\n(hash + Shamir-quorum HMAC sign)", pad=14)
axes[1].grid(alpha=0.35)
axes[1].tick_params(width=1.5, length=6)

axes[2].plot(ns, bytes_per_record, marker="o", markersize=9, linewidth=2.5, color="seagreen")
axes[2].set_xlabel("Simulated transaction volume (records)")
axes[2].set_ylabel("Bytes per record\n(canonicalized)")
axes[2].set_title("Storage overhead per record\n(near-constant, as predicted)", pad=14)
axes[2].grid(alpha=0.35)
axes[2].set_ylim(0, max(bytes_per_record) * 1.3)
axes[2].tick_params(width=1.5, length=6)

for ax in axes:
    for spine in ax.spines.values():
        spine.set_linewidth(1.3)

plt.tight_layout(pad=2.5, h_pad=4.0)
plt.savefig(os.path.join(RESULTS_DIR, "overhead_scaling.png"), dpi=200, bbox_inches="tight")
print("saved overhead_scaling.png (larger, vertical layout, dpi=200)")

# reset rcParams to defaults before drawing the tamper-detection chart, which
# is sized/readable separately and unaffected by this change
plt.rcParams.update(plt.rcParamsDefault)

# Tamper detection illustration
fig2, ax = plt.subplots(figsize=(7, 3.2))
tamper = R["correctness_and_tamper_detection"]
labels = ["Chain before\ntampering", "Naive tamper\n(content only)", "Tamper +\nhash recompute\n(no quorum)"]
values = [1 if tamper["chain_valid_before_tamper"] else 0,
          1 if tamper["chain_valid_after_naive_tamper"] else 0,
          1 if tamper["chain_valid_after_hash_recomputed_tamper_without_quorum"] else 0]
colors = ["seagreen" if v else "crimson" for v in values]
bars = ax.bar(labels, [1, 1, 1], color=colors)
ax.set_yticks([])
ax.set_title(f"Tamper detection on a {tamper['n_records']}-record simulated ledger\n"
             f"(green = chain verifies as VALID, red = INVALID / tampering detected)")
for b, v, lbl in zip(bars, values, ["VALID", "DETECTED", "DETECTED"]):
    ax.text(b.get_x() + b.get_width()/2, 0.5, lbl, ha="center", va="center",
             color="white", fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(RESULTS_DIR, "tamper_detection.png"), dpi=160)
print("saved tamper_detection.png")
