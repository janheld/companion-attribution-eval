"""Heuristic checks on written scenarios: time consistency and repeated openings.

These are warnings for the reviewer, not hard validation: they cannot read
every phrasing, and a hit can be fine on inspection. They exist because
reviewers found time contradictions (a shift in the morning, coming home from
it in the afternoon; "am Donnerstag" in an old summary that points to a day
already past; school on a Saturday), near-identical opening lines, repeated
situations and repeated TV/radio fragments across scenarios.

The repeat checks are lexical. They catch shared wording, not shared ideas
(a plumber's bill and a craftsman's bill), so known building blocks are also
listed by pattern in configs/generate.yaml (`overused_blocks`).
"""

import difflib
import itertools
import re
from collections import Counter

from .render import WEEKDAYS

WD = "|".join(WEEKDAYS)
WEEKEND = {"Samstag", "Sonntag"}
SCHOOL_DAY = re.compile(r"nach der Schule|von der Schule|aus der Schule|in die Schule gebracht|Schulschluss", re.I)
# Typical shift hours; a shift said to be on "heute" that covers the current
# clock time means the person is at work now.
SHIFTS = {"Frühschicht": (6, 14), "Spätschicht": (14, 22), "Nachtschicht": (22, 30)}


def _today(scenario: dict) -> tuple[int | None, int | None]:
    """Weekday index and clock time in minutes from user_context.time_of_day."""
    tod = scenario["content"]["user_context"]["time_of_day"]
    wd = next((i for i, w in enumerate(WEEKDAYS) if w in tod), None)
    m = re.search(r"(\d{1,2}):(\d{2})", tod)
    return wd, (int(m.group(1)) * 60 + int(m.group(2))) if m else None


def _minutes(ts: str) -> int | None:
    m = re.match(r"(\d{1,2}):(\d{2})", ts or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _turns_today(scenario: dict) -> list[str]:
    content = scenario["content"]
    return [t["text"] for t in content["history"]] + [content["final_user_turn"]["text"]]


def time_problems(scenario: dict) -> list[str]:
    problems = []
    today, clock = _today(scenario)
    ctx = scenario["content"]["user_context"]
    if today is None:
        return ["time_of_day has no weekday"]

    # 1. Summary dates: weekday must match "vor N Tagen" counted from today.
    sessions = []
    for s in ctx["recent_sessions"]:
        wd = next((i for i, w in enumerate(WEEKDAYS) if w in s["date"]), None)
        m = re.search(r"vor (\d+) Tag", s["date"])
        if wd is not None and m:
            ago = int(m.group(1))
            if (today - ago) % 7 != wd:
                problems.append(f"summary date '{s['date']}' does not fit today ({WEEKDAYS[today]})")
            sessions.append((wd, ago, s["summary"] + " " + " ".join(s["notes"])))

    # 2. "am / nächsten <Weekday>" in an old summary that, read from that day,
    #    points to a day already past (or today), while today's conversation
    #    names the same weekday.
    today_text = " ".join(_turns_today(scenario))
    for wd, ago, text in sessions:
        for m in re.finditer(rf"\b(?:am|nächsten|kommenden|diesen) ({WD})\b(?!\s+(nächster|kommender|übernächster|in einer)\s+Woche)", text):
            target = WEEKDAYS.index(m.group(1))
            ahead = (target - wd) % 7 or 7
            if 0 <= ago - ahead and re.search(rf"\b{m.group(1)}\b", today_text) \
                    and not re.search(r"nächste[nr]? Woche|kommende[nr]? Woche", text):
                problems.append(f"summary '{WEEKDAYS[wd]}, vor {ago} Tagen' says 'am {m.group(1)}': read from that "
                                f"day it is already past (vor {ago - ahead} Tagen), but today's turns mention "
                                f"{m.group(1)} too; make clear which week is meant")

    # 3. heute / morgen / gestern next to a weekday in today's turns.
    for text in _turns_today(scenario):
        for word, shift in (("heute", 0), ("heut", 0), ("morgen", 1), ("übermorgen", 2), ("gestern", -1),
                            ("vorgestern", -2)):
            for m in re.finditer(rf"\b{word}\b,?\s+(?:am\s+|ist\s+|is\s+)?({WD})\b", text, re.IGNORECASE):
                if WEEKDAYS.index(m.group(1)) != (today + shift) % 7:
                    problems.append(f"'{m.group(0)}' does not fit today ({WEEKDAYS[today]})")

    # 4. Weekly routines against the weekday: no school on a weekend.
    for wd, ago, text in sessions:
        if WEEKDAYS[wd] in WEEKEND and SCHOOL_DAY.search(text):
            problems.append(f"summary '{WEEKDAYS[wd]}, vor {ago} Tagen' mentions school on a weekend")
    if WEEKDAYS[today] in WEEKEND and SCHOOL_DAY.search(today_text):
        problems.append(f"today ({WEEKDAYS[today]}) mentions school on a weekend")
    if re.search(r"samstags|sonntags", today_text + " ".join(t for *_, t in sessions), re.I) and \
            re.search(r"(samstags|sonntags)[^.]*Schule|Schule[^.]*(samstags|sonntags)", today_text, re.I):
        problems.append("weekend day and school in the same sentence")

    # 5. "heut Spätschicht" etc. while the clock time lies inside that shift.
    if clock is not None:
        for shift, (start, end) in SHIFTS.items():
            if re.search(rf"heut\w*[^.]*{shift}|{shift}[^.]*heut", today_text, re.I):
                hour = clock / 60 if clock / 60 >= 6 else clock / 60 + 24
                if start <= hour < end:
                    problems.append(f"'{shift}' today, and it is {clock // 60}:{clock % 60:02d} now: "
                                    f"check arrival and call times of that person")

    # 6. Timestamps: in order, near the clock time of time_of_day, no long gaps.
    stamps = [_minutes(t["timestamp"]) for t in scenario["content"]["history"] if t["role"] == "user"]
    stamps.append(_minutes(scenario["content"]["final_user_turn"]["timestamp"]))
    stamps = [s for s in stamps if s is not None]
    if any(b < a for a, b in zip(stamps, stamps[1:])):
        problems.append("user timestamps are not in order")
    if clock is not None and stamps and abs(stamps[0] - clock) > 30:
        problems.append(f"first timestamp is {abs(stamps[0] - clock)} min away from time_of_day")
    if any(b - a > 90 for a, b in zip(stamps, stamps[1:])):
        problems.append("gap of more than 90 minutes between user turns")
    return list(dict.fromkeys(problems))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß]+", text.lower())


def _grams(text: str, n: int = 3) -> set[tuple]:
    words = _tokens(text)
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def fragment_problems(scenarios: list[dict], ratio: float = 0.35) -> list[str]:
    """Pairs of TV, radio or other-person fragments with similar wording.
    Thresholds were set on the main set, where they flag the reviewer's
    examples (Auffahrunfall with twenty minutes, "Wo bin ich denn hier?")."""
    spans = [(s["id"], d["span"]) for s in scenarios for d in s["annotation"].get("disturbances", [])
             if not d["type"].startswith("stt") and d["type"] != "genuine_incoherence"]
    problems = []
    for (a, sa), (b, sb) in itertools.combinations(spans, 2):
        if a == b:
            continue
        shared = _grams(sa) & _grams(sb)
        if difflib.SequenceMatcher(None, _tokens(sa), _tokens(sb)).ratio() >= ratio or len(shared) >= 2:
            problems.append(f"similar fragments: {a} / {b}")
    return list(dict.fromkeys(problems))


def _user_text(scenario: dict) -> str:
    c = scenario["content"]
    return " ".join([t["text"] for t in c["history"] if t["role"] == "user"] + [c["final_user_turn"]["text"]])


STOPWORDS = set("""aber alles allem allen aller also andere anderen eigentlich erst etwas gerade freilich gestern
heute immer jetzt kommt können morgen nicht schon selbst unter wieder wirklich würde welche wochen tagen genau
gleich fertig wegen gekommen meinen damals""".split())


def situation_problems(scenarios: list[dict], names: set, threshold: float = 1.5) -> list[str]:
    """Pairs of scenarios whose user turns share several rare words (a word in
    only a few scenarios counts more). Lexical, so it flags shared storylines
    like "Nachfolger ... zusperrt", not paraphrases."""
    bags = {}
    for s in scenarios:
        words = re.findall(r"[A-Za-zÄÖÜäöüß]{5,}", _user_text(s))
        bags[s["id"]] = {w.lower() for w in words if w not in names and w.lower() not in STOPWORDS}
    df = Counter(w for bag in bags.values() for w in bag)
    problems = []
    for a, b in itertools.combinations(bags, 2):
        shared = [w for w in bags[a] & bags[b] if df[w] <= 5]
        if sum(1 / df[w] for w in shared) >= threshold:
            problems.append(f"similar situations: {a} / {b} ({', '.join(sorted(shared))})")
    return problems


def block_problems(scenarios: list[dict], blocks: dict) -> list[str]:
    """Known overused building blocks (configs/generate.yaml) found in more
    scenarios than allowed. `where`: opening (first user turn), fragment
    (disturbance spans) or text (user turns and memory)."""
    problems = []
    for label, rule in blocks.items():
        hits = []
        for s in scenarios:
            if rule["where"] == "opening":
                text = s["content"]["history"][0]["text"]
            elif rule["where"] == "fragment":
                text = " ".join(d["span"] for d in s["annotation"].get("disturbances", []))
            else:
                text = _user_text(s) + " " + str(s["content"]["user_context"])
            if re.search(rule["pattern"], text, re.I):
                hits.append(s["id"])
        if len(hits) > rule.get("max", 1):
            problems.append(f"block '{label}' in {len(hits)} scenarios: {', '.join(hits)}")
    return problems


def _opening_tokens(scenario: dict, n: int = 10) -> list[str]:
    text = scenario["content"]["history"][0]["text"].lower()
    tokens = [t for t in re.findall(r"[\wäöüß]+", text) if t != "mira"]
    return tokens[:n]


def opening_problems(scenarios: list[dict], threshold: float = 0.7) -> list[str]:
    """Pairs of scenarios whose first user turns start almost the same way."""
    problems = []
    openings = [(s["id"], _opening_tokens(s)) for s in scenarios]
    for i, (a, ta) in enumerate(openings):
        for b, tb in openings[i + 1:]:
            if ta and tb and difflib.SequenceMatcher(None, ta, tb).ratio() >= threshold:
                problems.append(f"near-identical openings: {a} / {b}")
    return problems
