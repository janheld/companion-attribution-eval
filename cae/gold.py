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


def sample(outputs: list[dict], grades: dict, target: int = 140, per_stratum: int = 12,
           seed: int = SEED) -> list[dict]:
    """Hand-written cases and must-include items first, then every stratum
    from the rarest up: rare strata completely, common ones up to
    per_stratum, then plain items. Within each step the next item comes from
    the model with the fewest items so far, so no model dominates."""
    rng = random.Random(seed)
    pool = outputs[:]
    rng.shuffle(pool)
    info = {o["key"]: strata(o, grades.get(o["key"], {}).get("labels", {})) for o in pool}
    chosen = {o["key"]: o for o in pool if o.get("model_name") == "handwritten"}
    chosen.update({o["key"]: o for o in _must_include(pool) if o["key"] not in chosen})
    per_model = Counter(o.get("model_name") for o in chosen.values() if o.get("model_name") != "handwritten")

    def add(candidates: list[dict], limit: int) -> None:
        by_model = defaultdict(list)
        for o in candidates:
            if o["key"] not in chosen:
                by_model[o.get("model_name", "")].append(o)
        added = 0
        while added < limit and len(chosen) < target and any(by_model.values()):
            name = min((m for m in by_model if by_model[m]), key=lambda m: (per_model[m], m))
            o = by_model[name].pop(0)
            chosen[o["key"]] = o
            per_model[name] += 1
            added += 1

    special = Counter(st for o in pool for st in info[o["key"]] if not st.startswith("plain:"))
    for stratum, _ in sorted(special.items(), key=lambda kv: (kv[1], kv[0])):
        add([o for o in pool if stratum in info[o["key"]]], per_stratum)
    # Plain items last, spread over condition x task.
    plain = sorted({info[o["key"]][-1] for o in pool})
    while len(chosen) < target:
        before = len(chosen)
        for stratum in plain:
            add([o for o in pool if info[o["key"]][-1] == stratum], 1)
        if len(chosen) == before:
            break
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


def build(config_paths: list[str], target: int = 140) -> None:
    if ITEMS.exists():
        raise SystemExit(f"{ITEMS.relative_to(ROOT)} exists; the gold set is built once. Delete it on purpose to rebuild.")
    outputs, grades = [], {}
    for path in config_paths:
        cfg = load_run_config(path)
        outputs += load_outputs(cfg["run_id"])
        grades.update(load_grades(cfg["run_id"], cfg["grader"]["name"]))
    items = sample(outputs, grades, target)
    split(items)
    with ITEMS.open("w", encoding="utf-8") as f:
        for i, o in enumerate(sorted(items, key=lambda x: x["key"])):
            item = {"gold_id": f"g{i + 1:03d}", "output_key": o["key"], "run_id": o["run_id"],
                    "model_name": o.get("model_name", ""), "set": o["set"],
                    "scenario_id": o["scenario_id"], "task": o["task"], "text": o["text"],
                    "stratum": o["stratum"], "split": o["split"]}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(items)} gold items: {dict(Counter(o['split'] for o in items))}")
    print(f"models: {dict(Counter(o.get('model_name') for o in items))}")
    print(f"strata: {dict(Counter(o['stratum'] for o in items))}")


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


def evaluate(config_paths: list[str], split_name: str) -> None:
    cfg = load_run_config(config_paths[0])
    if split_name == "heldout" and LOCK.exists():
        raise SystemExit(f"Held-out part was already evaluated ({LOCK.read_text().strip()}). It is used once only.")
    items = [it for it in load_items() if it["split"] == split_name]
    labels = author_labels()
    unlabeled = [it["gold_id"] for it in items if it["gold_id"] not in labels]
    if unlabeled:
        raise SystemExit(f"{len(unlabeled)} {split_name} items not labeled yet: {', '.join(unlabeled[:10])} ...")
    grades = {}
    for run_id in {it["run_id"] for it in items}:
        grades.update(load_grades(run_id, cfg["grader"]["name"]))
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
button{padding:6px 14px}a{color:#2457a6}.done{color:#1a7f37}
.turn{padding:8px 12px;margin:8px 0;border-radius:8px;white-space:pre-wrap;font-size:14px}
.turn.user{background:#fff;border:1px solid #ccc}.turn.assistant{background:#eef3fb;border:1px solid #c9d8ef;margin-left:32px}
.turn b{display:block;margin-bottom:2px}mark{background:#ffd9a8}"""


def turns_html(scenario: dict, show_index: bool = False, marks: dict | None = None) -> str:
    """The conversation as separate boxes per turn, display only: same text and
    speaker labels as render.transcript, which the models and the grader get."""
    content = scenario["content"]
    turns = content["history"] + [{"role": "user", **content["final_user_turn"]}]
    out = []
    for i, t in enumerate(turns):
        text = html.escape(t["text"])
        for span in (marks or {}).get(i, []):
            text = text.replace(html.escape(span), f"<mark>{html.escape(span)}</mark>")
        who = f"Nutzer [{t['timestamp']}]" if t["role"] == "user" else "Mira"
        prefix = f"#{i} " if show_index else ""
        out.append(f"<div class='turn {t['role']}'><b>{prefix}{who}</b>{text}</div>")
    return "".join(out)

# No field is preselected: a default would anchor the author on the most
# common value, which is also the grader's most common answer, and inflate
# agreement on the held-out part. Every field, including not_applicable and
# false, has to be chosen actively; the server refuses incomplete labels.
FLAG_VALUES = ["true", "false"]

# Order of items for this labeling session: shuffled anew at every server
# start, so development and held-out items never come in blocks.
SESSION_ORDER: list[str] = []
SESSIONS_LOG = ROOT / "runs" / "gold_sessions.jsonl"


def grouped_order(items: list[dict], rng) -> list[str]:
    """Items of the same scenario come one after another, so the conversation is
    read once (author's request, 2026-11-09, during the blind pass). Groups are
    shuffled, and so are the items within a group; dev and held-out mix freely."""
    groups = defaultdict(list)
    for it in items:
        groups[(it["set"], it["scenario_id"])].append(it["gold_id"])
    keys = list(groups)
    rng.shuffle(keys)
    order = []
    for k in keys:
        members = groups[k][:]
        rng.shuffle(members)
        order += members
    return order


def _same_as_previous(gold_id: str) -> bool:
    if gold_id not in SESSION_ORDER:
        return False
    i = SESSION_ORDER.index(gold_id)
    if i == 0:
        return False
    items = {it["gold_id"]: it for it in load_items()}
    a, b = items[SESSION_ORDER[i - 1]], items[gold_id]
    return (a["set"], a["scenario_id"]) == (b["set"], b["scenario_id"])


def _ordered(items: list[dict]) -> list[dict]:
    rank = {g: i for i, g in enumerate(SESSION_ORDER)}
    return sorted(items, key=lambda it: rank.get(it["gold_id"], len(rank)))


def _next_unlabeled() -> str | None:
    labels = author_labels()
    return next((it["gold_id"] for it in _ordered(load_items()) if it["gold_id"] not in labels), None)


def _scenarios() -> dict:
    out = {}
    for name in {it["set"] for it in load_items()}:
        out.update({(name, s["id"]): s for s in load_frozen(name)})
    return out


def _page(title: str, body: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style>{body}").encode("utf-8")


def list_page() -> bytes:
    items, labels = _ordered(load_items()), author_labels()
    rows = "".join(f"<li><a href='/g/{it['gold_id']}'>{it['gold_id']}</a> "
                   f"{'<span class=done>✓</span>' if it['gold_id'] in labels else ''}</li>" for it in items)
    todo = _next_unlabeled()
    nxt = f"<p><a href='/g/{todo}'>next unlabeled: {todo}</a></p>" if todo else "<p>All labeled.</p>"
    return _page("Gold labeling", f"<h1>Gold set</h1><p>{len(labels)} of {len(items)} labeled.</p>{nxt}<ul>{rows}</ul>")


def item_page(gold_id: str, error: str = "") -> bytes:
    items = {it["gold_id"]: it for it in load_items()}
    it = items[gold_id]
    s = _scenarios()[(it["set"], it["scenario_id"])]
    current = author_labels().get(gold_id, {}).get("labels", {})
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    fields = []
    # Only a label saved earlier for this item is shown again; nothing else is checked.
    options = {**LABELS, **{flag: FLAG_VALUES for flag in FLAGS}}
    for field, values in options.items():
        chosen = current.get(field)
        chosen = str(chosen).lower() if isinstance(chosen, bool) else chosen
        radios = "".join(f"<label><input type=radio name={field} value={v} required "
                         f"{'checked' if v == chosen else ''}>{v}</label>" for v in values)
        fields.append(f"<fieldset><legend>{field}</legend>{radios}</fieldset>")
    note = html.escape(author_labels().get(gold_id, {}).get("note", ""))
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    if _same_as_previous(gold_id):
        err += "<p style='background:#eef3fb;padding:6px'>Gleiches Gespräch wie beim vorigen Item.</p>"
    body = f"""<p><a href='/'>list</a></p><h1>{gold_id}: {kind}</h1>{err}
<p>Rubric: prompts/grader_rubric.en.md. Condition, model, prompt variant and grader labels are hidden.</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<form method=post action='/g/{gold_id}'>{''.join(fields)}
<p><textarea name=note style='width:100%;height:50px' placeholder='Notiz (optional, z. B. Grenzfall)'>{note}</textarea></p>
<button>Speichern und weiter</button></form>
<h2>Gespräch</h2>{turns_html(s)}
<h2>Gedächtniskontext</h2><pre>{html.escape(render.context_block(s['content']['user_context']))}</pre>"""
    return _page(gold_id, body)


def save_label(gold_id: str, form: dict) -> list[str]:
    """Save a complete label; return the missing fields (nothing saved) otherwise."""
    missing = [f for f in [*LABELS, *FLAGS] if not form.get(f)]
    bad = [f for f in LABELS if form.get(f) and form[f][0] not in LABELS[f]] + \
          [f for f in FLAGS if form.get(f) and form[f][0] not in FLAG_VALUES]
    if missing or bad:
        return missing + bad
    labels = {field: form[field][0] for field in LABELS}
    labels.update({flag: form[flag][0] == "true" for flag in FLAGS})
    row = {"gold_id": gold_id, "labels": labels, "note": form.get("note", [""])[0],
           "labeled_at": datetime.now(timezone.utc).isoformat()}
    with AUTHOR_LABELS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return []


def serve(port: int = 8766) -> None:
    SESSION_ORDER[:] = grouped_order(load_items(), random.SystemRandom())
    # Record when each labeling session started and in which order mode, so the
    # report can say how many labels came before and after grouping.
    SESSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SESSIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(), "order": "grouped_by_scenario"}) + "\n")

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
            missing = save_label(gold_id, parse_qs(self.rfile.read(length).decode("utf-8")))
            if missing:
                return self._send(item_page(gold_id, f"Nicht gespeichert, bitte noch setzen: {', '.join(missing)}"), 400)
            todo = _next_unlabeled()
            self.send_response(303)
            self.send_header("Location", f"/g/{todo}" if todo else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Gold labeling on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
