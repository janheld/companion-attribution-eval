"""Generate scenario drafts and revise them from review comments.

Generated scenarios always start as `draft`. Nothing here can approve a scenario.
"""

import hashlib
import json
import random
import shutil
from collections import Counter

import yaml

from . import cost, llm, people
from .schema import (CONTACT_TYPES, DISTURBANCE_TYPES, ROOT, SCENARIO_DIR,
                     content_hash, load_set, save, scenario_path, validate)

CONFIG = ROOT / "configs" / "generate.yaml"
PROMPT = ROOT / "prompts" / "generator.en.md"


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


# --- Output schema for structured outputs ---------------------------------

def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props,
            "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}


def output_schema() -> dict:
    all_types = sorted({t for ts in DISTURBANCE_TYPES.values() for t in ts})
    user_context = _obj({
        "name": _STR,
        # The companion always uses "du" (product rule), so the generator may not pick "Sie".
        "address_form": {"type": "string", "enum": ["du"]},
        "dialect": _STR,
        "relationship_phase": _obj({"phase": _STR, "days": {"type": "integer"}}),
        "time_of_day": _STR,
        "last_conversation_note": _STR,
        "caregiver_notes": {"type": "array", "items": _obj({"author": _STR, "text": _STR})},
        "knowledge_blocks": {"type": "array", "items": _obj({"topic": _STR, "text": _STR})},
        "recent_sessions": {"type": "array", "items": _obj({
            "date": _STR, "summary": _STR, "notes": {"type": "array", "items": _STR}})},
    })
    turn = _obj({"role": {"type": "string", "enum": ["user", "assistant"]},
                 "timestamp": _STR, "text": _STR})
    content = _obj({
        "user_context": user_context,
        "history": {"type": "array", "items": turn},
        "final_user_turn": _obj({"timestamp": _STR, "text": _STR}),
    })
    annotation = _obj({
        "disturbance_position": {"type": "string", "enum": ["final_turn", "history", "none"]},
        "disturbances": {"type": "array", "items": _obj({
            "turn_index": {"type": "integer"}, "span": _STR,
            "type": {"type": "string", "enum": all_types}})},
        "contact_type": {"type": "string", "enum": CONTACT_TYPES + ["none"]},
        "unavailable_action_request": {"type": "boolean"},
        "rationale": _STR,
    })
    return {"type": "json_schema", "schema": _obj({"content": content, "annotation": annotation})}


# --- Specs: what each scenario should be -----------------------------------

def _allocate(options: list, n: int, rng: random.Random, weights: list | None = None) -> list:
    """Spread n items over options by weight, exactly (not by sampling), then shuffle.

    Exact allocation keeps small sets balanced; sampling could give a
    calibration set with three Bavarian speakers by chance.
    """
    weights = weights or [1] * len(options)
    total = sum(weights)
    counts = [int(n * w / total) for w in weights]
    # Ties are broken at random; otherwise the first options in the list
    # (e.g. Monday, Tuesday) would always get the leftover slots.
    tiebreak = [rng.random() for _ in options]
    remainders = sorted(range(len(options)), key=lambda i: (n * weights[i] / total - counts[i], tiebreak[i]),
                        reverse=True)
    for i in remainders[: n - sum(counts)]:
        counts[i] += 1
    items = [o for o, c in zip(options, counts) for _ in range(c)]
    rng.shuffle(items)
    return items


def make_specs(set_name: str, cfg: dict) -> list[dict]:
    set_cfg = cfg["sets"][set_name]
    specs = _condition_specs(set_name, set_cfg, cfg)
    # Names, interests and jobs are assigned across the whole set, not per
    # condition, because their limits (unique, capped) are set-wide.
    people.assign(specs, cfg, set_cfg, set_cfg["seed"])
    _assign_situations(specs, cfg, random.Random(set_cfg["seed"] * 100 + 98))
    # A set can be extended later (calibration round 2) without moving any
    # existing spec: additions have their own seed and id offset, and the
    # specs stored in already written scenarios are reserved for the name and
    # cap rules (they are the record of what those scenarios use).
    add = set_cfg.get("additions")
    if add:
        extra = _condition_specs(set_name, {**set_cfg, **add}, cfg, id_offset=add["id_offset"])
        _spread_over_set(extra, cfg, random.Random(add["seed"]))
        written = _written_specs(set_name, {s["id"] for s in extra})
        people.assign(extra, cfg, {}, add["seed"], reserved=written)
        _assign_situations(extra, cfg, random.Random(add["seed"] * 100 + 98), reserved=written)
        specs += extra
    return specs


def _spread_over_set(specs: list[dict], cfg: dict, rng: random.Random) -> None:
    """With one scenario per condition, per-condition allocation would give every
    scenario the most frequent dialect and phase; allocate them across the batch."""
    phases = cfg["relationship_phases"]
    dialects = _allocate(list(cfg["dialects"]), len(specs), rng, list(cfg["dialects"].values()))
    phase_names = _allocate(list(phases), len(specs), rng, [p["weight"] for p in phases.values()])
    two_way = [s for s in specs if len(cfg["positions"][s["condition"]]) > 1]
    for spec, position in zip(two_way, _allocate(["final_turn", "history"], len(two_way), rng)):
        spec["disturbance_position"] = position
    for spec, dialect, phase in zip(specs, dialects, phase_names):
        spec["dialect"] = dialect
        spec["relationship_phase"] = phase
        spec["days"] = rng.randint(*phases[phase]["days"])


def _assign_situations(specs: list[dict], cfg: dict, rng: random.Random, reserved: list[dict] = ()) -> None:
    """Occasion (fitting the time of day, capped) and opening style (spread evenly)."""
    occasions = cfg["occasions"]
    counts = Counter(r.get("occasion") for r in reserved if r.get("occasion"))
    cap = max(1, int((len(specs) + len(reserved)) * cfg["occasion_max_share"]))
    for spec in specs:
        fitting = [o for o, times in occasions.items() if spec["time_of_day"] in times]
        spec["occasion"] = people._pick(fitting, counts, cap, set(), rng)
    for spec, style in zip(specs, _allocate(cfg["opening_styles"], len(specs), rng)):
        spec["opening_style"] = style


def _written_specs(set_name: str, exclude: set[str]) -> list[dict]:
    folder = SCENARIO_DIR / set_name
    stored = [json.loads(p.read_text(encoding="utf-8")).get("spec", {}) for p in sorted(folder.glob("*.json"))]
    return [s for s in stored if s.get("first_name") and s.get("id") not in exclude]


def _condition_specs(set_name: str, set_cfg: dict, cfg: dict, id_offset: int = 0) -> list[dict]:
    specs = []
    for cond_index, (cond, n) in enumerate(set_cfg["counts"].items()):
        rng = random.Random(set_cfg["seed"] * 100 + cond_index)
        dialects = _allocate(list(cfg["dialects"]), n, rng, list(cfg["dialects"].values()))
        phases = cfg["relationship_phases"]
        phase_names = _allocate(list(phases), n, rng, [p["weight"] for p in phases.values()])
        positions = _allocate(cfg["positions"][cond], n, rng)
        types = _allocate(DISTURBANCE_TYPES[cond], n, rng) if DISTURBANCE_TYPES[cond] else [None] * n
        contacts = _allocate(CONTACT_TYPES, n, rng) if cond == "contact" else [None] * n
        times = _allocate(cfg["times_of_day"], n, rng)
        weekdays = _allocate(cfg["weekdays"], n, rng)
        health = _allocate(cfg["persona_hints"]["health"], n, rng)
        relatives = _allocate(cfg["persona_hints"]["relatives"], n, rng)
        req = cfg["action_requests"]
        if cond in req["conditions"]:
            has_request = _allocate([True, False], n, rng, [req["share"], 1 - req["share"]])
        else:
            has_request = [False] * n
        forced = set_cfg.get("force_action_request", [])
        if cond == "recovery":
            # Varied wording of the scripted misreading, and a spread from hard
            # cases (the broadcast itself sounds confused) to easy ones.
            misreadings = _allocate(cfg["recovery"]["misreadings"], n, rng)
            difficulties = _allocate(list(cfg["recovery"]["difficulty"]), n, rng)
        else:
            misreadings = difficulties = [None] * n
        # Added after the main set was written: own random stream, so the
        # draws above (and the specs of written scenarios) do not move.
        extra_rng = random.Random(set_cfg["seed"] * 100 + 50 + cond_index)
        corrections, forgetful = _recovery_extras(difficulties, cfg, extra_rng) if cond == "recovery" \
            else ([None] * n, [False] * n)
        forms = _allocate(cfg["incoherence_forms"], n, extra_rng) if cond == "incoherent_user" else [None] * n
        for i in range(n):
            phase = phase_names[i]
            hints = cfg["persona_hints"]
            specs.append({
                "id": f"{cond}_{id_offset + i + 1:03d}",
                "set": set_name,
                "condition": cond,
                "dialect": dialects[i],
                "relationship_phase": phase,
                "days": rng.randint(*phases[phase]["days"]),
                "time_of_day": times[i],
                "weekday": weekdays[i],
                "disturbance_position": positions[i],
                "main_disturbance_type": types[i],
                "contact_type": contacts[i],
                "household": _fitting_household(rng.choice(hints["household"]), relatives[i], hints, extra_rng),
                "history_turns": rng.choice([6, 8, 10, 12]),
                "health": health[i],
                "relatives": relatives[i],
                "misreading": misreadings[i],
                "recovery_difficulty": difficulties[i],
                "correction_style": corrections[i],
                "forgetfulness_note": forgetful[i],
                "incoherence_form": forms[i],
                "action_request": (rng.choice(req["kinds"])
                                   if has_request[i] or f"{cond}_{id_offset + i + 1:03d}" in forced else None),
            })
    return specs


def _recovery_extras(difficulties: list, cfg: dict, rng: random.Random) -> tuple[list, list]:
    """Correction style per difficulty, and a forgetfulness note for some hard cases."""
    rec = cfg["recovery"]
    corrections, forgetful = [None] * len(difficulties), [False] * len(difficulties)
    for level, styles in rec["correction_styles"].items():
        idx = [i for i, d in enumerate(difficulties) if d == level]
        for i, style in zip(idx, _allocate(styles, len(idx), rng)):
            corrections[i] = style
        if level == "hard":
            share = rec["forgetfulness_note_share_hard"]
            for i, note in zip(idx, _allocate([True, False], len(idx), rng, [share, 1 - share])):
                forgetful[i] = note
    return corrections, forgetful


def _fitting_household(household: str, relatives: str, hints: dict, rng: random.Random) -> str:
    """Redraw a household that contradicts the relatives hint (never married, but a granddaughter)."""
    def fits(h):
        return not any(word in relatives for word in hints["household_excludes"].get(h, []))
    return household if fits(household) else rng.choice([h for h in hints["household"] if fits(h)])


def spec_message(spec: dict, cfg: dict, revision: dict | None = None) -> str:
    lines = [
        "Write one scenario with this specification.",
        f"- condition: {spec['condition']}",
        f"- dialect: {spec['dialect']}",
        f"- relationship phase: {spec['relationship_phase']}, day {spec['days']}",
        f"- today: {spec.get('weekday', 'any weekday')}, {spec['time_of_day']}",
        f"- user: {spec['first_name']} {spec['last_name']} ({spec['gender']})" if spec.get("first_name") else "- user: any name",
        f"- household: {spec['household']}; interests: {', '.join(spec['interests'])}; former job: {spec['former_job']}",
        f"- history length: exactly {spec['history_turns']} turns",
        *([f"- occasion: {spec['occasion']}", f"- first user turn: {spec['opening_style']}"] if spec.get("occasion") else []),
        f"- disturbance position: {spec['disturbance_position']}",
    ]
    if spec["main_disturbance_type"]:
        lines.append(f"- main disturbance type: {spec['main_disturbance_type']}")
    if spec["contact_type"]:
        lines.append(f"- contact type: {spec['contact_type']}")
    else:
        lines.append("- contact_type in the annotation: none")
    if spec.get("side_older"):
        extra = f"; also allowed: {', '.join(spec['side_extra'])}" if spec.get("side_extra") else ""
        lines.append(f"- names for side characters, use only these: own generation {', '.join(spec['side_older'])}; "
                     f"children or grandchildren {', '.join(spec['side_younger'])}; "
                     f"surname for a doctor, neighbor or acquaintance {', '.join(spec['side_surnames'])}{extra}")
    if spec.get("health"):
        lines.append(f"- health: {spec['health']}; relatives: {spec['relatives']}")
    if spec.get("action_request"):
        lines.append(f"- action request in the final user turn: {spec['action_request']}")
    if spec["condition"] == "recovery":
        misreading = spec.get("misreading") or cfg["recovery"]["misreadings"][0]
        lines.append(f"- scripted misreading (last history turn, word for word): \"{misreading}\"")
        if spec.get("recovery_difficulty"):
            lines.append(f"- recovery difficulty: {spec['recovery_difficulty']} "
                         f"({cfg['recovery']['difficulty'][spec['recovery_difficulty']]})")
        if spec.get("correction_style"):
            lines.append(f"- correction style: {spec['correction_style']}")
        if spec.get("forgetfulness_note"):
            lines.append("- forgetfulness note: yes (one caregiver note on mild, ordinary forgetfulness)")
    if spec.get("incoherence_form"):
        lines.append(f"- incoherence form: {spec['incoherence_form']}")
    if revision:
        lines += ["", "This is a revision. The reviewer gave this feedback on the previous version:",
                  revision["comment"] or "(no comment, status: " + revision["status"] + ")",
                  "", "Previous version:", json.dumps(revision["previous"], ensure_ascii=False, indent=1),
                  "", "Write an improved version that addresses the feedback. Keep what was not criticized."]
    return "\n".join(lines)


# --- Generation -------------------------------------------------------------

def _request(spec: dict, cfg: dict, revision: dict | None = None) -> dict:
    gen = cfg["generator"]
    system = [{"type": "text", "text": PROMPT.read_text(encoding="utf-8"),
               "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": spec_message(spec, cfg, revision)}]
    return llm.build_params(gen["model"], gen["settings"], system, messages, output_schema())


def _build_scenario(spec: dict, data: dict, generator: dict, version: int) -> dict:
    ann = data["annotation"]
    if ann.get("contact_type") == "none":
        ann["contact_type"] = None
    scenario = {
        "id": spec["id"], "set": spec["set"], "kind": "contact" if spec["condition"] == "contact" else "attribution",
        "condition": spec["condition"], "version": version,
        "status": "draft", "review": {"comment": "", "reviewed_at": None},
        "content_hash": "",
        "generator": {**generator, "prompt_sha256": prompt_sha256()},
        "spec": spec,
        "content": data["content"],
        "annotation": ann,
    }
    scenario["content_hash"] = content_hash(scenario)
    return scenario


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT.read_bytes()).hexdigest()


def next_version(set_name: str, scenario_id: str) -> int:
    """Next version number, counting archived versions, so a fresh rewrite never reuses one."""
    archived = (SCENARIO_DIR / "archive" / set_name).glob(f"{scenario_id}.v*.json")
    versions = [int(p.stem.rsplit(".v", 1)[1]) for p in archived]
    current = scenario_path(set_name, scenario_id)
    if current.exists():
        versions.append(json.loads(current.read_text(encoding="utf-8"))["version"])
    return max(versions, default=0) + 1


def archive_current(set_name: str, scenario: dict) -> None:
    """Keep the old version before a revision overwrites it."""
    archive = SCENARIO_DIR / "archive" / set_name
    archive.mkdir(parents=True, exist_ok=True)
    shutil.copy(scenario_path(set_name, scenario["id"]),
                archive / f"{scenario['id']}.v{scenario['version']}.json")


def revision_input(old: dict) -> dict:
    return {"comment": old["review"]["comment"], "status": old["status"],
            "previous": {"content": old["content"], "annotation": old["annotation"]}}


def _estimate(n: int, cfg: dict) -> float:
    prompt_tokens = len(PROMPT.read_text(encoding="utf-8")) / 3.5
    return n * cost.estimate(cfg["generator"]["model"], prompt_tokens + 400, cfg["est_output_tokens"])


def generate(set_name: str, only_ids: list[str] | None = None, assume_yes: bool = False) -> None:
    cfg = load_config()
    specs = make_specs(set_name, cfg)
    if only_ids:
        specs = [s for s in specs if s["id"] in only_ids]
    todo = [s for s in specs if not scenario_path(set_name, s["id"]).exists()]
    print(f"{len(todo)} of {len(specs)} scenarios to generate in set '{set_name}'.")
    if not todo:
        return
    cost.check_budget(_estimate(len(todo), cfg), cfg["budget_usd"], assume_yes)
    for spec in todo:
        _generate_one(spec, cfg, version=1)


def _generate_one(spec: dict, cfg: dict, version: int, revision: dict | None = None) -> None:
    params = _request(spec, cfg, revision)
    record = llm.call(params, labels={"task": "generate", "id": spec["id"], "version": version},
                      run_id=f"generate:{spec['set']}")
    if record["stop_reason"] != "end_turn":
        print(f"  {spec['id']}: stop_reason={record['stop_reason']}, skipped")
        return
    generator = {"model": cfg["generator"]["model"], "via": "api", "cache_key": record["key"]}
    scenario = _build_scenario(spec, json.loads(record["text"]), generator, version)
    problems = validate(scenario)
    if problems:
        scenario["review"]["comment"] = "auto-validation: " + "; ".join(problems)
    save(scenario)
    flag = f"  ({len(problems)} validation problems)" if problems else ""
    print(f"  {spec['id']} v{version}: ${record['cost_usd']:.3f}{flag}")


def revise(set_name: str, assume_yes: bool = False) -> None:
    """Regenerate every rejected or needs_edit scenario, using the review comment."""
    cfg = load_config()
    targets = [s for s in load_set(set_name) if s["status"] in ("rejected", "needs_edit")]
    print(f"{len(targets)} scenarios to revise in set '{set_name}'.")
    if not targets:
        return
    cost.check_budget(_estimate(len(targets), cfg) * 1.5, cfg["budget_usd"], assume_yes)
    for old in targets:
        archive_current(set_name, old)
        _generate_one(old["spec"], cfg, version=old["version"] + 1, revision=revision_input(old))
