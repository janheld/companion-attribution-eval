"""Write scenarios without the API: tasks out, drafts in.

`tasks` writes one task file per scenario to scenarios/inbox/<set>/: the exact
spec message the API generator would receive (including the revision block for
rejected / needs_edit scenarios). A writer (here: Claude Code, working from
prompts/generator.en.md) answers each task with <id>.json holding
{"content": ..., "annotation": ...}, the same shape as the API's structured output.

`import` wraps those answers exactly like API output, validates them and saves
them as `draft`. Nothing here can approve a scenario; review stays the gate.
The generator field records `via: claude-code`, so the provenance of every
scenario stays visible.
"""

import json
import re

from .generate import (_build_scenario, archive_current, load_config, make_specs,
                       next_version, revision_input, spec_message)
from .schema import SCENARIO_DIR, load, load_set, save, scenario_path, validate

INBOX = SCENARIO_DIR / "inbox"
WRITER = {"model": "claude-opus-5-5", "via": "claude-code"}
NAME_KEYS = ("gender", "first_name", "last_name", "side_older", "side_younger", "side_surnames", "side_extra")


def _targets(set_name: str, only_ids: list[str] | None) -> list[tuple[dict, dict | None]]:
    """(spec, existing scenario or None) for every scenario that needs writing."""
    out = []
    for spec in make_specs(set_name, load_config()):
        if only_ids and spec["id"] not in only_ids:
            continue
        path = scenario_path(set_name, spec["id"])
        if not path.exists():
            out.append((spec, None))
            continue
        old = load(path)
        if old["status"] in ("rejected", "needs_edit"):
            out.append((old["spec"], old))
    return out


def write_tasks(set_name: str, only_ids: list[str] | None = None) -> None:
    folder = INBOX / set_name
    folder.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    targets = _targets(set_name, only_ids)
    for spec, old in targets:
        revision = revision_input(old) if old else None
        (folder / f"{spec['id']}.task.md").write_text(spec_message(spec, cfg, revision), encoding="utf-8")
    print(f"{len(targets)} task files in {folder.relative_to(SCENARIO_DIR.parent)}")


def normalize_time(value: str) -> str:
    """'Freitag, Vormittag, 9:35 Uhr' -> 'Freitag, 09:35', the form the API generator uses."""
    match = re.search(r"(\d{1,2}):(\d{2})", value)
    if not match:
        return value
    weekday = value.split(",")[0].strip()
    return f"{weekday}, {int(match.group(1)):02d}:{match.group(2)}"


def _shape_problems(data: dict) -> list[str]:
    problems = [f"missing key {k}" for k in ("content", "annotation") if k not in data]
    if not problems:
        problems += [f"missing content.{k}" for k in ("user_context", "history", "final_user_turn")
                     if k not in data["content"]]
        problems += [f"missing annotation.{k}" for k in ("disturbance_position", "disturbances",
                                                         "contact_type", "unavailable_action_request", "rationale")
                     if k not in data["annotation"]]
    return problems


def import_drafts(set_name: str, overwrite_drafts: bool = False) -> None:
    folder = INBOX / set_name
    specs = {s["id"]: s for s in make_specs(set_name, load_config())}
    for answer in sorted(folder.glob("*.json")):
        sid = answer.stem
        try:
            data = json.loads(answer.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  {sid}: invalid JSON ({e}), skipped")
            continue
        problems = _shape_problems(data)
        if problems:
            print(f"  {sid}: {'; '.join(problems)}, skipped")
            continue
        path = scenario_path(set_name, sid)
        old = load(path) if path.exists() else None
        # Approved scenarios are never overwritten. Drafts only on request
        # (e.g. renaming in place), so a stray inbox file cannot replace one.
        replaceable = ("rejected", "needs_edit") + (("draft",) if overwrite_drafts else ())
        if old and old["status"] not in replaceable:
            print(f"  {sid}: existing scenario is {old['status']}, not overwritten")
            continue
        if old:
            archive_current(set_name, old)
        spec = old["spec"] if old else specs[sid]
        if old:
            # Name assignments are set-wide and may have been added after this
            # scenario was written; fill in missing ones, never replace stored ones.
            spec = {**{k: specs[sid][k] for k in NAME_KEYS if k in specs[sid]}, **spec}
        # Metadata the writer may format differently: the dialect label comes from
        # the spec, and companion turns carry no timestamp (only user turns do).
        ctx = data["content"]["user_context"]
        ctx["dialect"] = spec["dialect"]
        ctx["time_of_day"] = normalize_time(ctx["time_of_day"])
        for turn in data["content"]["history"]:
            if turn.get("role") == "assistant":
                turn["timestamp"] = ""
        scenario = _build_scenario(spec, data, WRITER, version=next_version(set_name, sid))
        problems = validate(scenario)
        if problems:
            scenario["review"]["comment"] = "auto-validation: " + "; ".join(problems)
        save(scenario)
        answer.unlink()
        (folder / f"{sid}.task.md").unlink(missing_ok=True)
        (folder / f"{sid}.rename.md").unlink(missing_ok=True)
        flag = f"  ({len(problems)} validation problems)" if problems else ""
        print(f"  {sid} v{scenario['version']}: imported{flag}")


def check_inbox(set_name: str, only_ids: list[str] | None = None) -> None:
    """Check written answers before import: structure, names against the spec, time."""
    from .checks import time_problems
    from .people import _all_pool_names, names_in
    specs = {s["id"]: s for s in make_specs(set_name, load_config())}
    pool = _all_pool_names()
    users = {w for sc in load_set(set_name) for w in sc["content"]["user_context"]["name"].split()}
    for answer in sorted((INBOX / set_name).glob("*.json")):
        sid = answer.stem
        if only_ids and sid not in only_ids:
            continue
        data = json.loads(answer.read_text(encoding="utf-8"))
        # A revision is checked against the spec stored with the scenario (the
        # record of what it was written with), a new scenario against make_specs.
        path = scenario_path(set_name, sid)
        spec = specs[sid]
        if path.exists():
            # Same merge as on import: stored spec, plus name keys added since.
            spec = {**{k: specs[sid][k] for k in NAME_KEYS if k in specs[sid]}, **load(path)["spec"]}
        scenario = {"id": sid, "condition": spec["condition"], "status": "draft", "spec": spec, **data}
        problems = _shape_problems(data) or validate(scenario)
        allowed = {spec.get("first_name"), spec.get("last_name")} | {
            n for k in ("side_older", "side_younger", "side_surnames", "side_extra") for n in spec.get(k, [])}
        stt_words = {w for d in data["annotation"].get("disturbances", []) if d.get("type", "").startswith("stt")
                     for w in re.findall(r"[\wäöüÄÖÜß]+", d.get("span", ""))}
        extra = names_in(data, pool) - allowed - stt_words
        if extra:
            problems.append(f"names not assigned to this scenario: {', '.join(sorted(extra))}")
        own = set(data["content"]["user_context"].get("name", "").split())
        clash = (names_in(data, pool) - own) & users
        if clash:
            problems.append(f"side character carries a user name of the set: {', '.join(sorted(clash))}")
        name = data["content"]["user_context"].get("name", "")
        if spec.get("first_name") and name != f"{spec['first_name']} {spec['last_name']}":
            problems.append(f"user name is {name!r}, spec says {spec['first_name']} {spec['last_name']}")
        problems += [f"time: {p}" for p in time_problems(scenario)]
        print(f"{sid}: {'OK' if not problems else '; '.join(problems)}")
