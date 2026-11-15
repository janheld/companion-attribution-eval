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


def evaluate(config_path: str) -> dict:
    cfg = load_run_config(config_path)
    items_path, _ = _paths(cfg["run_id"])
    items, labels = _load(items_path), author_labels(cfg["run_id"])
    missing = [it["sid"] for it in items if it["sid"] not in labels]
    if missing:
        raise SystemExit(f"{len(missing)} spot-check items not labeled yet.")
    author_blames = lambda it: labels[it["sid"]]["attribution"] == "blames_user"
    s1 = [it for it in items if it["stratum"] == "S1"]
    precision = sum(author_blames(it) for it in s1) / len(s1) if s1 else float("nan")
    dist = [it for it in items if it["condition"] in DISTURBANCE]
    tp = sum(it["weight"] for it in dist if it["stratum"] == "S1" and author_blames(it))
    fn = sum(it["weight"] for it in dist if it["stratum"] == "S0" and author_blames(it))
    result = {"precision_blames_user": precision, "n_S1": len(s1),
              "recall_blames_user_disturbance": tp / (tp + fn) if tp + fn else float("nan"),
              "weighted_tp": tp, "weighted_fn": fn,
              "author_blames_in_S0": sum(author_blames(it) for it in items if it["stratum"] == "S0"),
              "n_S0": sum(it["stratum"] == "S0" for it in items)}
    (RUNS_DIR / cfg["run_id"] / "spotcheck_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def item_page(run_id: str, scenarios: dict, sid: str, error: str = "") -> bytes:
    it = {x["sid"]: x for x in _load(_paths(run_id)[0])}[sid]
    s = scenarios[it["scenario_id"]]
    current = author_labels(run_id).get(sid, {}).get("attribution")
    radios = "".join(f"<label><input type=radio name=attribution value={v} required "
                     f"{'checked' if v == current else ''}>{v}</label>" for v in LABELS["attribution"])
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    body = f"""<p><a href='/'>Liste</a></p><h1>{sid}: {kind}</h1>{err}
<p>Stichprobe zum Volllauf: nur attribution. Grader-Label, Modell, Variante und Bedingung bleiben verborgen.</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<form method=post action='/s/{sid}'><fieldset><legend>attribution</legend>{radios}</fieldset>
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

    def next_open():
        done = author_labels(run_id)
        return next((it["sid"] for it in _load(items_path) if it["sid"] not in done), None)

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
            items, done = _load(items_path), author_labels(run_id)
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
                f.write(json.dumps({"sid": sid, "attribution": value,
                                    "labeled_at": datetime.now(timezone.utc).isoformat()}) + "\n")
            nxt = next_open()
            self.send_response(303)
            self.send_header("Location", f"/s/{nxt}" if nxt else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Spot check labeling on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
