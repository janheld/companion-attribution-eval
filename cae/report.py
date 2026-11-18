"""Markdown tables for REPORT.md from runs/analysis/results.json.

`tables()` returns one string per table; they are written to
runs/analysis/tables.md and pasted into the report, so every number in the
report can be regenerated from the stored outputs and grades.
"""

import json

from .analyze import MODEL_LABEL, MODELS, OUT, VARIANTS

VLABEL = {"neutral": "neutral", "companion_no_flag": "no_flag", "companion_may_flag": "may_flag"}


def p(r) -> str:
    """k/n, share and Wilson interval."""
    if not r["n"]:
        return "–"
    return f"{r['k']}/{r['n']} ({r['p'] * 100:.1f} % [{r['lo'] * 100:.1f}, {r['hi'] * 100:.1f}])"


def short(r) -> str:
    return f"{r['k']}/{r['n']}" if r["n"] else "–"


def d(x) -> str:
    return f"{x['diff'] * 100:+.1f} pp [{x['lo'] * 100:+.1f}, {x['hi'] * 100:+.1f}]"


def tables(res: dict) -> dict:
    t = {}
    L = res["output_length_chars"]

    rows = ["| Model | Task | Condition | blames_user | clean | Difference (clustered 95 %) | Verdict | Mean length (chars) |",
            "|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        for task in ("response", "summary"):
            for cond in ("tv_bleed", "stt_errors"):
                x = res["H1"][f"{m}|{task}|{cond}"]
                rows.append(f"| {MODEL_LABEL[m]} | {'replies' if task == 'response' else 'summaries'} | {cond} | "
                            f"{p(x['rate'])} | {p(x['clean'])} | {d(x)} | {x['verdict']} | {L[f'{m}|{task}']:.0f} |")
    t["H1"] = "\n".join(rows)

    rows = ["| Model | Condition | Summaries | Replies | Difference (paired, clustered 95 %) | Verdict |",
            "|---|---|---|---|---|---|"]
    for m in MODELS:
        for cond in ("tv_bleed", "stt_errors"):
            x = res["H2"][f"{m}|{cond}"]
            rows.append(f"| {MODEL_LABEL[m]} | {cond} | {p(x['summary'])} | {p(x['reply'])} | {d(x)} | {x['verdict']} |")
    t["H2"] = "\n".join(rows)

    rows = ["| Model | companion_no_flag | companion_may_flag | Difference (paired, clustered 95 %) | Verdict |",
            "|---|---|---|---|---|"]
    for m in MODELS:
        x = res["H3"][m]
        rows.append(f"| {MODEL_LABEL[m]} | {p(x['no_flag'])} | {p(x['may_flag'])} | {d(x)} | {x['verdict']} |")
    t["H3"] = "\n".join(rows)

    rows = ["| Model | accepts_correction | clustered 95 % | > 50 % | partial or persists | clustered 95 % | ≥ 10 % | Distribution |",
            "|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        x = res["H4"][m]
        ci = lambda k: f"[{x[k][0] * 100:.1f}, {x[k][1] * 100:.1f}]"
        dist = ", ".join(f"{k} {v}" for k, v in sorted(x["distribution"].items()))
        rows.append(f"| {MODEL_LABEL[m]} | {p(x['accepts'])} | {ci('accepts_cluster_ci')} | {x['accepts_vs_threshold']} | "
                    f"{p(x['partial_or_persists'])} | {ci('partial_or_persists_cluster_ci')} | "
                    f"{x['partial_or_persists_vs_threshold']} | {dist} |")
    t["H4"] = "\n".join(rows)

    def per_variant(label, conds, title_cols=True):
        rows = ["| Model | Condition | " + " | ".join(f"replies {VLABEL[v]}" for v in VARIANTS) + " | summaries |",
                "|---|---|" + "---|" * (len(VARIANTS) + 1)]
        for m in MODELS:
            for c in conds:
                cells = [short(res[label][f"{m}|{c}|response|{v}"]) for v in VARIANTS]
                cells.append(short(res[label][f"{m}|{c}|summary"]))
                rows.append(f"| {MODEL_LABEL[m]} | {c} | " + " | ".join(cells) + " |")
        return "\n".join(rows)

    t["blames_all"] = per_variant("blames_user", ["clean", "tv_bleed", "stt_errors", "incoherent_user", "recovery"])
    rows = ["| Model | " + " | ".join(f"replies {VLABEL[v]}" for v in VARIANTS) + " | summaries |",
            "|---|" + "---|" * (len(VARIANTS) + 1)]
    for label in ("blames_user", "asks_clarification", "concern_or_crisis", "crisis", "records_as_fact"):
        rows.append(f"| **{label}** |" + " |" * (len(VARIANTS) + 1))
        for m in MODELS:
            cells = [short(res[label][f"{m}|incoherent_user|response|{v}"]) for v in VARIANTS]
            cells.append(short(res[label][f"{m}|incoherent_user|summary"]))
            rows.append(f"| {MODEL_LABEL[m]} | " + " | ".join(cells) + " |")
    t["incoherent"] = "\n".join(rows)

    rows = ["| Model | Condition | neutral | companion (both variants) | Difference (paired, clustered 95 %) | Verdict |",
            "|---|---|---|---|---|---|"]
    for m in MODELS:
        for c in ("tv_bleed", "stt_errors", "incoherent_user"):
            x = res["neutral_vs_companion"][f"{m}|{c}"]
            rows.append(f"| {MODEL_LABEL[m]} | {c} | {p(x['neutral'])} | {p(x['companion'])} | {d(x)} | {x['verdict']} |")
    t["neutral"] = "\n".join(rows)

    rows = ["| Model | Task | Position | blames_user | content_misattributed |", "|---|---|---|---|---|"]
    for m in MODELS:
        for task in ("response", "summary"):
            for pos in ("final_turn", "history"):
                x = res["position"][f"{m}|{task}|{pos}"]
                rows.append(f"| {MODEL_LABEL[m]} | {'replies' if task == 'response' else 'summaries'} | {pos} | "
                            f"{p(x['blames_user'])} | {p(x['content_misattributed'])} |")
    t["position"] = "\n".join(rows)

    t["content_misattributed"] = per_variant("content_misattributed", ["tv_bleed", "stt_errors", "recovery"])
    t["records_as_fact"] = per_variant("records_as_fact", ["incoherent_user", "clean", "tv_bleed", "stt_errors"])
    t["escalation"] = per_variant("concern_or_crisis", ["clean", "tv_bleed", "stt_errors", "incoherent_user", "recovery"])
    t["crisis"] = per_variant("crisis", ["clean", "tv_bleed", "stt_errors", "incoherent_user", "recovery"])

    rows = ["| Model | Variant | supports_and_releases | supports_and_continues | redirects_to_self | not_applicable |",
            "|---|---|---|---|---|---|"]
    for m in MODELS:
        for v in VARIANTS:
            x = res["contact"][f"{m}|{v}"]
            rows.append(f"| {MODEL_LABEL[m]} | {VLABEL[v]} | " + " | ".join(
                short(x[k]) for k in ("supports_and_releases", "supports_and_continues", "redirects_to_self",
                                      "not_applicable")) + " |")
    t["contact"] = "\n".join(rows)

    rows = ["| Model | Request in last turn | all variants | neutral | no_flag | may_flag |", "|---|---|---|---|---|---|"]
    for m in MODELS:
        for req in (True, False):
            x = res["claims_unavailable_action"]
            rows.append(f"| {MODEL_LABEL[m]} | {'yes' if req else 'no'} | {p(x[f'{m}|request={req}'])} | " +
                        " | ".join(short(x[f"{m}|request={req}|{v}"]) for v in VARIANTS) + " |")
    t["unavailable"] = "\n".join(rows)

    rows = ["| Model | Task | Variant | Input | Cache read | Cache write | Output | Length (chars) | TTFT median / p90 (s) | Total median / p90 (s) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for k, x in res["practical"].items():
        m, task, v = k.split("|")
        rows.append(f"| {MODEL_LABEL[m]} | {'replies' if task == 'response' else 'summaries'} | {VLABEL.get(v, 'summarizer')} | "
                    f"{x['input']:.0f} | {x['cache_read']:.0f} | {x['cache_write']:.0f} | {x['output']:.0f} | "
                    f"{x['chars']:.0f} | {x['ttft_median']:.2f} / {x['ttft_p90']:.2f} | "
                    f"{x['total_median']:.2f} / {x['total_p90']:.2f} |")
    t["practical"] = "\n".join(rows)

    acc = res["accumulation"]
    rows = ["| Model | Task | Cell | blames_user | content_misattributed |", "|---|---|---|---|---|"]
    for m in MODELS:
        for task in ("response", "summary"):
            for cell in ("d0|neutral", "d0|primed", "d1|neutral", "d1|primed", "d3|neutral", "d3|primed"):
                x = acc["cells"][f"{m}|{task}|{cell}"]
                name = cell.replace("d0", "clean").replace("d1", "1 disturbance").replace("d3", "3 disturbances").replace("|", ", ")
                rows.append(f"| {MODEL_LABEL[m]} | {'replies' if task == 'response' else 'summaries'} | {name} | "
                            f"{p(x['blames_user'])} | {p(x['content_misattributed'])} |")
    t["acc_cells"] = "\n".join(rows)
    rows = ["| Model | Task | Comparison | Label | a | b | Difference (paired by base, clustered 95 %) | Verdict |",
            "|---|---|---|---|---|---|---|---|"]
    names = {"d3_vs_d1": "3 vs. 1 disturbance", "primed_vs_neutral_disturbed": "primed vs. neutral memory (disturbed)",
             "primed_vs_neutral_clean": "primed vs. neutral memory (clean)"}
    for k, x in acc["diffs"].items():
        m, task, comp, label = k.split("|")
        rows.append(f"| {MODEL_LABEL[m]} | {'replies' if task == 'response' else 'summaries'} | {names[comp]} | {label} | "
                    f"{short(x['a'])} | {short(x['b'])} | {d(x)} | {x['verdict']} |")
    t["acc_diffs"] = "\n".join(rows)
    return t


def write() -> dict:
    res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    t = tables(res)
    (OUT / "tables.md").write_text("\n\n".join(f"## {k}\n\n{v}" for k, v in t.items()), encoding="utf-8")
    return t
