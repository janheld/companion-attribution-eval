"""Turn a scenario into what a model sees.

Layout of a `response` request, following the pilot setup:
  system[0]  system prompt of the variant      (cache breakpoint: shared by all scenarios)
  system[1]  user context block of the scenario
  messages   session history, every user turn prefixed with its timestamp,
             then the final user turn            (cache breakpoint: shared by repetitions)
The `annotation` of a scenario is never rendered: it is ground truth for analysis.
"""

import re

CACHE = {"type": "ephemeral"}
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


# Scenario writers formatted some context fields differently ("Vertraut (ab Tag
# 91)" vs "Vertraut"). The format is unified here, when the context block is
# built, not in the scenario files: approved scenarios keep their content hash,
# and every model sees the same format.

def phase_label(days: int) -> str:
    """Phase name from the day count, matching the phases in the companion prompt."""
    if days <= 14:
        return "Kennenlernen"
    if days <= 90:
        return "Vertraut werden"
    return "Vertraut"


def session_date(raw: str, today: str) -> str:
    """Normalize to 'Dienstag, vor 2 Tagen', filling a missing part from today's weekday."""
    weekday = next((w for w in WEEKDAYS if w in raw), None)
    match = re.search(r"vor (\d+) Tag", raw)
    days = int(match.group(1)) if match else (1 if "gestern" in raw.lower() else None)
    today_wd = next((w for w in WEEKDAYS if w in today), None)
    if today_wd and days and not weekday:
        weekday = WEEKDAYS[(WEEKDAYS.index(today_wd) - days) % 7]
    if today_wd and weekday and not days:
        days = (WEEKDAYS.index(today_wd) - WEEKDAYS.index(weekday)) % 7 or 7
    if weekday and days:
        return f"{weekday}, vor {days} {'Tag' if days == 1 else 'Tagen'}"
    return raw


def _days_ago(raw: str, today: str) -> int:
    """Age of a summary in days, for sorting; unknown ages go last."""
    match = re.search(r"vor (\d+) Tag", session_date(raw, today))
    return int(match.group(1)) if match else 10_000


def sorted_sessions(ctx: dict) -> list[dict]:
    """Summaries newest first, as a memory store would list them. Writers put
    them in either order; sorting here keeps the scenario files (and the hashes
    of approved scenarios) unchanged."""
    return sorted(ctx["recent_sessions"], key=lambda s: _days_ago(s["date"], ctx["time_of_day"]))


def context_block(ctx: dict) -> str:
    lines = ["# Nutzerkontext", "",
             f"Name: {ctx['name']}",
             "Bevorzugte Sprache: Deutsch",
             f"Anrede: {ctx['address_form']}",
             f"Beziehungsphase: {phase_label(ctx['relationship_phase']['days'])}, "
             f"Tag {ctx['relationship_phase']['days']}",
             f"Aktuelle Zeit: {ctx['time_of_day']}"]
    if ctx.get("last_conversation_note"):
        lines.append(f"Hinweis: {ctx['last_conversation_note']}")
    if ctx.get("caregiver_notes"):
        lines += ["", "## Notizen von Angehörigen und Pflege"]
        lines += [f"- {n['author']}: {n['text']}" for n in ctx["caregiver_notes"]]
    lines += ["", "## Wissen über die Person"]
    lines += [f"- {k['topic']}: {k['text']}" for k in ctx["knowledge_blocks"]]
    lines += ["", "## Letzte Gespräche"]
    for s in sorted_sessions(ctx):
        lines.append(f"### {session_date(s['date'], ctx['time_of_day'])}")
        lines.append(s["summary"])
        lines += [f"- Notiz: {n}" for n in s["notes"]]
    # The dialect field is generator metadata, not something a production
    # context would contain, so it is not rendered.
    return "\n".join(lines)


def _user_text(turn: dict) -> str:
    return f"[{turn['timestamp']}] {turn['text']}"


def response_request(scenario: dict, system_prompt: str) -> tuple[list, list]:
    content = scenario["content"]
    system = [{"type": "text", "text": system_prompt, "cache_control": CACHE},
              {"type": "text", "text": context_block(content["user_context"])}]
    messages = []
    for turn in content["history"]:
        text = _user_text(turn) if turn["role"] == "user" else turn["text"]
        messages.append({"role": turn["role"], "content": text})
    final = {"type": "text", "text": _user_text(content["final_user_turn"]), "cache_control": CACHE}
    messages.append({"role": "user", "content": [final]})
    return system, messages


def transcript(scenario: dict) -> str:
    content = scenario["content"]
    lines = []
    for turn in content["history"]:
        if turn["role"] == "user":
            lines.append(f"Nutzer [{turn['timestamp']}]: {turn['text']}")
        else:
            lines.append(f"Mira: {turn['text']}")
    final = content["final_user_turn"]
    lines.append(f"Nutzer [{final['timestamp']}]: {final['text']}")
    return "\n".join(lines)


def summary_request(scenario: dict, summarizer_prompt: str) -> tuple[list, list]:
    # The summarizer sees only the session, the name and the time, like the
    # pilot's end-of-session summarizer; it does not see the long-term memory.
    ctx = scenario["content"]["user_context"]
    user = (f"Person: {ctx['name']}\nZeit: {ctx['time_of_day']}\n\n"
            f"Gesprächsprotokoll:\n{transcript(scenario)}")
    system = [{"type": "text", "text": summarizer_prompt, "cache_control": CACHE}]
    messages = [{"role": "user", "content": [{"type": "text", "text": user, "cache_control": CACHE}]}]
    return system, messages
