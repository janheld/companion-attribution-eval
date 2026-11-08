"""Word diff of a revised scenario against its previous (archived) version.

Revisions are meant to change only what the reviewer asked for. A word diff
per field lets the reviewer check that, instead of re-reading the scenario.
"""

import difflib
import html
import json
import re

from .schema import SCENARIO_DIR, load_set


def previous_version(set_name: str, scenario: dict) -> dict | None:
    """The newest archived version below the current one."""
    archived = []
    for path in (SCENARIO_DIR / "archive" / set_name).glob(f"{scenario['id']}.v*.json"):
        version = int(path.stem.rsplit(".v", 1)[1])
        if version < scenario["version"]:
            archived.append((version, path))
    if not archived:
        return None
    return json.loads(max(archived)[1].read_text(encoding="utf-8"))


def fields(scenario: dict) -> dict[str, str]:
    """Every text of a scenario under a readable label, in reading order."""
    c, ann = scenario["content"], scenario["annotation"]
    ctx = c["user_context"]
    out = {"Name": ctx["name"], "Zeit": ctx["time_of_day"],
           "Phase": f"{ctx['relationship_phase']['phase']}, Tag {ctx['relationship_phase']['days']}",
           "Hinweis": ctx.get("last_conversation_note") or ""}
    for i, n in enumerate(ctx.get("caregiver_notes", [])):
        # Older drafts may hold a note as a plain string; show it as it was.
        out[f"Notiz {i}"] = f"{n['author']}: {n['text']}" if isinstance(n, dict) else str(n)
    for k in ctx["knowledge_blocks"]:
        out[f"Wissen {k['topic']}"] = k["text"]
    for i, s in enumerate(ctx["recent_sessions"]):
        out[f"Gespräch {i} ({s['date']})"] = s["summary"] + " | Notizen: " + " / ".join(s["notes"])
    for i, t in enumerate(c["history"]):
        who = "Nutzer" if t["role"] == "user" else "Mira"
        out[f"#{i} {who}"] = (f"[{t['timestamp']}] " if t["role"] == "user" else "") + t["text"]
    final = c["final_user_turn"]
    out[f"#{len(c['history'])} Nutzer (final)"] = f"[{final['timestamp']}] {final['text']}"
    for i, d in enumerate(ann.get("disturbances", [])):
        out[f"Störung {i}"] = f"#{d['turn_index']} {d['type']}: {d['span']}"
    out["Begründung"] = ann.get("rationale", "")
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"\S+\s*", text)


def word_diff(old: str, new: str) -> list[tuple[str, str]]:
    """[(op, text)] with op in ' ', '-', '+'."""
    a, b = _words(old), _words(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append((" ", "".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(("-", "".join(a[i1:i2])))
        if j2 > j1:
            out.append(("+", "".join(b[j1:j2])))
    return out


def changed_fields(old: dict, new: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    fo, fn = fields(old), fields(new)
    labels = list(fo) + [k for k in fn if k not in fo]
    return [(label, word_diff(fo.get(label, ""), fn.get(label, "")))
            for label in labels if fo.get(label, "") != fn.get(label, "")]


def _context(ops: list[tuple[str, str]], keep: int = 8) -> list[tuple[str, str]]:
    """Shorten long unchanged stretches to a few words on each side."""
    out = []
    for n, (op, text) in enumerate(ops):
        words = text.split()
        if op == " " and len(words) > 2 * keep:
            head = " ".join(words[:keep]) + " " if n > 0 else ""
            tail = " " + " ".join(words[-keep:]) + " " if n < len(ops) - 1 else ""
            text = f"{head}…{tail}"
        out.append((op, text))
    return out


def text_report(old: dict, new: dict) -> str:
    lines = [f"## {new['id']}  v{old['version']} -> v{new['version']}",
             f"Kommentar: {old['review'].get('comment', '')}"]
    for label, ops in changed_fields(old, new):
        marked = "".join(t if op == " " else f"[-{t.strip()}-] " if op == "-" else f"{{+{t.strip()}+}} "
                         for op, t in _context(ops))
        lines.append(f"  {label}: {marked.strip()}")
    return "\n".join(lines)


def html_report(old: dict, new: dict, heading: str | None = None) -> str:
    rows = []
    for label, ops in changed_fields(old, new):
        parts = "".join(html.escape(t) if op == " " else
                        f"<del>{html.escape(t)}</del>" if op == "-" else f"<ins>{html.escape(t)}</ins>"
                        for op, t in _context(ops))
        rows.append(f"<tr><td><b>{html.escape(label)}</b></td><td>{parts}</td></tr>")
    head = heading or f"<b>Kommentar zu v{old['version']}:</b> {html.escape(old['review'].get('comment', ''))}"
    return (f"<p>{head}</p>"
            f"<table>{''.join(rows) or '<tr><td>keine Textänderung</td></tr>'}</table>")


def print_diffs(set_name: str, only_ids: list[str] | None = None) -> None:
    for scenario in load_set(set_name):
        if only_ids and scenario["id"] not in only_ids:
            continue
        if scenario["status"] != "draft" and not only_ids:
            continue
        old = previous_version(set_name, scenario)
        if old:
            print(text_report(old, scenario) + "\n")
