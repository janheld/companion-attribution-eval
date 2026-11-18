"""Figures for the report (SVG and PNG in figures/).

Colors: the first three slots of a categorical palette validated for colour
vision deficiency, one per model in a fixed order; values and labels in text
colours, never in the series colour.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .schema import ROOT  # noqa: E402

FIGURES = ROOT / "figures"
MODELS = ["haiku-4-5", "haiku-5-5", "sonnet-5-5"]
LABEL = {"haiku-4-5": "Haiku 4.5", "haiku-5-5": "Haiku 5.5", "sonnet-5-5": "Sonnet 5.5"}
COLOR = {"haiku-4-5": "#2a78d6", "haiku-5-5": "#eb6834", "sonnet-5-5": "#1baf7a"}
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _bars(ax, groups, get, title):
    """Grouped bars: one group per x label, one bar per model, Wilson error bars."""
    width = 0.26
    for i, m in enumerate(MODELS):
        xs, ps, errs = [], [], [[], []]
        for j, g in enumerate(groups):
            r = get(m, g)
            xs.append(j + (i - 1) * (width + 0.02))
            ps.append(r["p"])
            errs[0].append(r["p"] - r["lo"])
            errs[1].append(r["hi"] - r["p"])
        ax.bar(xs, ps, width, color=COLOR[m], label=LABEL[m], edgecolor=SURFACE, linewidth=1)
        ax.errorbar(xs, ps, yerr=errs, fmt="none", ecolor=TEXT2, elinewidth=1, capsize=2)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g.replace("_", "\n") for g in groups], color=TEXT, fontsize=9)
    ax.set_title(title, color=TEXT, fontsize=10, loc="left")
    _style(ax)


def _save(fig, name):
    FIGURES.mkdir(exist_ok=True)
    for ext in ("svg", "png"):
        fig.savefig(FIGURES / f"{name}.{ext}", dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def draw(res: dict) -> None:
    conds = ["clean", "tv_bleed", "stt_errors", "incoherent_user", "recovery"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True, facecolor=SURFACE)
    _bars(axes[0], conds, lambda m, c: res["blames_user"][f"{m}|{c}|response|all"],
          "Replies (three prompt variants pooled)")
    _bars(axes[1], conds, lambda m, c: res["blames_user"][f"{m}|{c}|summary"], "Summaries")
    axes[0].set_ylabel("share blames_user (95 % Wilson)", color=TEXT2, fontsize=9)
    axes[0].set_ylim(0, 0.5)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
    _save(fig, "blames_user_main")

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True, facecolor=SURFACE)
    cells = ["d0|neutral", "d0|primed", "d1|neutral", "d1|primed", "d3|neutral", "d3|primed"]
    names = ["clean,\nneutral", "clean,\nprimed", "1 dist.,\nneutral", "1 dist.,\nprimed", "3 dist.,\nneutral",
             "3 dist.,\nprimed"]
    for ax, task, label, title in ((axes[0], "response", "blames_user", "blames_user, replies"),
                                   (axes[1], "summary", "content_misattributed", "content_misattributed, summaries")):
        _bars(ax, cells, lambda m, c, task=task, label=label: res["accumulation"]["cells"][f"{m}|{task}|{c}"][label],
              f"Accumulation set: {title}")
        ax.set_xticklabels(names, color=TEXT, fontsize=8)
    axes[0].set_ylabel("share (95 % Wilson)", color=TEXT2, fontsize=9)
    axes[0].set_ylim(0, 1)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
    _save(fig, "accumulation")

    fig, ax = plt.subplots(figsize=(6, 3.4), facecolor=SURFACE)
    _bars(ax, ["accepts", "partial_or_persists"], lambda m, k: res["H4"][m][k], "Recovery replies (H4)")
    ax.set_xticklabels(["accepts_correction", "partial or persists"], color=TEXT, fontsize=9)
    ax.axhline(0.5, color=TEXT2, linestyle="--", linewidth=0.8)
    ax.axhline(0.10, color=TEXT2, linestyle=":", linewidth=0.8)
    ax.set_ylim(0, 1)
    ax.set_ylabel("share (95 % Wilson)", color=TEXT2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper right")
    _save(fig, "recovery_h4")
