"""Freeze a scenario set: record exactly which approved versions are evaluated."""

import json
from datetime import datetime, timezone

from .schema import SCENARIO_DIR, load_set, save, sync_status

FROZEN_DIR = SCENARIO_DIR / "frozen"


def manifest_path(set_name: str):
    return FROZEN_DIR / f"{set_name}.manifest.json"


def freeze(set_name: str) -> None:
    scenarios = load_set(set_name)
    for s in scenarios:
        if sync_status(s):
            save(s)
    not_approved = [s["id"] for s in scenarios if s["status"] != "approved"]
    if not scenarios or not_approved:
        raise SystemExit(f"Cannot freeze '{set_name}': not approved: {not_approved or 'empty set'}")
    manifest = {
        "set": set_name,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": {s["id"]: {"version": s["version"], "content_hash": s["content_hash"]} for s in scenarios},
    }
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path(set_name).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Froze {len(scenarios)} scenarios of '{set_name}'.")


def load_frozen(set_name: str) -> list[dict]:
    """Return the frozen scenarios, or stop if anything differs from the manifest.

    This is the gate in front of every model run.
    """
    path = manifest_path(set_name)
    if not path.exists():
        raise SystemExit(f"Set '{set_name}' is not frozen. Review, approve all, then run freeze.")
    manifest = json.loads(path.read_text(encoding="utf-8"))["scenarios"]
    scenarios = load_set(set_name)
    problems = []
    for s in scenarios:
        sync_status(s)
        entry = manifest.get(s["id"])
        if s["status"] != "approved":
            problems.append(f"{s['id']}: status {s['status']}")
        elif entry is None:
            problems.append(f"{s['id']}: not in manifest")
        elif entry["content_hash"] != s["content_hash"]:
            problems.append(f"{s['id']}: content changed since freeze")
    missing = set(manifest) - {s["id"] for s in scenarios}
    problems += [f"{sid}: in manifest but file missing" for sid in sorted(missing)]
    if problems:
        raise SystemExit("Refusing to run:\n  " + "\n  ".join(problems))
    return scenarios
