#!/usr/bin/env python3
"""
Figures of the report, drawn from the RAW artifacts of the repository (nothing is typed in by hand except the replay-versus-sync constants that are documented in
`artifacts/experiments/2026-10-08-c4-replay/README.md`). Run from the repository root with a python that has matplotlib:  python3 docs/report/make_figures.py
Colors: the first slots of the validated reference palette of the dataviz skill (blue, orange, aqua), in fixed order; marks are thin; no dual axes.
"""
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures"
EXP = ROOT / "artifacts/experiments"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb"})


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def fig_benchmark():
    data = json.loads((EXP / "2026-10-07-g7-bigchunk/summary-cot_l3_q64-chunk64-vsB0.json").read_text())
    order = [("n24-B0", "B0\n5070 Ti, 1 process", BLUE), ("n24-B0x2", "B0x2\n5070 Ti, 2 processes", BLUE), ("n24-B3x2", "B3x2\n+ 1660S, greedy", ORANGE), ("n24-B4x2", "B4x2\n+ 1660S, tail-aware", ORANGE)]
    steady = {k: [r["T_mean_after_first"] for name, r in data["runs"].items() if name.startswith(k + "-r")] for k, _, _ in order}
    base = statistics.mean(steady["n24-B0"])
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    for i, (key, label, color) in enumerate(order):
        values = steady[key]
        ax.scatter([i] * len(values), values, s=36, color=color, zorder=3, edgecolor="#fcfcfb", linewidth=1.2)
        mean = statistics.mean(values)
        ax.hlines(mean, i - 0.28, i + 0.28, color=color, linewidth=2, zorder=2)
        ax.text(i, mean + 3.2, f"{mean:.1f} s  ({base / mean:.3f}x)", ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(order)), [o[1] for o in order], fontsize=8.5)
    ax.set_ylabel("seconds per generation\n(steady state, 3 runs each)")
    ax.set_ylim(60, 125)
    ax.set_title("Cluster benchmark: 24 candidates, 64 questions, CUDA noise engine, chunk 64", fontsize=10, loc="left")
    ax.scatter([], [], color=BLUE, label="the 5070 Ti alone")
    ax.scatter([], [], color=ORANGE, label="the two machines")
    ax.legend(frameon=False, loc="lower left", fontsize=8.5)
    save(fig, "fig1-cluster-benchmark")


def fig_replay():
    r1 = json.loads((EXP / "2026-10-08-c4-replay/replay-5070ti-lrtA.json").read_text())
    r2 = json.loads((EXP / "2026-10-08-c4-replay/replay-1660s-lrtA.json").read_text())
    med = lambda r: statistics.median(g["apply_seconds"] for g in r["generations"])  # noqa: E731
    sync = 8.55 + 0.51 + 0.74                       # measured on the 1660S: transfer, load, rehash (c4-replay/README.md)
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.4, 3.6), gridspec_kw={"width_ratios": [1, 1.25]})
    labels = ["replay\n5070 Ti", "replay\n1660S", "full sync\n1660S"]
    values = [med(r1), med(r2), sync]
    colors = [BLUE, ORANGE, AQUA]
    a.bar(range(3), values, color=colors, width=0.5)
    for i, v in enumerate(values):
        a.text(i, v + 0.3, f"{v:.1f} s", ha="center", fontsize=9)
    a.set_xticks(range(3), labels, fontsize=8.5)
    a.set_ylabel("seconds to reach the next weights")
    a.set_title("(a) measured, 24 candidates", fontsize=10, loc="left")
    per = med(r2) / 24
    ns = list(range(4, 41))
    b.plot(ns, [per * n for n in ns], color=ORANGE, linewidth=2, label="replay on the 1660S (0.511 s x N)")
    b.axhline(sync, color=AQUA, linewidth=2, label="full sync, gigabit cable (9.8 s)")
    b.axvline(sync / per, color=MUTED, linewidth=1, linestyle=":")
    b.text(sync / per + 0.6, 2, f"break-even N = {sync / per:.0f}", fontsize=8.5, color=MUTED)
    b.scatter([24], [med(r2)], color=ORANGE, zorder=3, s=40)
    b.set_xlabel("candidates per generation, N")
    b.set_ylabel("seconds")
    b.set_title("(b) linear model through the measured point", fontsize=10, loc="left")
    b.legend(frameon=False, fontsize=8.5, loc="upper left")
    save(fig, "fig2-replay-vs-sync")


def load_analysis(run):
    return json.loads((EXP / f"2026-10-07-learning-runtime/analysis-run{run}.json").read_text())


def fig_learning():
    runs = {"A": (BLUE, "run A (alpha 1e-3, 100 gens)"), "B": (ORANGE, "run B (replication)"), "C": (AQUA, "run C (alpha 5e-4, 60 gens)")}
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.6, 3.7), sharey=True)
    for run, (color, label) in runs.items():
        cps = load_analysis(run)["checkpoints"]
        gens = sorted(int(g) for g in cps)
        a.plot(gens, [100 * cps[str(g)]["train"]["accuracy"] for g in gens], color=color, linewidth=1.8, label=label)
        b.plot(gens, [100 * cps[str(g)]["H3"]["accuracy"] for g in gens], color=color, linewidth=1.8, label=label)
    for ax, title in ((a, "(a) the 64 training questions"), (b, "(b) 128 new questions of the same family (H3)")):
        ax.set_xlabel("generation")
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_ylim(20, 100)
    b.axhline(81.2, color=MUTED, linestyle="--", linewidth=1.2)
    b.text(100, 82.4, "base model with 512 tokens: 81.2", ha="right", fontsize=8.5, color=MUTED)
    b.axhline(32.8, color=MUTED, linestyle=":", linewidth=1.2)
    b.text(100, 34, "base model with 256 tokens: 32.8", ha="right", fontsize=8.5, color=MUTED)
    a.set_ylabel("accuracy, % (256-token limit)")
    a.legend(frameon=False, fontsize=8.5, loc="lower right")
    save(fig, "fig3-learning-curves")


def fig_walks():
    fig, ax = plt.subplots(figsize=(6.2, 3.7))
    groups = {}
    for run in "AB":
        a = load_analysis(run)
        walks = json.loads((EXP / f"2026-10-07-learning-runtime/randomwalk-run{run}-from50.json").read_text())["walks"]
        real = 100 * a["checkpoints"]["100"]["train"]["accuracy"]
        groups[run] = [real] + [100 * w["50"]["train"]["accuracy"] for w in walks.values()]
    labels = ["real updates", "shuffled coefficients, walk 1", "shuffled coefficients, walk 2"]
    colors = [BLUE, ORANGE, AQUA]
    width = 0.22
    for j, (label, color) in enumerate(zip(labels, colors)):
        xs = [i + (j - 1) * (width + 0.03) for i in range(2)]
        vals = [groups[run][j] for run in "AB"]
        ax.bar(xs, vals, width=width, color=color, label=label)
        for x, v in zip(xs, vals):
            ax.text(x, v + 1.2, f"{v:.0f}", ha="center", fontsize=8.5)
    ax.set_xticks([0, 1], ["run A", "run B"])
    ax.set_ylabel("training accuracy, %\n(50 generations from checkpoint 50)")
    ax.set_ylim(0, 108)
    ax.set_title("Same noise, same step size: with the rewards, and without", fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1)
    save(fig, "fig4-random-walk-control")


def fig_learning_v2():
    d1 = json.loads((EXP / "2026-10-08-learning-v2/analysis-runD1.json").read_text())["checkpoints"]
    d2 = json.loads((EXP / "2026-10-08-learning-v2/analysis-runD2.json").read_text())["checkpoints"]
    direct = json.loads((EXP / "2026-10-08-direct-answer-probe/direct-lrtD1.json").read_text())["results"]["0"]["direct_prompt"]["accuracy"] * 100
    g1 = sorted(int(g) for g in d1)
    g2 = sorted(int(g) for g in d2)
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 3.7))
    panels = [("H1", "(a) H1: new questions of the training family"), ("H2", "(b) H2: other family (three operands)"), ("H3", "(c) H3: other family (word problems)")]
    for ax, (key, title) in zip(axes, panels):
        ax.plot(g1, [100 * d1[str(g)][key]["accuracy"] for g in g1], color=BLUE, linewidth=1.8, label="run D1 (sigma 1e-3)")
        ax.plot([20 + g for g in g2], [100 * d2[str(g)][key]["accuracy"] for g in g2], color=ORANGE, linewidth=1.8, label="run D2 (from generation 20, sigma 5e-4)")
        ax.axhline(100 * d1["0"][key]["accuracy"], color=MUTED, linestyle="--", linewidth=1.1)
        ax.text(0.98, 100 * d1["0"][key]["accuracy"], "base model", ha="right", va="bottom", fontsize=8.5, color=MUTED, transform=ax.get_yaxis_transform())
        ax.set_ylim(*{"H1": (58, 90), "H2": (80, 98), "H3": (10, 88)}[key])
        ax.set_xlabel("generation")
        ax.set_title(title, fontsize=9.5, loc="left")
    axes[0].axhline(direct, color=MUTED, linestyle=":", linewidth=1.3)
    axes[0].text(0.98, direct, "base model asked for only the integer", ha="right", va="bottom", fontsize=8.5, color=MUTED, transform=axes[0].get_yaxis_transform())
    axes[0].set_ylabel("accuracy, % (512-token limit)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8.5, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.1))
    save(fig, "fig5-learning-v2")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fig_benchmark, fig_replay, fig_learning, fig_walks, fig_learning_v2):
        f()
