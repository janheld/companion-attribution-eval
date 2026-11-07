"""Assign names and interests across a whole scenario set, and check them.

Rules (set by the reviewer after calibration round 1):
  - user first names and surnames come from configs/names.yaml and occur at
    most once per set,
  - side characters get names from the same pools, never a user name of the
    same set, and each side name occurs in at most `side_name_cap` scenarios,
  - no two names in one scenario look alike (Theo / Theobald, Julia / Julian),
  - no interest is given to more than `max_share` of the scenarios.
Assignment is deterministic per set seed, so specs stay reproducible.

Sets written before the review of the main set (calibration, main) keep the
rules they were written with (`name_rules: v1`: base pools, cap 3, no
look-alike filter), so their specs can still be reproduced.
"""

import json
import random
import re
from collections import Counter

import yaml

from .schema import ROOT

NAMES_FILE = ROOT / "configs" / "names.yaml"
SIDE_KEYS = ("side_older", "side_younger", "side_surnames", "side_extra")


def load_names(extended: bool = True) -> dict:
    """Name pools; `extended` adds the *_added lists (names added after the main set)."""
    raw = yaml.safe_load(NAMES_FILE.read_text(encoding="utf-8"))
    pools = {k: v for k, v in raw.items() if not k.endswith("_added")}
    if extended:
        for key in pools:
            pools[key] = pools[key] + raw.get(f"{key}_added", [])
    return pools


def rules(set_cfg: dict, cfg: dict) -> dict:
    """Name rules of a set: v1 for sets written before the main-set review."""
    v1 = set_cfg.get("name_rules") == "v1"
    return {"extended": not v1, "cap": 3 if v1 else cfg["people"]["side_name_cap"], "lookalike": not v1}


def look_alike(a: str, b: str) -> bool:
    """Names that are easy to mix up when heard: same first four letters, or one starts the other."""
    a, b = a.lower(), b.lower()
    return a[:4] == b[:4] or a.startswith(b) or b.startswith(a)


def _pick(pool: list[str], counts: Counter, cap: int, exclude: set, rng: random.Random,
          avoid_like: set = frozenset()) -> str:
    """Least-used name under the cap, random among ties."""
    candidates = [n for n in pool if counts[n] < cap and n not in exclude
                  and not any(look_alike(n, m) for m in avoid_like)]
    if not candidates:
        raise SystemExit("Name pool too small for this set; extend configs/names.yaml.")
    low = min(counts[n] for n in candidates)
    name = rng.choice([n for n in candidates if counts[n] == low])
    counts[name] += 1
    return name


def assign(specs: list[dict], cfg: dict, set_cfg: dict, seed: int, reserved: list[dict] = ()) -> None:
    """Add user name, gender, side names, interests and job to every spec, in place.

    `reserved` are specs of scenarios that already exist in the same set (used
    when a set is extended): their names count against the limits, and their
    jobs and interests count against the caps.
    """
    rng = random.Random(seed * 100 + 99)
    rule = rules(set_cfg, cfg)
    names = load_names(rule["extended"])
    people = {**cfg["people"], **set_cfg.get("people", {})}
    fixed = set_cfg.get("fixed_people", {})
    keep_gender = set_cfg.get("keep_gender", {})

    # Names already in use by scenarios that stay unchanged.
    used_first = {f["first_name"] for f in fixed.values()} | {r["first_name"] for r in reserved}
    used_last = {f["last_name"] for f in fixed.values()} | {r["last_name"] for r in reserved}
    side_counts = Counter(n for f in fixed.values() for n in f["side_names"])
    side_counts.update(n for r in reserved for key in SIDE_KEYS for n in r.get(key, []))

    free = [s for s in specs if s["id"] not in fixed]
    # Scenarios renamed in place keep the gender they were written with.
    open_slots = [s for s in free if s["id"] not in keep_gender]
    allocated = iter(_allocate_genders(len(open_slots), people["female_share"], rng))
    genders = [keep_gender.get(s["id"]) or next(allocated) for s in free]
    pools = {"female": [n for n in names["older_female"] if n not in used_first],
             "male": [n for n in names["older_male"] if n not in used_first]}
    for pool in pools.values():
        rng.shuffle(pool)
    surnames = [n for n in names["surnames"] if n not in used_last]
    rng.shuffle(surnames)

    for spec, gender in zip(free, genders):
        spec["gender"] = gender
        spec["first_name"] = pools[gender].pop()
        spec["last_name"] = surnames.pop()
    for sid, f in fixed.items():
        spec = next(s for s in specs if s["id"] == sid)
        spec.update({k: f[k] for k in ("gender", "first_name", "last_name")})

    user_names = ({s["first_name"] for s in specs} | {s["last_name"] for s in specs}
                  | used_first | used_last)
    side_surnames = [n for n in names["surnames"] if n not in user_names]
    for index, spec in enumerate(free):
        mine = set()
        like = {spec["first_name"]} if rule["lookalike"] else set()
        for key, generation in (("side_older", "older"), ("side_younger", "younger")):
            # Alternate female and male names, so the writer can name a wife and
            # a brother, a daughter and a grandson, without changing genders.
            picked = []
            for i in range(people[key]):
                pool = names[f"{generation}_{'female' if (i + index) % 2 == 0 else 'male'}"]
                picked.append(_pick(pool, side_counts, rule["cap"], user_names | mine, rng, like))
                mine.add(picked[-1])
                if rule["lookalike"]:
                    like.add(picked[-1])
            spec[key] = picked
        spec["side_surnames"] = [_pick(side_surnames, side_counts, rule["cap"], user_names | mine, rng)
                                 for _ in range(people["side_surnames"])]

    for sid, extra in set_cfg.get("extra_side_names", {}).items():
        spec = next(s for s in specs if s["id"] == sid)
        spec["side_extra"] = list(extra)
        side_counts.update(extra)

    total = len(free) + len(reserved)
    _assign_jobs(free, cfg, people, total, reserved, rng)
    _assign_interests(free, cfg, people, total, reserved, rng)


def _allocate_genders(n: int, female_share: float, rng: random.Random) -> list[str]:
    women = round(n * female_share)
    genders = ["female"] * women + ["male"] * (n - women)
    rng.shuffle(genders)
    return genders


def _assign_jobs(specs, cfg, people, total, reserved, rng) -> None:
    """Former jobs spread evenly with a cap, like interests (calibration had six farmers)."""
    jobs = list(cfg["persona_hints"]["former_jobs"])
    cap = max(1, int(total * people["job_max_share"]))
    counts = Counter(j for j in jobs for r in reserved if r.get("former_job") in j.split("|"))
    for spec in specs:
        job = _pick(jobs, counts, cap, set(), rng)
        spec["former_job"] = job.split("|")[0 if spec["gender"] == "male" else 1]


def _assign_interests(specs, cfg, people, total, reserved, rng) -> None:
    """Two interests per scenario, spread evenly; no interest above the cap."""
    interests = list(cfg["persona_hints"]["interests"])
    cap = max(1, int(total * people["interest_max_share"]))
    counts = Counter(i for r in reserved for i in r.get("interests", []))
    for spec in specs:
        first = _pick(interests, counts, cap, set(), rng)
        spec["interests"] = [first, _pick(interests, counts, cap, {first}, rng)]


# --- Checks on a written set -------------------------------------------------

def _all_pool_names() -> set[str]:
    names = load_names()
    return {n for key in ("older_female", "older_male", "younger_female", "younger_male", "surnames")
            for n in names[key]}


def names_in(scenario: dict, pool: set[str]) -> set[str]:
    text = json.dumps(scenario["content"], ensure_ascii=False)
    words = set(re.findall(r"\b[A-ZÄÖÜ][\wäöüß]*(?:-[A-ZÄÖÜ][\wäöüß]*)?", text))
    return words & pool


def set_problems(scenarios: list[dict], set_cfg: dict, cfg: dict) -> list[str]:
    """Name rules across the whole set. Scenarios listed as fixed are exempt from pool checks."""
    pool = _all_pool_names()
    cap = rules(set_cfg, cfg)["cap"]
    fixed = set_cfg.get("fixed_people", {})
    problems, user_first, user_last, side = [], Counter(), Counter(), Counter()
    found_by_id = {}
    for s in scenarios:
        first, *_, last = s["content"]["user_context"]["name"].split()
        user_first[first] += 1
        user_last[last] += 1
        spec = s.get("spec", {})
        if s["id"] not in fixed and "first_name" in spec and (first, last) != (spec["first_name"], spec["last_name"]):
            problems.append(f"{s['id']}: user is {first} {last}, spec says {spec['first_name']} {spec['last_name']}")
        # A recognition error can turn a word into something that looks like a
        # name ("eahm" -> "Emma"); such words are not people.
        stt_words = {w for d in s["annotation"].get("disturbances", []) if d.get("type", "").startswith("stt")
                     for w in re.findall(r"[\wäöüÄÖÜß]+", d.get("span", ""))}
        found_by_id[s["id"]] = names_in(s, pool) - {first, last} - stt_words
        allowed = set(spec.get("side_older", []) + spec.get("side_younger", []) + spec.get("side_surnames", [])
                      + spec.get("side_extra", []))
        if s["id"] not in fixed and "side_older" in spec:
            extra = found_by_id[s["id"]] - allowed
            if extra:
                problems.append(f"{s['id']}: names not assigned to this scenario: {', '.join(sorted(extra))}")
        side.update(found_by_id[s["id"]])
        given = sorted(n for n in found_by_id[s["id"]] | {first} if n not in user_last and n != last)
        for i, a in enumerate(given):
            for b in given[i + 1:]:
                if look_alike(a, b):
                    problems.append(f"{s['id']}: look-alike names {a} / {b}")
    problems += [f"user first name {n} used {c} times" for n, c in user_first.items() if c > 1]
    problems += [f"user surname {n} used {c} times" for n, c in user_last.items() if c > 1]
    users = set(user_first) | set(user_last)
    for sid, found in found_by_id.items():
        clash = found & users
        if clash:
            problems.append(f"{sid}: side character carries a user name: {', '.join(sorted(clash))}")
    problems += [f"side name {n} in {c} scenarios (max {cap})" for n, c in side.items() if c > cap]
    return problems
