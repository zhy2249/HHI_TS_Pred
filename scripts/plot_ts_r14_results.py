#!/usr/bin/env python3
"""Plot registered R14 BD-rate results without changing the result ledger.

Example (from the repository root):
    python3 scripts/plot_ts_r14_results.py --date 20261024
"""

import argparse
import csv
import os
from pathlib import Path
import re
import tempfile

# Keep matplotlib's cache out of the user's home and select a headless backend.
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "hhi-ts-r14-mpl"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
MODES = tuple(f"R14-{i}" for i in range(1, 16))
SEQUENCES = (
    "BasketballDrill", "BQMall", "PartyScene", "RaceHorsesC",
    "FourPeople", "Johnny", "KristenAndSara",
)
QPS = (22, 27, 32, 37)


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def build_data(data_dir, configuration):
    sequence = np.full((len(MODES), len(SEQUENCES)), np.nan)
    qp = np.full((len(MODES), len(QPS)), np.nan)
    qp_count = np.zeros_like(qp, dtype=int)
    seen = set()
    for row in read_rows(data_dir / "sequence_bdrate.csv"):
        if row["experiment"] not in MODES or row["configuration"] != configuration:
            continue
        if row["sequence"] not in SEQUENCES:
            continue
        key = (row["experiment"], row["sequence"])
        if key in seen:
            raise ValueError(f"Duplicate sequence result: {key}")
        seen.add(key)
        # This figure deliberately contains complete measured curves only.
        if row["status"] == "complete":
            sequence[MODES.index(key[0]), SEQUENCES.index(key[1])] = float(row["bd_611_pct"])
    if len(seen) != len(MODES) * len(SEQUENCES):
        raise ValueError("The registered R14 CE sequence grid is incomplete (missing rows).")

    seen = set()
    for row in read_rows(data_dir / "qp_group_summary.csv"):
        if (row["experiment"] not in MODES or row["configuration"] != configuration
                or row["group"] != "CE"):
            continue
        target = int(row["qp"])
        if target not in QPS:
            continue
        key = (row["experiment"], target)
        if key in seen:
            raise ValueError(f"Duplicate QP result: {key}")
        seen.add(key)
        i, j = MODES.index(key[0]), QPS.index(target)
        count = int(row["valid_sequences"])
        if int(row["expected_sequences"]) != len(SEQUENCES):
            raise ValueError(f"Unexpected CE sequence count: {key}")
        if row["bd_611_pct"]:
            if not 0 < count <= len(SEQUENCES):
                raise ValueError(f"Invalid QP coverage: {key}")
            qp[i, j] = float(row["bd_611_pct"])
            qp_count[i, j] = count
        elif count:
            raise ValueError(f"Missing value despite valid QP coverage: {key}")
    if len(seen) != len(MODES) * len(QPS):
        raise ValueError("The registered R14 CE QP grid is incomplete (missing rows).")
    return sequence, qp, qp_count


def draw_heatmap(values, columns, title, footer, path, counts=None):
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError(f"No valid data for {path.name}")
    limit = float(np.max(np.abs(finite))) or 0.001
    cmap = plt.get_cmap("RdBu_r").copy()
    cmap.set_bad("#dddddd")
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    width = 12.5 if len(columns) > 4 else 8.6
    fig, ax = plt.subplots(figsize=(width, 10.8))
    fig.subplots_adjust(left=0.12, right=0.86, bottom=0.17, top=0.88)
    image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(columns)), columns)
    ax.set_yticks(range(len(MODES)), MODES)
    ax.tick_params(axis="both", length=0, labelsize=10, pad=7)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(-0.5, len(columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(MODES), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, top=False, left=False)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            if not np.isfinite(value):
                label, color = "missing", "#555555"
            else:
                label = f"{value:+.3f}" if value else "0.000"
                if counts is not None and counts[i, j] < len(SEQUENCES):
                    label += f"*\n({counts[i, j]}/{len(SEQUENCES)})"
                color = "white" if abs(value) > 0.62 * limit else "#222222"
            ax.text(j, i, label, ha="center", va="center", color=color, fontsize=9.5)
    bar = fig.colorbar(image, ax=ax, fraction=0.037, pad=0.025, shrink=0.72)
    bar.set_label("6:1:1 BD-rate (%)", fontsize=10)
    bar.ax.tick_params(labelsize=9)
    fig.suptitle(title, fontsize=15, y=0.97)
    fig.text(0.12, 0.105, footer, fontsize=9, va="top", linespacing=1.5)
    fig.savefig(path, format="svg", metadata={"Date": None, "Creator": "plot_ts_r14_results.py"})
    # Matplotlib emits trailing spaces in SVG path coordinates; keep diffs clean.
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n",
                    encoding="utf-8")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "docs/experiments/results")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/experiments/figures")
    parser.add_argument("--configuration", default="LB", choices=("LB",))
    parser.add_argument("--date", default="20261024", help="Snapshot label and filename suffix, YYYYMMDD")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{8}", args.date):
        parser.error("--date must be YYYYMMDD")
    sequence, qp, counts = build_data(args.data_dir, args.configuration)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "svg.fonttype": "none",
        "svg.hashsalt": "hhi-ts-r14-results-v1", "axes.unicode_minus": False,
    })
    snapshot = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    paths = [args.output_dir / f"r14_sequence_bd_{args.date}.svg",
             args.output_dir / f"r14_qp_bd_{args.date}.svg"]
    partial = [f"{counts[i, j]}/7 at {MODES[i]} / QP{QPS[j]}"
               for i, j in np.ndindex(qp.shape)
               if np.isfinite(qp[i, j]) and counts[i, j] < len(SEQUENCES)]
    coverage_note = ("* Incomplete CE coverage (" + "; ".join(partial)
                     + "); unmarked numeric cells use 7/7."
                     if partial else "Every numeric cell uses all seven CE sequences.")
    draw_heatmap(
        sequence,
        ("Basketball\nDrill [C]", "BQMall [C]", "PartyScene [C]", "RaceHorsesC [C]",
         "FourPeople [E]", "Johnny [E]", "KristenAndSara\n[E]"),
        f"R14 {args.configuration} CE: per-sequence BD-rate | {snapshot}",
        "PCHIP BD-rate per Y/U/V component, then (6Y + U + V) / 8; Current reference.\n"
        "Complete measured four-point curves only. Grey = unavailable; no missing point is filled.\n"
        "Blue = lower rate; red = higher rate. Labels rounded to 0.001%; colour uses full precision.",
        paths[0],
    )
    draw_heatmap(
        qp, tuple(f"QP {q}" for q in QPS),
        f"R14 {args.configuration} CE: QP BD-rate | {snapshot}",
        "Each column replaces only its target QP; the other three points use Current.\n"
        "Y/U/V PCHIP first, then 6:1:1; equal sequence mean. QP columns are not additive.\n"
        + coverage_note + "\n"
        "Grey = missing. Blue = lower rate; red = higher rate. Values in percent.",
        paths[1], counts,
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
