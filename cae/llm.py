"""Model calls with a disk cache.

Every response is stored under cache/<key>.json. The key is a hash over the full
request plus a repetition index, so
- the same request with a different repetition index is a new call
  (otherwise repetitions would just return the first answer),
- any change to prompt text, scenario text, model or settings is a new call,
- re-running anything already computed costs nothing.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import cost
from .schema import ROOT, canonical_json

CACHE_DIR = ROOT / "cache"

# How "thinking: off" is expressed differs per model. Methodological note:
# Sonnet 5.5 cannot fully disable thinking; `between_tools` is its closest
# no-thinking mode (without tools it means no thinking). Opus 5.5 cannot turn
# thinking off at all, so it is only used with adaptive thinking (as grader and
# generator).
THINKING_OFF = {
    "claude-haiku-4-5": None,  # no thinking field = no thinking
    "claude-haiku-5-5": {"type": "disabled"},
    "claude-sonnet-5-5": {"type": "between_tools"},
}
NO_ADAPTIVE = {"claude-haiku-4-5"}  # only supports a fixed thinking budget


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines from .env into the environment, never overriding."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        load_dotenv()
        # max_retries covers 429/5xx with backoff inside the SDK.
        _client = anthropic.Anthropic(max_retries=5)
    return _client


def build_params(model: str, settings: dict, system, messages, output_format=None) -> dict:
    """Turn a config-level settings dict into API request parameters."""
    params = {"model": model, "max_tokens": settings.get("max_tokens", 1024),
              "system": system, "messages": messages}
    thinking = settings.get("thinking", "off")
    if thinking == "off":
        if model not in THINKING_OFF:
            raise ValueError(f"{model}: thinking cannot be turned off")
        if THINKING_OFF[model] is not None:
            params["thinking"] = THINKING_OFF[model]
    elif thinking == "adaptive":
        if model in NO_ADAPTIVE:
            raise ValueError(f"{model}: adaptive thinking not supported")
        params["thinking"] = {"type": "adaptive"}
    else:
        raise ValueError(f"unknown thinking setting {thinking!r}")
    output_config = {}
    if settings.get("effort"):
        output_config["effort"] = settings["effort"]
    if output_format:
        output_config["format"] = output_format
    if output_config:
        params["output_config"] = output_config
    # No temperature/top_p: the current API version rejects them. Repetitions
    # vary through the default sampling.
    return params


def cache_key(params: dict, rep: int = 0, labels: dict | None = None) -> str:
    payload = {"params": params, "rep": rep, "labels": labels or {}}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def cache_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / f"{key}.json"


def get_cached(key: str) -> dict | None:
    path = cache_path(key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def put_cached(key: str, record: dict) -> None:
    path = cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


def message_record(message, mode: str) -> dict:
    """The parts of an API response we keep, as plain JSON."""
    usage = message.usage
    usage_d = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    text = "".join(b.text for b in message.content if b.type == "text")
    return {
        "id": message.id,
        "model": message.model,
        "stop_reason": message.stop_reason,
        "text": text,
        "chars": len(text),
        "usage": usage_d,
        "cost_usd": cost.usage_cost(message.model, usage_d, batch=(mode == "batch")),
        "mode": mode,
    }


def call(params: dict, rep: int = 0, labels: dict | None = None, run_id: str = "adhoc") -> dict:
    """Direct streaming call with cache. Records time to first text token."""
    key = cache_key(params, rep, labels)
    cached = get_cached(key)
    if cached is not None:
        return cached | {"from_cache": True}

    start = time.perf_counter()
    first_text = None
    with client().messages.stream(**params) as stream:
        for event in stream:
            if (first_text is None and event.type == "content_block_delta"
                    and event.delta.type == "text_delta"):
                first_text = time.perf_counter()
        message = stream.get_final_message()
    end = time.perf_counter()

    record = message_record(message, mode="direct")
    record["latency"] = {
        "ttft_s": round(first_text - start, 3) if first_text else None,
        "total_s": round(end - start, 3),
    }
    record.update(key=key, rep=rep, labels=labels or {},
                  created_at=datetime.now(timezone.utc).isoformat())
    put_cached(key, record)
    cost.log_spend(run_id, record)
    return record | {"from_cache": False}


# --- Batch API ----------------------------------------------------------------
# Used for grading the full run (half price, no latency measurement). Batches
# are submitted once and their ids recorded in runs/<run_id>/batches.json, so a
# later invocation collects the results instead of submitting again. Results go
# into the same response cache as direct calls.

BATCH_CHUNK = 2000   # requests per batch; well below the 100,000 / 256 MB limits


def batch_request(key: str, params: dict) -> dict:
    # The cache key (64 hex characters) is a valid custom_id and maps results back.
    return {"custom_id": key, "params": params}


def _batch_log(folder: Path) -> list[dict]:
    path = folder / "batches.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save_batch_log(folder: Path, log: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "batches.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def batch_submit(requests: list[tuple[str, dict]], folder: Path) -> int:
    """Submit requests that are neither cached nor already in a submitted batch."""
    log = _batch_log(folder)
    in_flight = {k for b in log if not b.get("collected") for k in b["keys"]}
    todo = [(k, p) for k, p in requests if get_cached(k) is None and k not in in_flight]
    for i in range(0, len(todo), BATCH_CHUNK):
        chunk = todo[i:i + BATCH_CHUNK]
        batch = client().messages.batches.create(requests=[batch_request(k, p) for k, p in chunk])
        log.append({"id": batch.id, "keys": [k for k, _ in chunk],
                    "submitted_at": datetime.now(timezone.utc).isoformat(), "collected": False})
        _save_batch_log(folder, log)
        print(f"  submitted batch {batch.id} with {len(chunk)} requests")
    return len(todo)


def batch_collect(folder: Path, run_id: str) -> bool:
    """Collect ended batches into the cache. True when nothing is pending."""
    log = _batch_log(folder)
    pending = False
    for entry in log:
        if entry.get("collected"):
            continue
        batch = client().messages.batches.retrieve(entry["id"])
        if batch.processing_status != "ended":
            print(f"  batch {entry['id']}: {batch.processing_status}, {batch.request_counts.processing} processing")
            pending = True
            continue
        errors = 0
        for result in client().messages.batches.results(entry["id"]):
            if result.result.type != "succeeded":
                errors += 1      # left uncached: the next submit sends it again
                continue
            record = message_record(result.result.message, mode="batch")
            record.update(key=result.custom_id, rep=0, labels={}, latency=None,
                          created_at=datetime.now(timezone.utc).isoformat())
            put_cached(result.custom_id, record)
            cost.log_spend(run_id, record)
        entry.update(collected=True, errors=errors)
        _save_batch_log(folder, log)
        print(f"  batch {entry['id']}: collected, {errors} not succeeded")
    return not pending
