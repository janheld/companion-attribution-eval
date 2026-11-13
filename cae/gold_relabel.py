"""Third gold pass: adapt the gold labels to the sharpened rubric (v2).

The rubric was sharpened on the development part. Some definitions changed
(asks_clarification, recovery for summaries, content_misattributed, contact,
claims_unavailable_action) and one field is new (records_as_fact). Gold labels
written under the old definitions would then measure the grader against rules
it no longer has. So the author goes over all 140 items once more:

- dev and held-out mixed, in random order grouped by scenario; split, model,
  prompt variant and grader labels are never shown. For held-out items this
  pass happens without any look at grader results.
- the changed fields are prefilled with the current gold value (blind label,
  content_misattributed from the second pass); records_as_fact starts empty
  and must be set.
- answers go to gold/labels_v2.jsonl (append-only); labels.jsonl and
  labels_annotated.jsonl stay unchanged. Every row records which fields
  changed against the previous gold value, old and new.
- from then on labels_v2 is the gold reference for grader validation.
"""

import html
import json
import random
import re
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import gold, gold_annotated, render
from .grade import FLAGS, LABELS, RUBRIC

V2 = gold.GOLD_DIR / "labels_v2.jsonl"
EDITABLE = ["attribution", "recovery", "content_misattributed", "contact", "claims_unavailable_action"]
NEW = ["records_as_fact"]
RUBRIC_SECTIONS = ["attribution", "recovery", "content_misattributed", "records_as_fact", "contact",
                   "claims_unavailable_action"]
SESSION_ORDER: list[str] = []


def relabeled() -> dict:
    """Latest third-pass row per gold item."""
    if not V2.exists():
        return {}
    out = {}
    for line in V2.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["gold_id"]] = row
    return out


def previous_gold() -> dict:
    """Gold before this pass: blind labels, content_misattributed from the second pass."""
    return gold_annotated.reference_labels()


def reference_labels() -> dict:
    """Gold for validation after rubric v2: the third-pass labels."""
    return {gid: {"gold_id": gid, "labels": row["labels"], "note": row.get("note", "")}
            for gid, row in relabeled().items()}


def _values(field: str) -> list[str]:
    return LABELS[field] if field in LABELS else ["true", "false"]


def _str(v) -> str:
    return str(v).lower() if isinstance(v, bool) else str(v)


def save(gold_id: str, form: dict) -> list[str]:
    """Save a complete third-pass label; return the problem fields (nothing saved) otherwise."""
    bad = [f for f in EDITABLE + NEW if (form.get(f) or [""])[0] not in _values(f)]
    if bad:
        return bad
    old = previous_gold()[gold_id]["labels"]
    labels = dict(old)   # escalation and anything else not editable is carried over
    for f in EDITABLE + NEW:
        v = form[f][0]
        labels[f] = (v == "true") if f in FLAGS else v
    changes = {f: {"old": old[f], "new": labels[f]} for f in EDITABLE if labels[f] != old.get(f)}
    row = {"gold_id": gold_id, "labels": labels, "changes": changes, "note": form.get("note", [""])[0],
           "rubric_sha256": gold._rubric_sha(), "labeled_at": datetime.now(timezone.utc).isoformat()}
    with V2.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return []


def change_counts() -> dict:
    """Per field, how many items changed against the previous gold (latest row per item)."""
    rows = relabeled()
    counts = Counter(f for row in rows.values() for f in row["changes"])
    return {"items": len(rows), "changed_per_field": {f: counts.get(f, 0) for f in EDITABLE},
            "records_as_fact_true": sum(row["labels"]["records_as_fact"] is True for row in rows.values())}


def rubric_sections() -> str:
    """The rubric sections whose definitions changed or are new, for reading alongside."""
    text = RUBRIC.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^### ", text)
    out = []
    for p in parts[1:]:
        name = p.split()[0]
        if name in RUBRIC_SECTIONS:
            out.append(f"<details><summary>{html.escape(name)}</summary><pre>### {html.escape(p.strip())}</pre></details>")
    return "".join(out)


def _marks(scenario: dict) -> dict:
    spans = {}
    for d in scenario["annotation"].get("disturbances", []):
        spans.setdefault(d["turn_index"], []).append(d["span"])
    return spans


def item_page(gold_id: str, error: str = "") -> bytes:
    it = {x["gold_id"]: x for x in gold.load_items()}[gold_id]
    s = gold._scenarios()[(it["set"], it["scenario_id"])]
    old = previous_gold()[gold_id]["labels"]
    saved = relabeled().get(gold_id, {}).get("labels", {})
    fields = []
    for f in EDITABLE + NEW:
        chosen = _str(saved[f]) if f in saved else (_str(old[f]) if f in EDITABLE else None)
        radios = "".join(f"<label><input type=radio name={f} value={v} required "
                         f"{'checked' if v == chosen else ''}>{v}</label>" for v in _values(f))
        hint = f" <small>(bisher: {html.escape(_str(old[f]))})</small>" if f in EDITABLE else " <small>(neu, bitte setzen)</small>"
        fields.append(f"<fieldset><legend>{f}{hint}</legend>{radios}</fieldset>")
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    note = html.escape(relabeled().get(gold_id, {}).get("note", ""))
    blind_note = gold.author_labels().get(gold_id, {}).get("note") or "–"
    second_note = gold_annotated.annotated_labels().get(gold_id, {}).get("note") or "–"
    body = f"""<p><a href='/'>Liste</a></p><h1>{gold_id}: {kind}</h1>{err}
<p>Dritter Durchgang nach Rubrik v2. Vorbelegt ist dein bisheriger Gold-Wert; records_as_fact ist neu.
Modell, Variante, Split und Grader-Labels bleiben verborgen. escalation bleibt unverändert ({html.escape(_str(old['escalation']))}).</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<form method=post action='/g/{gold_id}'>{''.join(fields)}
<p><textarea name=note style='width:100%;height:50px' placeholder='Notiz (optional)'>{note}</textarea></p>
<button>Speichern und weiter</button></form>
<details><summary>Deine bisherigen Notizen</summary><p>Blind: {html.escape(blind_note)}</p><p>Zweiter Durchgang: {html.escape(second_note)}</p></details>
<h2>Geänderte Rubrik-Abschnitte (v2)</h2>{rubric_sections()}
<h2>Gespräch (Störstellen markiert)</h2>{gold.turns_html(s, show_index=True, marks=_marks(s))}
<h2>Gedächtniskontext</h2><pre>{html.escape(render.context_block(s['content']['user_context']))}</pre>"""
    return gold._page(gold_id, body)


def _ordered() -> list[dict]:
    rank = {g: i for i, g in enumerate(SESSION_ORDER)}
    return sorted(gold.load_items(), key=lambda it: rank.get(it["gold_id"], len(rank)))


def _next_open() -> str | None:
    done = relabeled()
    return next((it["gold_id"] for it in _ordered() if it["gold_id"] not in done), None)


def list_page() -> bytes:
    done, items = relabeled(), _ordered()
    rows = "".join(f"<li><a href='/g/{it['gold_id']}'>{it['gold_id']}</a> {'✓' if it['gold_id'] in done else ''}</li>"
                   for it in items)
    nxt = _next_open()
    link = f"<p><a href='/g/{nxt}'>nächstes offenes Item: {nxt}</a></p>" if nxt else "<p>Alle Items überarbeitet.</p>"
    return gold._page("Dritter Durchgang", f"<h1>Dritter Durchgang (Rubrik v2)</h1>"
                                           f"<p>{len(done)} von {len(items)} überarbeitet.</p>{link}<ul>{rows}</ul>")


def serve(port: int = 8768) -> None:
    gold_annotated._require_blind_pass_complete()
    missing = [it["gold_id"] for it in gold.load_items() if it["gold_id"] not in gold_annotated.annotated_labels()]
    if missing:
        raise SystemExit(f"The second pass is not complete ({len(missing)} items).")
    SESSION_ORDER[:] = gold.grouped_order(gold.load_items(), random.SystemRandom())

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
            bad = save(gold_id, parse_qs(self.rfile.read(length).decode("utf-8")))
            if bad:
                return self._send(item_page(gold_id, f"Nicht gespeichert, bitte setzen: {', '.join(bad)}"), 400)
            nxt = _next_open()
            self.send_response(303)
            self.send_header("Location", f"/g/{nxt}" if nxt else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Third pass (gold labels for rubric v2) on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
