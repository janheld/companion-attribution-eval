"""Second labeling pass for `content_misattributed`, with the ground truth shown.

In the blind pass the author sees what the grader sees: unmarked speech
recognition text. Whether an output repeats foreign content (TV, radio,
another person, a recognition error) as the person's own can then only be
guessed. This pass shows, per item, the annotated disturbances (turn, type,
exact span) and the scenario's rationale, which says what was actually said,
next to the author's blind label. Only `content_misattributed` can be set.

- It starts only when all gold items are labeled blind, so the blind pass
  stays blind.
- Corrections go to gold/labels_annotated.jsonl (append-only); the blind
  labels in gold/labels.jsonl are never touched.
- For grader validation, `content_misattributed` uses the value of this pass,
  every other field the blind label (`reference_labels`). How often the two
  passes differ is reported as a measure of how hard the disturbances are to
  see without marking.
"""

import html
import json
import random
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import gold, render

ANNOTATED = gold.GOLD_DIR / "labels_annotated.jsonl"
FIELD = "content_misattributed"
SESSION_ORDER: list[str] = []


def annotated_labels() -> dict:
    """Latest second-pass value per gold item."""
    if not ANNOTATED.exists():
        return {}
    out = {}
    for line in ANNOTATED.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["gold_id"]] = row
    return out


def reference_labels() -> dict:
    """Gold reference: blind labels, with content_misattributed from the second pass where it exists."""
    blind, second = gold.author_labels(), annotated_labels()
    out = {}
    for gid, row in blind.items():
        labels = dict(row["labels"])
        if gid in second:
            labels[FIELD] = second[gid][FIELD]
        out[gid] = {**row, "labels": labels, "note": " / ".join(n for n in (row.get("note"), second.get(gid, {}).get("note")) if n)}
    return out


def _require_blind_pass_complete() -> None:
    blind = gold.author_labels()
    missing = [it["gold_id"] for it in gold.load_items() if it["gold_id"] not in blind]
    if missing:
        raise SystemExit(f"The blind pass is not complete ({len(missing)} items unlabeled). "
                         "The annotated pass starts only afterwards.")


def _next_open() -> str | None:
    done = annotated_labels()
    rank = {g: i for i, g in enumerate(SESSION_ORDER)}
    items = sorted(gold.load_items(), key=lambda it: rank.get(it["gold_id"], len(rank)))
    return next((it["gold_id"] for it in items if it["gold_id"] not in done), None)


def _disturbance_rows(scenario: dict) -> str:
    ann = scenario["annotation"]
    rows = []
    for d in ann.get("disturbances", []):
        who = "Nutzerturn" if d["turn_index"] < len(scenario["content"]["history"]) else "finaler Nutzerturn"
        rows.append(f"<tr><td>#{d['turn_index']} ({who})</td><td>{html.escape(d['type'])}</td>"
                    f"<td>{html.escape(d['span'])}</td></tr>")
    if not rows:
        return "<p>Keine Störstellen annotiert.</p>"
    return ("<table><tr><th>Turn</th><th>Typ</th><th>Fremder bzw. falsch erkannter Text</th></tr>"
            + "".join(rows) + "</table>"
            f"<p><b>Was eigentlich gesagt wurde (Begründung des Szenarios, englisch):</b> "
            f"{html.escape(ann.get('rationale', ''))}</p>")


def _highlighted_transcript(scenario: dict) -> str:
    spans = {}
    for d in scenario["annotation"].get("disturbances", []):
        spans.setdefault(d["turn_index"], []).append(d["span"])
    return gold.turns_html(scenario, show_index=True, marks=spans)


def item_page(gold_id: str, error: str = "") -> bytes:
    it = {x["gold_id"]: x for x in gold.load_items()}[gold_id]
    s = gold._scenarios()[(it["set"], it["scenario_id"])]
    blind = gold.author_labels()[gold_id]
    current = annotated_labels().get(gold_id, {})
    chosen = str(current[FIELD]).lower() if FIELD in current else None
    radios = "".join(f"<label><input type=radio name={FIELD} value={v} required "
                     f"{'checked' if v == chosen else ''}>{v}</label>" for v in ("true", "false"))
    blind_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
                         for k, v in blind["labels"].items())
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    body = f"""<p><a href='/'>Liste</a></p><h1>{gold_id}: {kind}</h1>{err}
<p>Zweiter Durchgang: nur <b>{FIELD}</b> ist änderbar. Modell, Variante, Bedingung, Split und Grader-Labels bleiben verborgen.</p>
<h2>Output</h2><div class=out>{html.escape(it['text'])}</div>
<h2>Störstellen (Ground Truth)</h2>{_disturbance_rows(s)}
<h2>Dein blindes Label (unverändert)</h2><table>{blind_rows}</table>
<p><b>Deine Notiz aus dem blinden Durchgang:</b> {html.escape(blind.get('note', '') or '–')}</p>
<form method=post action='/g/{gold_id}'><fieldset><legend>{FIELD} (zweiter Durchgang)</legend>{radios}</fieldset>
<p><textarea name=note style='width:100%;height:50px' placeholder='Notiz zum zweiten Durchgang (optional)'>{html.escape(current.get('note', ''))}</textarea></p>
<button>Speichern und weiter</button></form>
<h2>Gespräch (Störstellen markiert)</h2>{_highlighted_transcript(s)}
<h2>Gedächtniskontext</h2><pre>{html.escape(render.context_block(s['content']['user_context']))}</pre>"""
    return gold._page(gold_id, body)


def save(gold_id: str, form: dict) -> str:
    value = (form.get(FIELD) or [""])[0]
    if value not in ("true", "false"):
        return f"Nicht gespeichert, bitte {FIELD} setzen."
    row = {"gold_id": gold_id, FIELD: value == "true",
           "blind_value": gold.author_labels()[gold_id]["labels"].get(FIELD),
           "note": form.get("note", [""])[0], "labeled_at": datetime.now(timezone.utc).isoformat()}
    with ANNOTATED.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return ""


def list_page() -> bytes:
    done = annotated_labels()
    rank = {g: i for i, g in enumerate(SESSION_ORDER)}
    items = sorted(gold.load_items(), key=lambda it: rank.get(it["gold_id"], len(rank)))
    rows = "".join(f"<li><a href='/g/{it['gold_id']}'>{it['gold_id']}</a> {'✓' if it['gold_id'] in done else ''}</li>"
                   for it in items)
    nxt = _next_open()
    link = f"<p><a href='/g/{nxt}'>nächstes offenes Item: {nxt}</a></p>" if nxt else "<p>Alle Items durchgesehen.</p>"
    return gold._page("Zweiter Durchgang", f"<h1>Zweiter Durchgang: {FIELD}</h1>"
                                            f"<p>{len(done)} von {len(items)} durchgesehen.</p>{link}<ul>{rows}</ul>")


def serve(port: int = 8767) -> None:
    _require_blind_pass_complete()
    SESSION_ORDER[:] = [it["gold_id"] for it in gold.load_items()]
    random.SystemRandom().shuffle(SESSION_ORDER)

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
            error = save(gold_id, parse_qs(self.rfile.read(length).decode("utf-8")))
            if error:
                return self._send(item_page(gold_id, error), 400)
            nxt = _next_open()
            self.send_response(303)
            self.send_header("Location", f"/g/{nxt}" if nxt else "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    print(f"Second pass (content_misattributed with annotations) on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def blind_vs_annotated(items: list[dict]) -> dict:
    """Agreement of the author with herself: blind value vs. value with annotations."""
    from . import stats
    blind, second = gold.author_labels(), annotated_labels()
    pairs = [(blind[it["gold_id"]]["labels"][FIELD], second[it["gold_id"]][FIELD])
             for it in items if it["gold_id"] in blind and it["gold_id"] in second]
    if not pairs:
        return {"n": 0}
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    return {"n": len(pairs), "agreement": sum(x == y for x, y in pairs) / len(pairs),
            "kappa": stats.cohens_kappa(a, b) if len(set(a) | set(b)) > 1 else float("nan"),
            "confusion (blind -> annotated)": stats.confusion(a, b)}
