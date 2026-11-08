"""Exploratory accumulation condition: derive 2 x 2 versions from written bases.

A writer produces one base per spec (prompts/generator_accumulation.en.md):
the full version with three disturbances and a neutral memory, plus for each
disturbance the replacement text, plus the sentence that contaminates memory.
The versions are derived here, mechanically, so that they differ only in the
varied factor:
  d3 / d1          three disturbances, or only the primary one (the other two
                   spans replaced by their `replacement`)
  neutral / primed memory without, or with, the confused-sounding sentence
                   and note appended to one earlier summary
Clean bases have no disturbances and give only neutral / primed.
"""

import copy
import json
import re

from .generate import _build_scenario, archive_current, load_config, make_specs, next_version, spec_message
from .inbox import INBOX, WRITER, _shape_problems, normalize_time
from .schema import ROOT, SCENARIO_DIR, content_hash, context_problems, load, save, scenario_path, turn_text, validate

SET = "accumulation"
BASES = SCENARIO_DIR / "accumulation_bases"
ADDENDUM = ROOT / "prompts" / "generator_accumulation.en.md"


def write_tasks() -> None:
    folder = INBOX / SET
    folder.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    specs = make_specs(SET, cfg)
    for spec in specs:
        text = (spec_message(spec, cfg) + "\n\nThis is an accumulation base. Follow the section in "
                "prompts/generator_accumulation.en.md in addition to prompts/generator.en.md.")
        (folder / f"{spec['id']}.task.md").write_text(text, encoding="utf-8")
    print(f"{len(specs)} task files in {folder.relative_to(ROOT)}")


def _set_turn(content: dict, index: int, text: str) -> None:
    if index == len(content["history"]):
        content["final_user_turn"]["text"] = text
    else:
        content["history"][index]["text"] = text


def _tidy(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    return re.sub(r"\s+([,.!?])", r"\1", text).strip()


def versions(base: dict, condition: str) -> dict[str, dict]:
    """{suffix: {"content", "annotation", "factors"}} for one base."""
    out = {}
    disturbances = base["annotation"].get("disturbances", [])
    counts = [3, 1] if condition != "clean" else [None]
    for n in counts:
        content = copy.deepcopy(base["content"])
        kept = []
        for d in disturbances:
            if n == 1 and not d["primary"]:
                scenario_like = {"content": content}
                old = turn_text(scenario_like, d["turn_index"])
                _set_turn(content, d["turn_index"], _tidy(old.replace(d["span"], d["replacement"], 1)))
            else:
                kept.append({k: d[k] for k in ("turn_index", "span", "type", "primary")})
        for memory in ("neutral", "primed"):
            c = copy.deepcopy(content)
            if memory == "primed":
                p = base["primed"]
                session = c["user_context"]["recent_sessions"][p["session_index"]]
                session["summary"] = session["summary"].rstrip() + " " + p["summary_sentence"].strip()
                session["notes"].append(p["note"])
            ann = {**{k: v for k, v in base["annotation"].items() if k != "disturbances"}, "disturbances": kept}
            suffix = f"d{n}_{memory}" if n else memory
            out[suffix] = {"content": c, "annotation": ann,
                           "factors": {"disturbances": n or 0, "memory": memory}}
    return out


def base_problems(base: dict, condition: str) -> list[str]:
    problems = _shape_problems(base)
    if problems:
        return problems
    p = base.get("primed") or {}
    if not {"session_index", "summary_sentence", "note"} <= set(p):
        problems.append("primed needs session_index, summary_sentence, note")
    elif not 0 <= p["session_index"] < len(base["content"]["user_context"]["recent_sessions"]):
        problems.append("primed.session_index out of range")
    else:
        # The sentence must point unambiguously at the person, not at someone
        # mentioned just before it in the summary (review of the first draft).
        first = base["content"]["user_context"]["name"].split()[0]
        problems += [f"primed.{k} must name the person ({first})" for k in ("summary_sentence", "note")
                     if not re.search(rf"\b{re.escape(first)}\b", p[k])]
    problems += context_problems(base["content"].get("user_context"))
    ds = base["annotation"].get("disturbances", [])
    if condition != "clean":
        if len(ds) != 3 or sum(bool(d.get("primary")) for d in ds) != 1:
            problems.append("needs exactly three disturbances, one of them primary")
        if len({d.get("turn_index") for d in ds}) != len(ds):
            problems.append("disturbances must sit in different turns")
        for d in ds:
            if "replacement" not in d:
                problems.append(f"disturbance in turn {d.get('turn_index')} has no replacement")
                continue
            text = turn_text(base, d["turn_index"])
            if text.count(d["span"]) != 1:
                problems.append(f"span not found exactly once in turn {d['turn_index']}: {d['span'][:40]!r}")
    return problems


def check() -> None:
    """Check written bases in the inbox, including every derived version."""
    from .checks import time_problems
    specs = {s["id"]: s for s in make_specs(SET, load_config())}
    for path in sorted((INBOX / SET).glob("*.json")):
        sid = path.stem
        base = json.loads(path.read_text(encoding="utf-8"))
        spec = specs[sid]
        problems = base_problems(base, spec["condition"])
        if not problems:
            for suffix, v in versions(base, spec["condition"]).items():
                s = {"id": f"{sid}_{suffix}", "condition": spec["condition"], "status": "draft", "spec": spec,
                     "content": v["content"], "annotation": v["annotation"]}
                problems += [f"{suffix}: {p}" for p in validate(s) + time_problems(s)]
            name = base["content"]["user_context"]["name"]
            if name != f"{spec['first_name']} {spec['last_name']}":
                problems.append(f"user name {name!r}, spec says {spec['first_name']} {spec['last_name']}")
        print(f"{sid}: {'OK' if not problems else '; '.join(dict.fromkeys(problems))}")


def import_bases() -> None:
    """Derive the versions of every written base and save them as drafts."""
    specs = {s["id"]: s for s in make_specs(SET, load_config())}
    BASES.mkdir(parents=True, exist_ok=True)
    for path in sorted((INBOX / SET).glob("*.json")):
        sid = path.stem
        base = json.loads(path.read_text(encoding="utf-8"))
        spec = specs[sid]
        problems = base_problems(base, spec["condition"])
        if problems:
            print(f"  {sid}: {'; '.join(problems)}, skipped")
            continue
        ctx = base["content"]["user_context"]
        ctx["dialect"] = spec["dialect"]
        ctx["time_of_day"] = normalize_time(ctx["time_of_day"])
        for turn in base["content"]["history"]:
            if turn.get("role") == "assistant":
                turn["timestamp"] = ""
        for suffix, v in versions(base, spec["condition"]).items():
            vid = f"{sid}_{suffix}"
            existing = scenario_path(SET, vid)
            if existing.exists():
                old = load(existing)
                if content_hash({"content": v["content"], "annotation": v["annotation"]}) == old["content_hash"]:
                    continue  # this version did not change; keep it, and its review status
                archive_current(SET, old)
            vspec = {**spec, "id": vid, "base_id": sid, "factors": v["factors"]}
            scenario = _build_scenario(vspec, {"content": v["content"], "annotation": v["annotation"]},
                                       WRITER, version=next_version(SET, vid))
            scenario["accumulation"] = {"base_id": sid, **v["factors"]}
            problems = validate(scenario)
            if problems:
                scenario["review"]["comment"] = "auto-validation: " + "; ".join(problems)
            save(scenario)
        (BASES / f"{sid}.json").write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
        path.unlink()
        (INBOX / SET / f"{sid}.task.md").unlink(missing_ok=True)
        print(f"  {sid}: {len(versions(base, spec['condition']))} versions imported")


def full_version_id(scenario: dict) -> str | None:
    """Id of the version that shows everything (three disturbances, primed memory)."""
    acc = scenario.get("accumulation")
    if not acc:
        return None
    return f"{acc['base_id']}_{'d3_primed' if acc['disturbances'] else 'primed'}"
