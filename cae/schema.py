"""Scenario files: loading, saving, hashing and status rules.

A scenario is one JSON file. Only `content` and `annotation` are hashed: they are
what a model run depends on. Review metadata (status, comment) can change
without changing the hash.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "scenarios"

ATTRIBUTION_CONDITIONS = ["clean", "tv_bleed", "stt_errors", "incoherent_user", "recovery"]
CONTACT_CONDITION = "contact"
CONDITIONS = ATTRIBUTION_CONDITIONS + [CONTACT_CONDITION]

STATUSES = ["draft", "approved", "rejected", "needs_edit"]

DISTURBANCE_TYPES = {
    "tv_bleed": ["tv_news", "tv_film", "weather", "traffic", "ad", "radio", "other_person"],
    "stt_errors": ["stt_name", "stt_cutoff", "stt_phonetic", "stt_dialect"],
    "incoherent_user": ["genuine_incoherence"],
    # Recovery: the disturbance that triggered the scripted misreading.
    "recovery": ["tv_news", "tv_film", "weather", "traffic", "ad", "radio", "other_person"],
    "clean": [],
    "contact": [],
}
CONTACT_TYPES = ["visit", "call", "invitation", "new_acquaintance"]
POSITIONS = ["final_turn", "history", "none"]


def canonical_json(obj) -> str:
    # Sorted keys and fixed separators so the same content always hashes the same.
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(scenario: dict) -> str:
    payload = {"content": scenario["content"], "annotation": scenario["annotation"]}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def scenario_path(set_name: str, scenario_id: str) -> Path:
    return SCENARIO_DIR / set_name / f"{scenario_id}.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(scenario: dict) -> Path:
    path = scenario_path(scenario["set"], scenario["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_set(set_name: str) -> list[dict]:
    files = sorted((SCENARIO_DIR / set_name).glob("*.json"))
    return [load(f) for f in files]


def sync_status(scenario: dict) -> bool:
    """Reset an approved scenario to draft if its text was edited after approval.

    Returns True if the scenario changed. This is what makes direct JSON edits
    safe: an edited scenario has to be reviewed again before it can be frozen.
    """
    current = content_hash(scenario)
    if scenario.get("content_hash") == current:
        return False
    if scenario.get("status") == "approved":
        scenario["status"] = "draft"
        note = "auto: content changed after approval, needs review again"
        scenario["review"]["comment"] = (scenario["review"].get("comment", "") + "\n" + note).strip()
    scenario["content_hash"] = current
    return True


def validate(scenario: dict) -> list[str]:
    """Return a list of problems; empty means the scenario is structurally valid."""
    problems = []
    cond = scenario.get("condition")
    if cond not in CONDITIONS:
        problems.append(f"unknown condition {cond!r}")
        return problems
    if scenario.get("status") not in STATUSES:
        problems.append(f"unknown status {scenario.get('status')!r}")
    content = scenario.get("content", {})
    history = content.get("history", [])
    if not 6 <= len(history) <= 12:
        problems.append(f"history has {len(history)} turns, expected 6 to 12")
    for i, turn in enumerate(history):
        if turn.get("role") not in ("user", "assistant"):
            problems.append(f"turn {i}: bad role")
        if turn.get("role") == "user" and not turn.get("timestamp"):
            problems.append(f"turn {i}: user turn without timestamp")
    if history and history[0].get("role") != "user":
        problems.append("history must start with a user turn")
    if history and history[-1].get("role") != "assistant":
        problems.append("history must end with an assistant turn (final user turn follows)")
    for a, b in zip(history, history[1:]):
        if a.get("role") == b.get("role"):
            problems.append("history roles must alternate")
            break
    final = content.get("final_user_turn", {})
    if not final.get("text") or not final.get("timestamp"):
        problems.append("final_user_turn needs text and timestamp")

    ann = scenario.get("annotation", {})
    pos = ann.get("disturbance_position")
    if pos not in POSITIONS:
        problems.append(f"bad disturbance_position {pos!r}")
    if cond in ("clean", "contact") and (pos != "none" or ann.get("disturbances")):
        problems.append(f"{cond} must not contain disturbances")
    if cond not in ("clean", "contact"):
        if not ann.get("disturbances"):
            problems.append("condition needs at least one annotated disturbance")
        allowed = DISTURBANCE_TYPES[cond]
        for d in ann.get("disturbances", []):
            if d.get("type") not in allowed:
                problems.append(f"disturbance type {d.get('type')!r} not allowed for {cond}")
            idx = d.get("turn_index")
            in_final = idx == len(history)
            if not (in_final or (isinstance(idx, int) and 0 <= idx < len(history))):
                problems.append(f"disturbance turn_index {idx} out of range")
    # Requests for unavailable actions only in clean and contact, so the
    # side label never interferes with the attribution measurement.
    has_request = bool(ann.get("unavailable_action_request"))
    if has_request and cond not in ("clean", "contact"):
        problems.append(f"{cond} must not contain a request for an unavailable action")
    if "action_request" in scenario.get("spec", {}) and has_request != bool(scenario["spec"]["action_request"]):
        problems.append("unavailable_action_request does not match the spec")
    if cond == "contact" and ann.get("contact_type") not in CONTACT_TYPES:
        problems.append("contact scenario needs a contact_type")
    return problems


def turn_text(scenario: dict, index: int) -> str:
    """Text of a turn by index; index == len(history) means the final user turn."""
    history = scenario["content"]["history"]
    if index == len(history):
        return scenario["content"]["final_user_turn"]["text"]
    return history[index]["text"]
