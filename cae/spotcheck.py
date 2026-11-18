"""Spot check of the full run's grading (fixed on 2026-11-15, before grading).

After the main run is graded, two strata are drawn with a fixed seed:
- S1: 30 outputs the grader labeled `blames_user` (all of them if fewer),
  from any condition;
- S0: 30 random outputs without `blames_user` from the disturbance
  conditions `tv_bleed` and `stt_errors`, where a missed `blames_user` would
  hurt H1 most.
The two strata are mixed in one random order. The author labels only
`attribution`, blind: no grader label, model, prompt variant or condition name.

Because the strata are sampled at different rates, each item carries the
weight N_stratum / n_stratum. Precision of `blames_user` comes from S1 (all
conditions). Recall is estimated for tv_bleed and stt_errors only, from the
S1 items of those conditions and all of S0, weighted. With few `blames_user`
outputs in the disturbance conditions this recall rests on few cases; the
report gives the counts behind it.
"""

import html
import json
import random
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import gold, render
from .freeze import load_frozen
from .grade import LABELS, load_grades
from .run import RUNS_DIR, load_outputs, load_run_config

SEED = 20261115
N_PER_STRATUM = 30
DISTURBANCE = ("tv_bleed", "stt_errors")


def _paths(run_id: str):
    folder = RUNS_DIR / run_id
    return folder / "spotcheck_items.jsonl", folder / "spotcheck_labels.jsonl"


def draw(config_path: str) -> None:
    cfg = load_run_config(config_path)
    items_path, _ = _paths(cfg["run_id"])
    if items_path.exists():
        raise SystemExit(f"Spot check already drawn: {items_path}")
    grades = load_grades(cfg["run_id"], cfg["grader"]["name"])
    outputs = [o for o in load_outputs(cfg["run_id"]) if "error" not in grades[o["key"]]["labels"]]
    blamed = lambda o: grades[o["key"]]["labels"]["attribution"] == "blames_user"
    pop1 = sorted((o for o in outputs if blamed(o)), key=lambda o: o["key"])
    pop0 = sorted((o for o in outputs if not blamed(o) and o["condition"] in DISTURBANCE), key=lambda o: o["key"])
    rng = random.Random(SEED)
    s1 = rng.sample(pop1, min(N_PER_STRATUM, len(pop1)))
    s0 = rng.sample(pop0, min(N_PER_STRATUM, len(pop0)))
    rows = ([{"stratum": "S1", "weight": len(pop1) / len(s1), "output": o} for o in s1] +
            [{"stratum": "S0", "weight": len(pop0) / len(s0), "output": o} for o in s0])
    rng.shuffle(rows)
    with items_path.open("w", encoding="utf-8") as f:
        for i, r in enumerate(rows):
            o = r["output"]
            f.write(json.dumps({"sid": f"s{i + 1:02d}", "stratum": r["stratum"], "weight": r["weight"],
                                "output_key": o["key"], "scenario_id": o["scenario_id"], "condition": o["condition"],
                                "task": o["task"], "text": o["text"]}, ensure_ascii=False) + "\n")
    print(f"Drew {len(s1)} of {len(pop1)} blames_user and {len(s0)} of {len(pop0)} other disturbance outputs "
          f"into {items_path.relative_to(RUNS_DIR.parent)}")


def _load(path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def author_labels(run_id: str) -> dict:
    return {r["sid"]: r for r in _load(_paths(run_id)[1])}


def _recall(items: list[dict], author_blames) -> float:
    """Weighted recall of blames_user in tv_bleed and stt_errors."""
    tp = sum(it["weight"] for it in items if it["condition"] in DISTURBANCE and it["stratum"] == "S1" and author_blames(it))
    fn = sum(it["weight"] for it in items if it["condition"] in DISTURBANCE and it["stratum"] == "S0" and author_blames(it))
    return tp / (tp + fn) if tp + fn else float("nan")


def evaluate(config_path: str, n_boot: int = 2000) -> dict:
    """Precision from S1 (equal weights, Wilson interval); recall weighted by
    stratum size over sample size, with an interval from resampling items
    within each stratum (the strata were sampled separately)."""
    from . import stats
    cfg = load_run_config(config_path)
    items_path, _ = _paths(cfg["run_id"])
    items, labels = _load(items_path), author_labels(cfg["run_id"])
    missing = [it["sid"] for it in items if it["sid"] not in labels]
    if missing:
        raise SystemExit(f"{len(missing)} spot-check items not labeled yet.")
    author_blames = lambda it: labels[it["sid"]]["attribution"] == "blames_user"
    s1 = [it for it in items if it["stratum"] == "S1"]
    s0 = [it for it in items if it["stratum"] == "S0"]
    k1 = sum(author_blames(it) for it in s1)
    precision, p_lo, p_hi = stats.wilson(k1, len(s1))
    recall = _recall(items, author_blames)
    rng = random.Random(SEED)
    boots = sorted(r for r in (_recall([rng.choice(s1) for _ in s1] + [rng.choice(s0) for _ in s0], author_blames)
                               for _ in range(n_boot)) if r == r)
    r_lo, r_hi = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]) if boots else (float("nan"),) * 2
    s1_dist = [it for it in s1 if it["condition"] in DISTURBANCE]
    # With no miss in S0 the bootstrap interval collapses to [1, 1]. A
    # conservative lower bound uses the Wilson lower bound of the share of
    # true blames_user among grader blames_user in tv_bleed/stt_errors and the
    # Wilson upper bound of the miss rate in S0, scaled to the populations.
    grades = load_grades(cfg["run_id"], cfg["grader"]["name"])
    outputs = load_outputs(cfg["run_id"])
    pop1_dist = sum(1 for o in outputs if o["condition"] in DISTURBANCE
                    and grades[o["key"]]["labels"].get("attribution") == "blames_user")
    pop0 = sum(1 for o in outputs if o["condition"] in DISTURBANCE
               and grades[o["key"]]["labels"].get("attribution") != "blames_user")
    k1d = sum(author_blames(it) for it in s1_dist)
    k0 = sum(author_blames(it) for it in s0)
    tp_low = stats.wilson(k1d, len(s1_dist))[1] * pop1_dist if s1_dist else 0.0
    fn_high = stats.wilson(k0, len(s0))[2] * pop0
    recall_floor = tp_low / (tp_low + fn_high) if tp_low + fn_high else float("nan")
    result = {
        "precision_blames_user": precision, "precision_ci95": [p_lo, p_hi],
        "recall_blames_user_disturbance_weighted": recall, "recall_ci95_bootstrap": [r_lo, r_hi],
        "recall_conservative_lower_bound": recall_floor,
        "populations": {"grader_blames_user_in_tv_bleed_stt_errors": pop1_dist, "other_tv_bleed_stt_errors": pop0},
        "counts": {"S1_n": len(s1), "S1_author_blames": k1,
                   "S1_in_tv_bleed_stt_errors_n": len(s1_dist),
                   "S1_in_tv_bleed_stt_errors_author_blames": sum(author_blames(it) for it in s1_dist),
                   "S0_n": len(s0), "S0_author_blames": sum(author_blames(it) for it in s0),
                   "weight_S1": s1[0]["weight"] if s1 else None, "weight_S0": s0[0]["weight"] if s0 else None},
        "author_attribution_by_stratum": {st: dict(Counter(
            labels[it["sid"]]["attribution"] for it in items if it["stratum"] == st)) for st in ("S1", "S0")},
    }
    (RUNS_DIR / cfg["run_id"] / "spotcheck_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


# Labeling order (author's request, 2026-11-15): items of the same scenario
# come one after another, so the conversation is read once; groups and the
# order within groups are random, strata mix freely. Set at server start.
SESSION_ORDER: list[str] = []


def grouped_order(items: list[dict], rng) -> list[str]:
    groups = {}
    for it in items:
        groups.setdefault(it["scenario_id"], []).append(it["sid"])
    keys = sorted(groups)
    rng.shuffle(keys)
    order = []
    for k in keys:
        members = groups[k][:]
        rng.shuffle(members)
        order += members
    return order


def _same_as_previous(items: dict, sid: str) -> bool:
    if sid not in SESSION_ORDER or SESSION_ORDER.index(sid) == 0:
        return False
    prev = SESSION_ORDER[SESSION_ORDER.index(sid) - 1]
    return items[prev]["scenario_id"] == items[sid]["scenario_id"]


def _ordered(items: list[dict]) -> list[dict]:
    rank = {sid: i for i, sid in enumerate(SESSION_ORDER)}
    return sorted(items, key=lambda it: rank.get(it["sid"], len(rank)))


def item_page(run_id: str, scenarios: dict, sid: str, error: str = "") -> bytes:
    by_sid = {x["sid"]: x for x in _load(_paths(run_id)[0])}
    it = by_sid[sid]
    s = scenarios[it["scenario_id"]]
    saved = author_labels(run_id).get(sid, {})
    current = saved.get("attribution")
    note = html.escape(saved.get("note", ""))
    radios = "".join(f"<label><input type=radio name=attribution value={v} required "
                     f"{'checked' if v == current else ''}>{v}</label>" for v in LABELS["attribution"])
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    if _same_as_previous(by_sid, sid):
        err += "<p style='background:#eef3fb;padding:6px'>Gleiches Gespräch wie beim vorigen Item.</p>"
    body = f"""<p><a href='/'>Liste</a></p><h1>{sid}: {kind}</h1>{err}
<p>Stichprobe zum Volllauf: nur attribution. Grader-Label, Modell, Variante und Bedingung bleiben verborgen.</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<form method=post action='/s/{sid}'><fieldset><legend>attribution</legend>{radios}</fieldset>
<p><textarea name=note style='width:100%;height:50px' placeholder='Notiz (optional, z. B. Grenzfall)'>{note}</textarea></p>
<button>Speichern und weiter</button></form>
<h2>Gespräch</h2>{gold.turns_html(s)}
<h2>Gedächtniskontext</h2><pre>{html.escape(render.context_block(s['content']['user_context']))}</pre>"""
    return gold._page(sid, body)


def serve(config_path: str, port: int = 8769) -> None:
    cfg = load_run_config(config_path)
    run_id = cfg["run_id"]
    items_path, labels_path = _paths(run_id)
    if not items_path.exists():
        raise SystemExit("Draw the spot check first.")
    scenarios = {s["id"]: s for s in load_frozen(cfg["set"])}
    SESSION_ORDER[:] = grouped_order(_load(items_path), random.SystemRandom())

    def next_open():
        done = author_labels(run_id)
        return next((it["sid"] for it in _ordered(_load(items_path)) if it["sid"] not in done), None)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith("/s/"):
                return self._send(item_page(run_id, scenarios, path[3:]))
            items, done = _ordered(_load(items_path)), author_labels(run_id)
            nxt = next_open()
            link = f"<p><a href='/s/{nxt}'>nächstes offenes Item: {nxt}</a></p>" if nxt else "<p>Alle gelabelt.</p>"
            rows = "".join(f"<li><a href='/s/{it['sid']}'>{it['sid']}</a> {'✓' if it['sid'] in done else ''}</li>"
                           for it in items)
            self._send(gold._page("Stichprobe", f"<h1>Stichprobe</h1><p>{len(done)} von {len(items)}</p>{link}<ul>{rows}</ul>"))

        def do_POST(self):
            sid = urlparse(self.path).path[3:]
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
            value = (form.get("attribution") or [""])[0]
            if value not in LABELS["attribution"]:
                return self._send(item_page(run_id, scenarios, sid, "Bitte attribution setzen."), 400)
            with labels_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"sid": sid, "attribution": value, "note": form.get("note", [""])[0],
                                    "labeled_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n")
            nxt = next_open()
            self.send_response(303)
            self.send_header("Location", f"/s/{nxt}" if nxt else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Spot check labeling on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
