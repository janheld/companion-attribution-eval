"""Local review page for scenarios (http://127.0.0.1:8765).

Plain standard-library HTTP server: no build step, no JavaScript framework.
It only ever listens on localhost and only writes status and comment fields
of scenario files.
"""

import html
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .schema import STATUSES, load, save, scenario_path, SCENARIO_DIR, sync_status, validate
from .diff import html_report, previous_version
from .render import context_block

CSS = """
body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#fafaf7;color:#222;line-height:1.45}
a{color:#2457a6}table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;font-size:14px}
.turn{padding:8px 12px;margin:6px 0;border-radius:8px}.user{background:#fff;border:1px solid #ddd}
.assistant{background:#eef3fb;margin-left:40px}.final{border:2px solid #c47f00}
.idx{color:#888;font-size:12px}mark{background:#ffd9a8;padding:0 2px}
pre{white-space:pre-wrap;background:#fff;border:1px solid #ddd;padding:10px;font-size:13px}
.status-approved{color:#1a7f37}.status-rejected{color:#c0392b}.status-needs_edit{color:#b26a00}.status-draft{color:#666}
.meta{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;font-size:14px}
textarea{width:100%;height:90px}button{margin-right:8px;padding:6px 12px}
.problems{background:#fde8e8;padding:8px;border-radius:6px}
del{background:#fbd3d3;text-decoration:line-through}ins{background:#c9efd0;text-decoration:none}
"""


def _ids(set_name: str) -> list[str]:
    return sorted(p.stem for p in (SCENARIO_DIR / set_name).glob("*.json"))


def _load_synced(set_name: str, sid: str) -> dict:
    scenario = load(scenario_path(set_name, sid))
    if sync_status(scenario):
        save(scenario)
    return scenario


def _highlight(text: str, spans: list[str]) -> str:
    out = html.escape(text)
    for span in spans:
        if span:
            out = out.replace(html.escape(span), f"<mark>{html.escape(span)}</mark>")
    return out


def _page(title: str, body: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style>{body}").encode("utf-8")


def list_page(set_name: str, status_filter: str | None) -> bytes:
    rows, counts = [], {s: 0 for s in STATUSES}
    for sid in _ids(set_name):
        s = _load_synced(set_name, sid)
        counts[s["status"]] += 1
        if status_filter and s["status"] != status_filter:
            continue
        comment = html.escape(s["review"].get("comment", "")[:80])
        rows.append(f"<tr><td><a href='/s/{sid}'>{sid}</a></td><td>v{s['version']}</td>"
                    f"<td>{s['annotation']['disturbance_position']}</td>"
                    f"<td>{html.escape(s['content']['user_context'].get('dialect', ''))}</td>"
                    f"<td class='status-{s['status']}'>{s['status']}</td><td>{comment}</td></tr>")
    filters = " · ".join(f"<a href='/?status={st}'>{st} ({n})</a>" for st, n in counts.items())
    body = (f"<h1>Review: {html.escape(set_name)}</h1><p><a href='/'>all</a> · {filters}</p>"
            "<table><tr><th>id</th><th>ver</th><th>position</th><th>dialect</th><th>status</th><th>comment</th></tr>"
            + "".join(rows) + "</table>")
    return _page(f"Review {set_name}", body)


def detail_page(set_name: str, sid: str) -> bytes:
    s = _load_synced(set_name, sid)
    ids = _ids(set_name)
    i = ids.index(sid)
    nav = (f"<a href='/'>list</a>"
           + (f" · <a href='/s/{ids[i - 1]}'>← {ids[i - 1]}</a>" if i > 0 else "")
           + (f" · <a href='/s/{ids[i + 1]}'>{ids[i + 1]} →</a>" if i + 1 < len(ids) else ""))
    ann, content = s["annotation"], s["content"]
    spans_by_turn = {}
    for d in ann.get("disturbances", []):
        spans_by_turn.setdefault(d["turn_index"], []).append(d["span"])

    turns = []
    for idx, turn in enumerate(content["history"]):
        ts = f"[{turn['timestamp']}] " if turn["role"] == "user" else ""
        who = "Nutzer" if turn["role"] == "user" else "Mira"
        turns.append(f"<div class='turn {turn['role']}'><span class=idx>#{idx} {who}</span><br>"
                     f"{ts}{_highlight(turn['text'], spans_by_turn.get(idx, []))}</div>")
    final_idx = len(content["history"])
    final = content["final_user_turn"]
    turns.append(f"<div class='turn user final'><span class=idx>#{final_idx} Nutzer – finaler Turn</span><br>"
                 f"[{final['timestamp']}] {_highlight(final['text'], spans_by_turn.get(final_idx, []))}</div>")

    disturbances = "".join(f"<li>#{d['turn_index']} <b>{d['type']}</b>: {html.escape(d['span'])}</li>"
                           for d in ann.get("disturbances", [])) or "<li>keine</li>"
    problems = validate(s)
    problem_html = ("<div class=problems><b>Validation:</b> " + html.escape("; ".join(problems)) + "</div>"
                    if problems else "")
    spec = s.get("spec", {})
    old = previous_version(set_name, s)
    changes = (f"<h2>Änderungen gegenüber v{old['version']}</h2>{html_report(old, s)}" if old else "")
    buttons = "".join(f"<button name=status value={st}>{st}</button>" for st in STATUSES if st != "draft")

    body = f"""
<p>{nav}</p>
<h1>{sid} <small>v{s['version']}</small> <span class='status-{s['status']}'>[{s['status']}]</span></h1>
{problem_html}
{changes}
<div class=meta>
<b>Bedingung</b><span>{s['condition']}</span>
<b>Störung sitzt</b><span>{ann['disturbance_position']}</span>
<b>Kontakttyp</b><span>{ann.get('contact_type') or '–'}</span>
<b>Bitte um nicht verfügbare Handlung</b><span>{'ja: ' + html.escape(spec.get('action_request') or '') if ann.get('unavailable_action_request') else 'nein'}</span>
<b>Persona-Vorgaben</b><span>{html.escape(spec.get('health', '–'))}; {html.escape(spec.get('relatives', '–'))}</span>
<b>Dialekt</b><span>{html.escape(content['user_context'].get('dialect', ''))}</span>
<b>Spec</b><span>{html.escape(', '.join(spec.get('interests', [])))}; {html.escape(spec.get('household', ''))}</span>
</div>
<h2>Störungen (Ground Truth)</h2><ul>{disturbances}</ul>
<p><i>{html.escape(ann.get('rationale', ''))}</i></p>
<h2>Gesprächsverlauf</h2>{''.join(turns)}
<h2>Review</h2>
<form method=post action='/s/{sid}'>
<textarea name=comment placeholder='Kommentar zum Realismus, was geändert werden soll'>{html.escape(s['review'].get('comment', ''))}</textarea><br>
{buttons}
</form>
<h2>Nutzerkontext (so sieht ihn das Modell)</h2><pre>{html.escape(context_block(content['user_context']))}</pre>
<p class=idx>Datei: scenarios/{set_name}/{sid}.json · hash {s['content_hash'][:12]}</p>
<p>{nav}</p>"""
    return _page(sid, body)


def make_handler(set_name: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str):
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                status = parse_qs(url.query).get("status", [None])[0]
                return self._send(list_page(set_name, status))
            if url.path.startswith("/s/") and url.path[3:] in _ids(set_name):
                return self._send(detail_page(set_name, url.path[3:]))
            self._send(b"not found", 404)

        def do_POST(self):
            sid = urlparse(self.path).path[3:]
            if sid not in _ids(set_name):
                return self._send(b"not found", 404)
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            status = form.get("status", [""])[0]
            if status not in STATUSES:
                return self._send(b"bad status", 400)
            scenario = _load_synced(set_name, sid)
            scenario["status"] = status
            scenario["review"] = {"comment": form.get("comment", [""])[0].strip(),
                                  "reviewed_at": datetime.now(timezone.utc).isoformat()}
            save(scenario)
            ids = _ids(set_name)
            i = ids.index(sid)
            self._redirect(f"/s/{ids[i + 1]}" if i + 1 < len(ids) else "/")

        def log_message(self, *args):
            pass

    return Handler


def serve(set_name: str, port: int = 8765) -> None:
    server = HTTPServer(("127.0.0.1", port), make_handler(set_name))
    print(f"Review '{set_name}' at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
