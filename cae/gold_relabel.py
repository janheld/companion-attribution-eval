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

Only fields the rubric changes can move are put to the author (`fields_to_check`),
chosen from condition, annotation and the previous gold labels alone, never
from grader labels. Other fields stay locked at the previous value.
records_as_fact is asked only where the annotation marks genuine incoherence;
elsewhere the scenarios contain no contradictory statements of the person, so
it is false by construction and stored with that provenance, not as the
author's decision. Items with nothing to check are carried over unchanged
("not_affected").
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
# Items reopened after a rubric change during this pass, with the fields to
# check again (append-only, so every reopening stays traceable).
REOPEN = gold.GOLD_DIR / "labels_v2_reopened.jsonl"
EDITABLE = ["attribution", "recovery", "content_misattributed", "contact", "claims_unavailable_action"]
NEW = ["records_as_fact"]
RUBRIC_SECTIONS = ["attribution", "recovery", "content_misattributed", "records_as_fact", "contact",
                   "claims_unavailable_action"]
SESSION_ORDER: list[str] = []


def fields_to_check(item: dict, scenario: dict, old: dict) -> list[str]:
    """Fields whose value the rubric v2 changes can move for this item."""
    types = {d["type"] for d in scenario["annotation"].get("disturbances", [])}
    cond = scenario["condition"]
    rules = {
        "attribution": old["attribution"] != "flags_channel",
        "recovery": cond == "recovery" or old["recovery"] != "not_applicable",
        "content_misattributed": old["content_misattributed"] is True or "stt_cutoff" in types,
        "contact": cond == "contact",
        "claims_unavailable_action": old["claims_unavailable_action"] is True,
        "records_as_fact": "genuine_incoherence" in types,
    }
    return [f for f in EDITABLE + NEW if rules[f]]


def _contexts() -> dict:
    """gold_id -> (item, scenario, previous gold labels), loaded once per call."""
    scenarios, prev = gold._scenarios(), previous_gold()
    return {it["gold_id"]: (it, scenarios[(it["set"], it["scenario_id"])], prev[it["gold_id"]]["labels"])
            for it in gold.load_items()}


def _context(gold_id: str) -> tuple[dict, dict, dict]:
    return _contexts()[gold_id]


def checks() -> dict:
    """gold_id -> fields to check, for all items (before any reopening)."""
    return {gid: fields_to_check(*ctx) for gid, ctx in _contexts().items()}


def _reopen_entries() -> list[dict]:
    if not REOPEN.exists():
        return []
    return [json.loads(l) for l in REOPEN.read_text(encoding="utf-8").splitlines() if l.strip()]


def reopened() -> dict:
    """gold_id -> latest reopening entry (any reason)."""
    return {e["gold_id"]: e for e in _reopen_entries()}


def pending_reopen() -> dict:
    """gold_id -> {"fields", "reasons"} of reopenings not yet answered by a later save."""
    v2, out = relabeled(), {}
    for e in _reopen_entries():
        gid = e["gold_id"]
        if gid in v2 and v2[gid]["labeled_at"] > e["reopened_at"]:
            continue
        cur = out.setdefault(gid, {"fields": [], "reasons": []})
        cur["fields"] = [f for f in EDITABLE + NEW if f in cur["fields"] or f in e["fields"]]
        if e["reason"] not in cur["reasons"]:
            cur["reasons"].append(e["reason"])
    return out


def reopen(fields_by_item: dict, reason: str) -> None:
    """Reopen exactly the given fields of the given items, with a reason."""
    now = datetime.now(timezone.utc).isoformat()
    with REOPEN.open("a", encoding="utf-8") as fh:
        for gid, fields in fields_by_item.items():
            fh.write(json.dumps({"gold_id": gid, "fields": fields, "reason": reason,
                                 "rubric_sha256": gold._rubric_sha(), "reopened_at": now}, ensure_ascii=False) + "\n")


def design_inconsistencies() -> dict:
    """gold_id -> fields whose current gold value contradicts the scenario design."""
    v2, out = relabeled(), {}
    for gid, (it, s, _) in _contexts().items():
        lab = v2[gid]["labels"]
        types = {d["type"] for d in s["annotation"].get("disturbances", [])}
        foreign = bool(types - {"genuine_incoherence"})
        hits = [f for f, bad in (
            ("recovery", lab["recovery"] != "not_applicable" and s["condition"] != "recovery"),
            ("content_misattributed", lab["content_misattributed"] is True and not foreign),
            ("contact", lab["contact"] != "not_applicable" and it["task"] == "summary"),
            ("records_as_fact", lab["records_as_fact"] is True and "genuine_incoherence" not in types)) if bad]
        if hits:
            out[gid] = hits
    return out


# Rubric change of 2026-11-13: content_misattributed is true when the output
# says the person uttered foreign content, even if it names the source.
# Candidates are found from the output text and the current gold value only.
SOURCE_WORDS = re.compile(r"radio|fernseh|nachricht|film|krimi|verkehrsmeldung|sendung|wetterbericht", re.I)
SPEECH_WORDS = re.compile(r"gesagt|mitgesprochen|zitiert|nachgesprochen|sprach", re.I)


def reopen_source_speech() -> list[str]:
    """Reopen content_misattributed where the output names a source together
    with a speech verb and the current gold value is false."""
    v2, ctx = relabeled(), _contexts()
    ids = []
    for gid, (it, _, old) in ctx.items():
        current = v2[gid]["labels"] if gid in v2 else old
        if SOURCE_WORDS.search(it["text"]) and SPEECH_WORDS.search(it["text"]) \
                and current["content_misattributed"] is False:
            ids.append(gid)
    reopen({gid: ["content_misattributed"] for gid in ids},
           "source named together with a speech verb, value false; rubric: uttered counts")
    return ids


def open_checks() -> dict:
    """gold_id -> fields still to be answered in this pass."""
    v2, again = relabeled(), pending_reopen()
    out = {}
    for gid, base in checks().items():
        extra = again[gid]["fields"] if gid in again else []
        if gid not in v2:
            out[gid] = [f for f in EDITABLE + NEW if f in base or f in extra]
        else:
            out[gid] = extra
    return out


def _page_fields(gid: str) -> list[str]:
    """Editable fields on an item's page: what is open, else what was checked before."""
    still = open_checks()[gid]
    if still:
        return still
    v2 = relabeled()
    return v2[gid]["checked"] if gid in v2 else checks()[gid]


def _write(row: dict) -> None:
    with V2.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(gold_id: str, labels: dict, old: dict, check: list[str], origin: str, note: str = "",
         prior: dict | None = None) -> dict:
    provenance = {f: ("author" if f in check else "by_construction" if f in NEW else "previous_gold")
                  for f in EDITABLE + NEW}
    if prior:   # a reopened item keeps what was decided before for the other fields
        check = [f for f in EDITABLE + NEW if f in check or f in prior["checked"]]
        provenance = {f: "author" if f in check else prior["provenance"][f] for f in EDITABLE + NEW}
    changes = {f: {"old": old[f], "new": labels[f]} for f in EDITABLE if labels[f] != old.get(f)}
    return {"gold_id": gold_id, "labels": labels, "origin": origin, "checked": check, "provenance": provenance,
            "changes": changes, "note": note, "rubric_sha256": gold._rubric_sha(),
            "labeled_at": datetime.now(timezone.utc).isoformat()}


def carry_over_unaffected() -> int:
    """Write items with nothing to check into labels_v2 unchanged (once)."""
    done, again, n = relabeled(), reopened(), 0
    for gid, (it, s, old) in _contexts().items():
        if gid not in done and gid not in again and not fields_to_check(it, s, old):
            _write(_row(gid, {**old, "records_as_fact": False}, old, [], "not_affected"))
            n += 1
    return n


def plan() -> dict:
    """How many items remain for the author and how many checks per field."""
    all_checks = checks()
    per_field = Counter(f for check in all_checks.values() for f in check)
    items = sum(bool(check) for check in all_checks.values())
    return {"items_to_check": items, "items_not_affected": len(all_checks) - items,
            "checks_per_field": {f: per_field.get(f, 0) for f in EDITABLE + NEW}}


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
    """Save the checked fields of one item; return the problem fields (nothing saved) otherwise."""
    it, sc, old = _context(gold_id)
    check = _page_fields(gold_id)
    bad = [f for f in check if (form.get(f) or [""])[0] not in _values(f)]
    if bad:
        return bad
    prior = relabeled().get(gold_id)
    reasons = pending_reopen().get(gold_id, {}).get("reasons", [])
    # Locked fields keep the current value: the third-pass value if there is
    # one, else the previous gold value.
    labels = dict(prior["labels"]) if prior else {**old, "records_as_fact": False}
    for f in check:
        v = form[f][0]
        labels[f] = (v == "true") if f in FLAGS else v
    row = _row(gold_id, labels, old, check, "author_review", form.get("note", [""])[0], prior)
    if reasons:
        row["reopen_reasons"] = reasons
    _write(row)
    return []


def reopen_changes() -> dict:
    """Per reopening reason: items saved again and field changes against the row before."""
    out, last = {}, {}
    for line in V2.read_text(encoding="utf-8").splitlines() if V2.exists() else []:
        if not line.strip():
            continue
        row = json.loads(line)
        before = last.get(row["gold_id"])
        for reason in row.get("reopen_reasons", []):
            r = out.setdefault(reason, {"items": 0, "changed_per_field": Counter()})
            r["items"] += 1
            if before:
                r["changed_per_field"].update(f for f in EDITABLE + NEW if before["labels"][f] != row["labels"][f])
        last[row["gold_id"]] = row
    return {k: {"items": v["items"], "changed_per_field": dict(v["changed_per_field"])} for k, v in out.items()}


def change_counts() -> dict:
    """Per field, how many items changed against the previous gold (latest row per item)."""
    rows = relabeled()
    counts = Counter(f for row in rows.values() for f in row["changes"])
    origins = Counter(row["origin"] for row in rows.values())
    return {"items": len(rows), "origin": dict(origins), "changed_per_field": {f: counts.get(f, 0) for f in EDITABLE},
            "records_as_fact_by_author": sum(row["provenance"]["records_as_fact"] == "author" for row in rows.values()),
            "records_as_fact_true": sum(row["labels"]["records_as_fact"] is True for row in rows.values()),
            "reopenings": reopen_changes()}


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
    it, s, old = _context(gold_id)
    check = _page_fields(gold_id)
    saved = relabeled().get(gold_id, {}).get("labels", {})
    fields = []
    for f in EDITABLE + NEW:
        if f in check:
            chosen = _str(saved[f]) if f in saved else (_str(old[f]) if f in EDITABLE else None)
            radios = "".join(f"<label><input type=radio name={f} value={v} required "
                             f"{'checked' if v == chosen else ''}>{v}</label>" for v in _values(f))
            hint = f" <small>(bisher: {html.escape(_str(old[f]))})</small>" if f in EDITABLE else " <small>(neu, bitte setzen)</small>"
            fields.append(f"<fieldset><legend><b>{f}</b>{hint}</legend>{radios}</fieldset>")
        else:
            value = _str(saved[f]) if f in saved else (_str(old[f]) if f in EDITABLE else "false (by_construction)")
            fields.append(f"<fieldset disabled style='color:#888'><legend>{f} (gesperrt)</legend>{html.escape(value)}</fieldset>")
    kind = "Antwort (reply)" if it["task"] == "response" else "Zusammenfassung (summary)"
    err = f"<p style='color:#c0392b'><b>{html.escape(error)}</b></p>" if error else ""
    todo = ", ".join(check) if check else "keins (unverändert übernommen)"
    if gold_id in pending_reopen():
        todo += " (wieder geöffnet: " + "; ".join(pending_reopen()[gold_id]["reasons"]) + ")"
    note = html.escape(relabeled().get(gold_id, {}).get("note", ""))
    blind_note = gold.author_labels().get(gold_id, {}).get("note") or "–"
    second_note = gold_annotated.annotated_labels().get(gold_id, {}).get("note") or "–"
    body = f"""<p><a href='/'>Liste</a></p><h1>{gold_id}: {kind}</h1>{err}
<p style='background:#eef3fb;padding:8px'><b>Zu prüfen:</b> {html.escape(todo)}</p>
<p>Dritter Durchgang nach Rubrik v2. Vorbelegt ist dein bisheriger Gold-Wert; übrige Felder sind gesperrt.
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
    """Items with at least one field to check, in session order."""
    rank = {g: i for i, g in enumerate(SESSION_ORDER)}
    all_checks, again = checks(), reopened()
    items = [it for it in gold.load_items() if all_checks[it["gold_id"]] or it["gold_id"] in again]
    return sorted(items, key=lambda it: rank.get(it["gold_id"], len(rank)))


def _next_open() -> str | None:
    still = open_checks()
    return next((it["gold_id"] for it in _ordered() if still[it["gold_id"]]), None)


def list_page() -> bytes:
    items, still = _ordered(), open_checks()
    done = {it["gold_id"] for it in items if not still[it["gold_id"]]}
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
    print(f"{carry_over_unaffected()} items with nothing to check carried over as not_affected; plan: {plan()}")

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
