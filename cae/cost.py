"""Prices, spend ledger and budget checks.

The ledger (runs/ledger.jsonl) records the actual cost of every paid call, so
the total across all runs is always known. Cached calls are free and not logged.
"""

import json
from datetime import datetime, timezone

import yaml

from .schema import ROOT

PRICES_FILE = ROOT / "configs" / "prices.yaml"
LEDGER = ROOT / "runs" / "ledger.jsonl"

# The project's API budget is a 200 USD promotional credit. Above the warning
# line the user wants to be asked before anything else is spent.
TOTAL_BUDGET_USD = 200.0
WARN_AT_USD = 150.0


def prices() -> dict:
    return yaml.safe_load(PRICES_FILE.read_text(encoding="utf-8"))


def price_for(model: str) -> dict:
    table = prices()
    if model in table:
        return table[model]
    # Responses may report a dated model id; match on the configured prefix.
    for name, p in table.items():
        if isinstance(p, dict) and model.startswith(name):
            return p
    raise KeyError(f"no price for model {model!r} in {PRICES_FILE.name}")


def usage_cost(model: str, usage: dict, batch: bool = False) -> float:
    p = price_for(model)
    total = (usage.get("input_tokens", 0) * p["input"]
             + usage.get("output_tokens", 0) * p["output"]
             + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
             + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]) / 1e6
    if batch:
        total *= prices()["batch_discount"]
    return round(total, 6)


def estimate(model: str, input_tokens: float, output_tokens: float,
             cached_share: float = 0.0, batch: bool = False) -> float:
    """Rough cost for a number of tokens; cached_share of input is read from cache."""
    usage = {"input_tokens": input_tokens * (1 - cached_share),
             "cache_read_input_tokens": input_tokens * cached_share,
             "output_tokens": output_tokens}
    return usage_cost(model, usage, batch)


def log_spend(run_id: str, record: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "run": run_id,
             "model": record["model"], "mode": record["mode"],
             "cost_usd": record["cost_usd"], "usage": record["usage"]}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def total_spent() -> float:
    if not LEDGER.exists():
        return 0.0
    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    return round(sum(json.loads(l)["cost_usd"] for l in lines if l.strip()), 4)


def check_budget(estimate_usd: float, run_budget_usd: float, assume_yes: bool = False) -> None:
    """Print the estimate and stop if it breaks the run or project budget."""
    spent = total_spent()
    after = spent + estimate_usd
    print(f"Estimated cost of this step: ${estimate_usd:.2f}")
    print(f"Spent so far: ${spent:.2f}  ->  after this step: ${after:.2f} "
          f"(warn at ${WARN_AT_USD:.0f}, hard limit ${TOTAL_BUDGET_USD:.0f})")
    if estimate_usd > run_budget_usd:
        raise SystemExit(f"Abort: estimate exceeds this config's budget_usd (${run_budget_usd:.2f}).")
    if after > TOTAL_BUDGET_USD:
        raise SystemExit("Abort: this step would exceed the total project budget.")
    if after > WARN_AT_USD and not assume_yes:
        raise SystemExit("Stop: total would pass the 150 USD warning line. "
                         "Re-run with --yes after the user has agreed.")
    if not assume_yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            raise SystemExit("Cancelled.")
