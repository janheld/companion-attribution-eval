"""Gold set for grader validation: sampling, blind labeling, split, evaluation.

- `build` samples 100 to 150 dry-run outputs, stratified by the grader's
  preliminary labels, task, condition and a keyword heuristic, because a random
  sample would hold too few `blames_user` cases to say anything. The split into
  development and held-out (60/40, fixed seed, stratified by the same strata)
  is fixed here, before anyone labels.
- `serve` is the labeling page. It never loads grades, and it hides condition,
  model and prompt variant, so the author labels blind.
- `evaluate` compares author and grader. The development part can be
  evaluated as often as needed while the rubric is sharpened. The held-out part
  is evaluated exactly once: the first evaluation writes gold/heldout.lock with
  the rubric hash, and later attempts refuse.
"""

import hashlib
import html
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import yaml

from . import render, stats
from .freeze import load_frozen
from .grade import FLAGS, LABELS, RUBRIC, load_grades
from .run import load_outputs, load_run_config
from .schema import ROOT

GOLD_DIR = ROOT / "gold"
ITEMS = GOLD_DIR / "items.jsonl"
AUTHOR_LABELS = GOLD_DIR / "labels.jsonl"
LOCK = GOLD_DIR / "heldout.lock"
KEYWORDS = re.compile(r"durcheinander|verwirr|wirr|arzt|ärzt|fernseh|radio|undeutlich|verstanden", re.I)
HELDOUT_SHARE = 0.4
SEED = 7


# --- Sampling ---------------------------------------------------------------

def strata(output: dict, labels: dict) -> list[str]:
    """Why an output is interesting for validation, rarest reasons first."""
    s = []
    if labels.get("attribution") and labels["attribution"] != "ignores":
        s.append(f"attribution:{labels['attribution']}")
    for flag in FLAGS:
        if labels.get(flag):
            s.append(flag)
    if labels.get("escalation") in ("concern", "crisis"):
        s.append(f"escalation:{labels['escalation']}")
    for key in ("recovery", "contact"):
        if labels.get(key) not in (None, "not_applicable"):
            s.append(f"{key}:{labels[key]}")
    if KEYWORDS.search(output["text"]):
        s.append("keyword")
    s.append(f"plain:{output['condition']}:{output['task']}")
    return s


def _must_include(outputs: list[dict]) -> list[dict]:
    cfg = yaml.safe_load((GOLD_DIR / "must_include.yaml").read_text(encoding="utf-8"))
    wanted = {(m["set"], m["id"]) for m in cfg.get("scenarios", [])}
    picked, seen = [], set()
    for o in outputs:
        if (o["set"], o["scenario_id"]) in wanted and (o["scenario_id"], o["task"]) not in seen:
            picked.append(o)
            seen.add((o["scenario_id"], o["task"]))
    return picked


def sample(outputs: list[dict], grades: dict, target: int = 130, per_stratum: int = 20,
           seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    pool = outputs[:]
    rng.shuffle(pool)
    info = {o["key"]: strata(o, grades.get(o["key"], {}).get("labels", {})) for o in pool}
    chosen = {o["key"]: o for o in _must_include(pool)}
    counts = Counter(info[o["key"]][0] for o in pool)
    # Rare strata first, each up to per_stratum, then fill up across conditions.
    for stratum, _ in sorted(counts.items(), key=lambda kv: kv[1]):
        members = [o for o in pool if stratum in info[o["key"]] and o["key"] not in chosen]
        for o in members[:per_stratum]:
            if len(chosen) < target:
                chosen[o["key"]] = o
    for o in pool:
        if len(chosen) >= target:
            break
        chosen.setdefault(o["key"], o)
    return [dict(o, stratum=info[o["key"]][0]) for o in chosen.values()]


def split(items: list[dict], seed: int = SEED) -> None:
    """Assign dev / heldout per stratum, 60/40, in place."""
    rng = random.Random(seed + 1)
    by_stratum = defaultdict(list)
    for it in items:
        by_stratum[it["stratum"]].append(it)
    for members in by_stratum.values():
        rng.shuffle(members)
        n_held = round(len(members) * HELDOUT_SHARE)
        for i, it in enumerate(members):
            it["split"] = "heldout" if i < n_held else "dev"


def build(config_path: str, target: int = 130) -> None:
    if ITEMS.exists():
        raise SystemExit(f"{ITEMS.relative_to(ROOT)} exists; the gold set is built once. Delete it on purpose to rebuild.")
    cfg = load_run_config(config_path)
    outputs = load_outputs(cfg["run_id"])
    grades = load_grades(cfg["run_id"], cfg["grader"]["name"])
    items = sample(outputs, grades, target)
    split(items)
    with ITEMS.open("w", encoding="utf-8") as f:
        for i, o in enumerate(sorted(items, key=lambda x: x["key"])):
            item = {"gold_id": f"g{i + 1:03d}", "output_key": o["key"], "run_id": o["run_id"], "set": o["set"],
                    "scenario_id": o["scenario_id"], "task": o["task"], "text": o["text"],
                    "stratum": o["stratum"], "split": o["split"]}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(items)} gold items: {Counter(o['split'] for o in items)}; strata: {Counter(o['stratum'] for o in items)}")


def load_items() -> list[dict]:
    if not ITEMS.exists():
        raise SystemExit("No gold set yet: run `cae gold build` first.")
    return [json.loads(l) for l in ITEMS.read_text(encoding="utf-8").splitlines() if l.strip()]


def author_labels() -> dict:
    """Latest label per gold item (the file is append-only, so changes stay traceable)."""
    if not AUTHOR_LABELS.exists():
        return {}
    out = {}
    for line in AUTHOR_LABELS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["gold_id"]] = row
    return out


# --- Evaluation -------------------------------------------------------------

def compare(pairs: list[tuple[dict, dict]]) -> dict:
    """pairs: (author labels, grader labels). Per field: kappa, confusion and
    precision / recall / FPR per value."""
    result = {}
    for field in [*LABELS, *FLAGS]:
        gold = [a[field] for a, g in pairs if field in a and field in g]
        pred = [g[field] for a, g in pairs if field in a and field in g]
        if not gold:
            continue
        values = LABELS.get(field, [True, False])
        result[field] = {
            "n": len(gold),
            "kappa": stats.cohens_kappa(gold, pred) if len(set(gold) | set(pred)) > 1 else float("nan"),
            "confusion": stats.confusion(gold, pred),
            "per_value": {str(v): stats.binary_scores(gold, pred, v) for v in values},
        }
    return result


def _rubric_sha() -> str:
    return hashlib.sha256(RUBRIC.read_bytes()).hexdigest()


def evaluate(config_path: str, split_name: str) -> None:
    cfg = load_run_config(config_path)
    if split_name == "heldout" and LOCK.exists():
        raise SystemExit(f"Held-out part was already evaluated ({LOCK.read_text().strip()}). It is used once only.")
    items = [it for it in load_items() if it["split"] == split_name]
    labels = author_labels()
    unlabeled = [it["gold_id"] for it in items if it["gold_id"] not in labels]
    if unlabeled:
        raise SystemExit(f"{len(unlabeled)} {split_name} items not labeled yet: {', '.join(unlabeled[:10])} ...")
    grades = load_grades(cfg["run_id"], cfg["grader"]["name"])
    pairs = [(labels[it["gold_id"]]["labels"], grades[it["output_key"]]["labels"]) for it in items]
    result = compare(pairs)
    out = GOLD_DIR / f"eval_{split_name}.json"
    out.write_text(json.dumps({"split": split_name, "n": len(items), "rubric_sha256": _rubric_sha(),
                               "evaluated_at": datetime.now(timezone.utc).isoformat(), "result": result},
                              indent=2, default=str) + "\n", encoding="utf-8")
    if split_name == "heldout":
        LOCK.write_text(f"evaluated {datetime.now(timezone.utc).isoformat()} rubric {_rubric_sha()}\n")
    print_result(result)
    print(f"written to {out.relative_to(ROOT)}")


def print_result(result: dict) -> None:
    for field, r in result.items():
        print(f"\n{field}  (n={r['n']}, kappa={r['kappa']:.2f})")
        for value, s in r["per_value"].items():
            if s["tp"] + s["fn"] + s["fp"]:
                print(f"  {value:24s} precision {s['precision']:.2f}  recall {s['recall']:.2f}  "
                      f"FPR {s['fpr']:.2f}  (tp {s['tp']}, fp {s['fp']}, fn {s['fn']})")
        print(f"  confusion (author -> grader): {r['confusion']}")


# --- Labeling page ----------------------------------------------------------

CSS = """body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#fafaf7;color:#222;line-height:1.45}
pre{white-space:pre-wrap;background:#fff;border:1px solid #ddd;padding:10px;font-size:13px}
.out{background:#fff8e6;border:2px solid #c47f00;padding:10px;white-space:pre-wrap}
fieldset{margin:8px 0;border:1px solid #ccc}label{display:inline-block;margin-right:14px}
button{padding:6px 14px}a{color:#2457a6}.done{color:#1a7f37}"""

DEFAULTS = {"attribution": "ignores", "escalation": "none", "contact": "not_applicable",
            "recovery": "not_applicable"}


def _scenarios() -> dict:
    out = {}
    for name in {it["set"] for it in load_items()}:
        out.update({(name, s["id"]): s for s in load_frozen(name)})
    return out


def _page(title: str, body: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style>{body}").encode("utf-8")


def list_page() -> bytes:
    items, labels = load_items(), author_labels()
    rows = "".join(f"<li><a href='/g/{it['gold_id']}'>{it['gold_id']}</a> "
                   f"{'<span class=done>✓</span>' if it['gold_id'] in labels else ''}</li>" for it in items)
    todo = next((it["gold_id"] for it in items if it["gold_id"] not in labels), None)
    nxt = f"<p><a href='/g/{todo}'>next unlabeled: {todo}</a></p>" if todo else "<p>All labeled.</p>"
    return _page("Gold labeling", f"<h1>Gold set</h1><p>{len(labels)} of {len(items)} labeled.</p>{nxt}<ul>{rows}</ul>")


def item_page(gold_id: str) -> bytes:
    items = {it["gold_id"]: it for it in load_items()}
    it = items[gold_id]
    s = _scenarios()[(it["set"], it["scenario_id"])]
    current = author_labels().get(gold_id, {}).get("labels", {})
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    fields = []
    for field, values in LABELS.items():
        chosen = current.get(field, DEFAULTS[field])
        radios = "".join(f"<label><input type=radio name={field} value={v} {'checked' if v == chosen else ''}>{v}</label>"
                         for v in values)
        fields.append(f"<fieldset><legend>{field}</legend>{radios}</fieldset>")
    for flag in FLAGS:
        fields.append(f"<fieldset><legend>{flag}</legend><label><input type=checkbox name={flag} value=1 "
                      f"{'checked' if current.get(flag) else ''}>true</label></fieldset>")
    note = html.escape(author_labels().get(gold_id, {}).get("note", ""))
    body = f"""<p><a href='/'>list</a></p><h1>{gold_id}: {kind}</h1>
<p>Rubric: prompts/grader_rubric.en.md. Condition, model, prompt variant and grader labels are hidden.</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<form method=post action='/g/{gold_id}'>{''.join(fields)}
<p><textarea name=note style='width:100%;height:50px' placeholder='Notiz (optional, z. B. Grenzfall)'>{note}</textarea></p>
<button>Speichern und weiter</button></form>
<h2>Gespräch</h2><pre>{html.escape(render.transcript(s))}</pre>
<h2>Gedächtniskontext</h2><pre>{html.escape(render.context_block(s['content']['user_context']))}</pre>"""
    return _page(gold_id, body)


def save_label(gold_id: str, form: dict) -> None:
    labels = {field: form.get(field, [DEFAULTS[field]])[0] for field in LABELS}
    labels.update({flag: flag in form for flag in FLAGS})
    row = {"gold_id": gold_id, "labels": labels, "note": form.get("note", [""])[0],
           "labeled_at": datetime.now(timezone.utc).isoformat()}
    with AUTHOR_LABELS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def serve(port: int = 8766) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self._send(list_page())
            if path.startswith("/g/"):
                return self._send(item_page(path[3:]))
            self._send(b"not found", 404)

        def do_POST(self):
            gold_id = urlparse(self.path).path[3:]
            length = int(self.headers.get("Content-Length", 0))
            save_label(gold_id, parse_qs(self.rfile.read(length).decode("utf-8")))
            items, labels = load_items(), author_labels()
            todo = next((it["gold_id"] for it in items if it["gold_id"] not in labels), None)
            self.send_response(303)
            self.send_header("Location", f"/g/{todo}" if todo else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Gold labeling on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
