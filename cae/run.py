"""Run the models under test on a frozen scenario set.

One job = one model call: (model, task, prompt variant, scenario, repetition).
Everything that varies between runs comes from the run config. Every response
is cached (cae/llm.py), so re-running, adding repetitions or adding a model
only pays for what is missing.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from . import cost, llm, prompts, render
from .freeze import load_frozen
from .schema import ROOT

RUNS_DIR = ROOT / "runs"


def load_run_config(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _job_params(job: dict, cfg: dict) -> dict:
    scenario, model = job["scenario"], job["model"]
    if job["task"] == "response":
        system, messages = render.response_request(scenario, prompts.system_prompt(job["variant"]))
    else:
        system, messages = render.summary_request(scenario, prompts.summarizer_prompt(cfg["summarizer"]))
    return llm.build_params(model["model"], model["settings"], system, messages)


def jobs(cfg: dict, scenarios: list[dict]) -> list[dict]:
    """All calls of a run, repetition-major: every scenario's first repetition
    runs before any second one, so later repetitions find the prompt cache warm."""
    out = []
    for rep in range(cfg["repetitions"]):
        for model in cfg["models"]:
            for s in scenarios:
                if "response" in cfg["tasks"]:
                    out += [{"model": model, "task": "response", "variant": v, "scenario": s, "rep": rep}
                            for v in cfg["prompt_variants"]]
                if "summary" in cfg["tasks"]:
                    out.append({"model": model, "task": "summary", "variant": f"summarizer_{cfg['summarizer']}",
                                "scenario": s, "rep": rep})
    for job in out:
        job["params"] = _job_params(job, cfg)
        job["labels"] = {"task": job["task"], "variant": job["variant"], "scenario_id": job["scenario"]["id"],
                         "content_hash": job["scenario"]["content_hash"]}
    return out


def _prompt_chars(params: dict) -> int:
    text = "".join(b["text"] for b in params["system"])
    for m in params["messages"]:
        c = m["content"]
        text += c if isinstance(c, str) else "".join(b["text"] for b in c)
    return len(text)


def estimate_calls(calls: list[tuple[str, dict, int]], out_tokens: dict, chars_per_token: float) -> float:
    """Offline estimate, no API call. calls: (model, params, rep, task).
    The whole prompt is cached at the final breakpoint if it is long enough for
    the model; the first repetition writes the cache, later ones read it."""
    total = 0.0
    for model, params, rep, task in calls:
        tokens = _prompt_chars(params) / chars_per_token
        p = cost.price_for(model)
        cacheable = tokens >= p.get("min_cache_tokens", 1024)
        usage = {"output_tokens": out_tokens[task]}
        if cacheable and rep == 0:
            usage["cache_creation_input_tokens"] = tokens
        elif cacheable:
            usage["cache_read_input_tokens"] = tokens
        else:
            usage["input_tokens"] = tokens
        total += cost.usage_cost(model, usage)
    return total


def estimate(cfg: dict, job_list: list[dict]) -> float:
    est = cfg["estimate"]
    out = {"response": est["response_output_tokens"], "summary": est["summary_output_tokens"]}
    missing = [j for j in job_list if llm.get_cached(llm.cache_key(j["params"], j["rep"], j["labels"])) is None]
    return estimate_calls([(j["model"]["model"], j["params"], j["rep"], j["task"]) for j in missing],
                          out, est["chars_per_token"])


def _execute(job: dict, run_id: str) -> dict:
    record = llm.call(job["params"], rep=job["rep"], labels=job["labels"], run_id=run_id)
    s = job["scenario"]
    return {
        "key": record["key"], "run_id": run_id, "model_name": job["model"]["name"],
        "model": job["model"]["model"], "settings": job["model"]["settings"],
        "task": job["task"], "variant": job["variant"], "rep": job["rep"],
        "scenario_id": s["id"], "set": s["set"], "condition": s["condition"], "kind": s["kind"],
        "content_hash": s["content_hash"],
        "disturbance_position": s["annotation"]["disturbance_position"],
        "text": record["text"], "chars": record["chars"], "stop_reason": record["stop_reason"],
        "usage": record["usage"], "cost_usd": record["cost_usd"], "latency": record.get("latency"),
        "from_cache": record["from_cache"],
    }


def run(config_path: str, assume_yes: bool = False) -> None:
    cfg = load_run_config(config_path)
    if cfg.get("mode", "direct") != "direct":
        raise SystemExit("Only direct calls are implemented so far (batch comes with the full run).")
    scenarios = load_frozen(cfg["set"])
    job_list = jobs(cfg, scenarios)
    est = estimate(cfg, job_list)
    print(f"{len(job_list)} calls in run '{cfg['run_id']}' "
          f"({sum(1 for j in job_list if j['task'] == 'response')} replies, "
          f"{sum(1 for j in job_list if j['task'] == 'summary')} summaries)")
    cost.check_budget(est, cfg["budget_usd"], assume_yes)
    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 4)) as pool:
        rows = list(pool.map(lambda j: _execute(j, cfg["run_id"]), job_list))
    write_outputs(cfg["run_id"], rows)


def write_outputs(run_id: str, rows: list[dict]) -> None:
    folder = RUNS_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "outputs.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    paid = [r for r in rows if not r["from_cache"]]
    usage = {"calls": len(rows), "paid_calls": len(paid),
             "cost_usd_this_invocation": round(sum(r["cost_usd"] for r in paid), 4),
             "cost_usd_all_outputs": round(sum(r["cost_usd"] for r in rows), 4),
             "refusals": sum(r["stop_reason"] == "refusal" for r in rows),
             "max_tokens_hits": sum(r["stop_reason"] == "max_tokens" for r in rows)}
    (folder / "usage.json").write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(usage, indent=2))


def load_outputs(run_id: str) -> list[dict]:
    path = RUNS_DIR / run_id / "outputs.jsonl"
    if not path.exists():
        raise SystemExit(f"No outputs for run '{run_id}'. Run it first.")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
