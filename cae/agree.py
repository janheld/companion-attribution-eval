"""Agreement between the author's gold labels and the grader, while the rubric
is sharpened on the development part, and once at the end on the held-out part.

- `grade_items(split)` grades the gold items of a split with the rubric as it
  is now. Grades are stored per rubric hash (runs/gold_grades/<hash>/), so
  every rubric version keeps its own comparison. Calls go through the response
  cache: an unchanged rubric costs nothing.
- `agree(split="dev")` compares and writes a disagreement page. It refuses the
  held-out part.
- `agree_final()` is the one and only held-out evaluation: it requires the
  rubric to be committed, grades the held-out items with it, writes the rubric
  hash and commit into the result and creates gold/heldout.lock. A second
  attempt is refused.
"""

import hashlib
import html
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import cost, gold, llm, stats
from .freeze import load_frozen
from .grade import FLAGS, LABELS, RUBRIC, grade_params, grading_estimate, parse
from .run import load_run_config
from .schema import ROOT

GRADES_DIR = ROOT / "runs" / "gold_grades"
EVAL_DIR = ROOT / "runs" / "gold_eval"
CONFIG = "configs/handwritten.yaml"   # any config with the grader block; all use Opus 5.5, low effort


def rubric_sha() -> str:
    return hashlib.sha256(RUBRIC.read_bytes()).hexdigest()


def _grades_path(sha: str):
    return GRADES_DIR / sha[:12] / "grades.jsonl"


def _items(split: str) -> list[dict]:
    return [it for it in gold.load_items() if it["split"] == split]


def _scenarios(items: list[dict]) -> dict:
    out = {}
    for name in {it["set"] for it in items}:
        out.update({(name, s["id"]): s for s in load_frozen(name)})
    return out


def _requests(items: list[dict], grader: dict):
    scenarios = _scenarios(items)
    for it in items:
        # Same output dict and cache labels as the original grading, so an
        # unchanged rubric hits the cache.
        output = {"task": it["task"], "text": it["text"], "key": it["output_key"]}
        params = grade_params(scenarios[(it["set"], it["scenario_id"])], output, grader)
        yield it, params, {"task": "grade", "output_key": it["output_key"]}


def estimate(split: str) -> tuple[int, float]:
    cfg = load_run_config(ROOT / CONFIG)
    reqs = list(_requests(_items(split), cfg["grader"]))
    missing = [(o, p) for o, p, labels in reqs if llm.get_cached(llm.cache_key(p, 0, labels)) is None]
    return len(missing), grading_estimate(missing, cfg["grader"], cfg)


def grade_items(split: str, assume_yes: bool = False, final: bool = False) -> dict:
    if split == "heldout" and not final:
        raise SystemExit("The held-out part is graded only by `cae gold agree --split heldout --final`.")
    cfg = load_run_config(ROOT / CONFIG)
    grader = cfg["grader"]
    reqs = list(_requests(_items(split), grader))
    n_missing, est = estimate(split)
    print(f"{len(reqs)} {split} items, {n_missing} not graded with this rubric yet (rubric {rubric_sha()[:12]})")
    if n_missing:
        cost.check_budget(est, cfg["budget_usd"], assume_yes)

    def one(req):
        it, params, labels = req
        record = llm.call(params, rep=0, labels=labels, run_id=f"gold-{split}")
        return {"gold_id": it["gold_id"], "output_key": it["output_key"], "rubric_sha256": rubric_sha(),
                "labels": parse(record), "from_cache": record["from_cache"]}

    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 4)) as pool:
        rows = list(pool.map(one, reqs))
    path = _grades_path(rubric_sha())
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_grades(path)
    existing.update({r["gold_id"]: r for r in rows})
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing.values()), encoding="utf-8")
    return existing


def _load_grades(path) -> dict:
    if not path.exists():
        return {}
    return {r["gold_id"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l)}


# --- Comparison ----------------------------------------------------------------

def compare(items: list[dict], author: dict, grades: dict) -> dict:
    """Per field: n, percent agreement, kappa, confusion; blames_user per task."""
    rows = [(it, author[it["gold_id"]]["labels"], grades[it["gold_id"]]["labels"]) for it in items]
    out = {}
    for field in [*LABELS, *FLAGS]:
        pairs = [(a[field], g[field]) for _, a, g in rows if field in a and field in g]
        if not pairs:
            continue
        a_l, g_l = [p[0] for p in pairs], [p[1] for p in pairs]
        out[field] = {
            "n": len(pairs),
            "agreement": sum(x == y for x, y in pairs) / len(pairs),
            "kappa": stats.cohens_kappa(a_l, g_l) if len(set(a_l) | set(g_l)) > 1 else float("nan"),
            "confusion": stats.confusion(a_l, g_l),
        }
    out["blames_user_by_task"] = {}
    for task in ("response", "summary"):
        sub = [(a["attribution"], g["attribution"]) for it, a, g in rows if it["task"] == task]
        if sub:
            s = stats.binary_scores([x for x, _ in sub], [y for _, y in sub], "blames_user")
            out["blames_user_by_task"][task] = {"n": len(sub), **s}
    return out


def disagreements(items: list[dict], author: dict, grades: dict) -> list[dict]:
    out = []
    for it in items:
        a, g = author[it["gold_id"]], grades[it["gold_id"]]["labels"]
        diff = [f for f in [*LABELS, *FLAGS] if f in g and a["labels"].get(f) != g[f]]
        if diff:
            out.append({"item": it, "fields": diff, "author": a["labels"], "grader": g, "note": a.get("note", "")})
    return out


def _rel(path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _fmt(x) -> str:
    return "–" if x != x else f"{x:.2f}"   # NaN check without math import


def print_summary(result: dict) -> None:
    for field, r in result.items():
        if field in ("blames_user_by_task", "per_value"):
            continue
        print(f"\n{field}: n={r['n']}, agreement {r['agreement'] * 100:.0f} %, kappa {_fmt(r['kappa'])}")
        print(f"  confusion (author -> grader): {r['confusion']}")
    print("\nblames_user by task (author = truth):")
    for task, s in result["blames_user_by_task"].items():
        print(f"  {task:8s} n={s['n']}: precision {_fmt(s['precision'])}, recall {_fmt(s['recall'])}, "
              f"FPR {_fmt(s['fpr'])} (tp {s['tp']}, fp {s['fp']}, fn {s['fn']})")


def write_disagreement_page(rows: list[dict], scenarios: dict, path) -> None:
    parts = []
    for d in rows:
        it = d["item"]
        s = scenarios[(it["set"], it["scenario_id"])]
        cells = "".join(f"<tr><td>{f}</td><td><b>{html.escape(str(d['author'].get(f)))}</b></td>"
                        f"<td>{html.escape(str(d['grader'].get(f)))}</td></tr>" for f in d["fields"])
        parts.append(f"""<section><h2>{it['gold_id']} · {it['task']}</h2>
<div class=out>{html.escape(it['text'])}</div>
<table><tr><th>Feld</th><th>Autor</th><th>Grader</th></tr>{cells}</table>
<p><b>Begründung des Graders (evidence):</b> {html.escape(d['grader'].get('evidence', ''))}</p>
<p><b>Deine Notiz:</b> {html.escape(d['note'] or '–')}</p>
<details><summary>Gespräch und Kontext</summary><pre>{html.escape(gold.render.transcript(s))}</pre>
<pre>{html.escape(gold.render.context_block(s['content']['user_context']))}</pre></details></section>""")
    css = ("body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;line-height:1.45}"
           ".out{background:#fff8e6;border:2px solid #c47f00;padding:10px;white-space:pre-wrap}"
           "td,th{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap}"
           "section{border-bottom:2px solid #ccc;padding-bottom:12px}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<!doctype html><meta charset=utf-8><title>Abweichungen</title><style>{css}</style>"
                    f"<h1>Abweichungen ({len(rows)} Items)</h1>{''.join(parts)}", encoding="utf-8")


def _labeled(items: list[dict]) -> dict:
    author = gold.author_labels()
    missing = [it["gold_id"] for it in items if it["gold_id"] not in author]
    if missing:
        raise SystemExit(f"{len(missing)} items not labeled yet: {', '.join(missing[:10])} ...")
    return author


def agree(split: str = "dev", assume_yes: bool = False) -> dict:
    if split != "dev":
        raise SystemExit("Only the development part can be compared repeatedly. "
                         "The held-out part: `cae gold agree --split heldout --final` (once).")
    items = _items("dev")
    author = _labeled(items)
    grades = grade_items("dev", assume_yes)
    result = compare(items, author, grades)
    print_summary(result)
    out = EVAL_DIR / f"dev_{rubric_sha()[:12]}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "agreement.json").write_text(json.dumps({"split": "dev", "rubric_sha256": rubric_sha(),
                                                    "result": result}, indent=2, default=str), encoding="utf-8")
    write_disagreement_page(disagreements(items, author, grades), _scenarios(items), out / "disagreements.html")
    print(f"\nAbweichungen: {_rel(out / 'disagreements.html')}")
    return result


# --- Held-out, once --------------------------------------------------------------

def _rubric_commit() -> str:
    rel = str(RUBRIC.relative_to(ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode != 0 or dirty.stdout.strip():
        raise SystemExit("Commit the rubric first: the held-out result must point to a committed rubric.")
    return subprocess.run(["git", "log", "-1", "--format=%H", "--", rel], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def agree_final(assume_yes: bool = False) -> dict:
    if gold.LOCK.exists():
        raise SystemExit(f"Held-out part was already evaluated ({gold.LOCK.read_text().strip()}). It is used once only.")
    commit = _rubric_commit()
    items = _items("heldout")
    author = _labeled(items)
    grades = grade_items("heldout", assume_yes, final=True)
    result = compare(items, author, grades)
    # Precision / recall / FPR per value, as the report needs them.
    result["per_value"] = gold.compare([(author[it["gold_id"]]["labels"], grades[it["gold_id"]]["labels"])
                                        for it in items])
    now = datetime.now(timezone.utc).isoformat()
    record = {"split": "heldout", "n": len(items), "rubric_sha256": rubric_sha(), "rubric_commit": commit,
              "evaluated_at": now, "result": result}
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "heldout_final.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    gold.LOCK.write_text(f"evaluated {now} rubric {rubric_sha()} commit {commit}\n", encoding="utf-8")
    print_summary(result)
    write_disagreement_page(disagreements(items, author, grades), _scenarios(items), EVAL_DIR / "heldout_disagreements.html")
    print(f"\nwritten to {_rel(EVAL_DIR / 'heldout_final.json')}; lock {_rel(gold.LOCK)}")
    return result
