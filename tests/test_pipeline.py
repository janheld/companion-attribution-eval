"""Tests for run, grade, stats and gold (no API calls)."""

import json
import math

import pytest

from cae import gold, grade, render, run, stats

from test_core import make_scenario


# --- stats against hand calculations -----------------------------------------

def test_wilson_matches_hand_calculation():
    # 8 of 40: p = 0.2; Wilson 95 % interval (0.105, 0.348), computed by hand.
    p, lo, hi = stats.wilson(8, 40)
    assert p == 0.2
    assert abs(lo - 0.1049) < 1e-3 and abs(hi - 0.3482) < 1e-3
    assert stats.wilson(0, 10)[1] == 0.0


def test_kappa_matches_hand_calculation():
    # 10 items, observed agreement 0.8; marginals a: 6 yes / 4 no, b: 6 / 4;
    # p_e = 0.6*0.6 + 0.4*0.4 = 0.52; kappa = (0.8 - 0.52) / 0.48 = 0.5833.
    a = ["y"] * 6 + ["n"] * 4
    b = ["y", "y", "y", "y", "y", "n", "n", "n", "n", "y"]
    assert abs(stats.cohens_kappa(a, b) - 0.28 / 0.48) < 1e-9
    assert stats.cohens_kappa(a, a) == 1.0


def test_binary_scores_and_confusion():
    gold_l = ["b", "b", "i", "i", "i"]
    pred_l = ["b", "i", "b", "i", "i"]
    s = stats.binary_scores(gold_l, pred_l, "b")
    assert (s["tp"], s["fp"], s["fn"], s["tn"]) == (1, 1, 1, 2)
    assert s["precision"] == 0.5 and s["recall"] == 0.5 and abs(s["fpr"] - 1 / 3) < 1e-9
    assert stats.confusion(gold_l, pred_l) == {"b": {"b": 1, "i": 1}, "i": {"b": 1, "i": 2}}


def test_cluster_bootstrap_resamples_scenarios():
    # One scenario with three identical repetitions behaves like one data point.
    rows = [{"scenario_id": "a", "v": 1}] * 3 + [{"scenario_id": "b", "v": 0}] * 3
    point, lo, hi = stats.cluster_bootstrap(rows, lambda r: r["v"])
    assert point == 0.5 and lo == 0.0 and hi == 1.0
    d, dlo, dhi = stats.cluster_bootstrap_diff(rows, rows, lambda r: r["v"])
    assert d == 0.0 and dlo <= 0 <= dhi


# --- run jobs ----------------------------------------------------------------

CFG = {"run_id": "t", "set": "testset", "repetitions": 3, "tasks": ["response", "summary"],
       "prompt_variants": ["neutral", "companion_no_flag", "companion_may_flag"], "summarizer": "standard",
       "models": [{"name": "h45", "model": "claude-haiku-4-5", "settings": {"thinking": "off", "max_tokens": 512}}],
       "grader": {"name": "opus", "model": "claude-opus-5-5", "settings": {"thinking": "adaptive", "effort": "low"}},
       "estimate": {"chars_per_token": 3.0, "response_output_tokens": 200, "summary_output_tokens": 300,
                    "grade_output_tokens": 500}}


def _scenarios(n=2):
    out = []
    for i in range(n):
        s = make_scenario(f"tv_bleed_00{i + 1}")
        s["content_hash"] = f"h{i}"
        out.append(s)
    return out


def test_jobs_cover_variants_tasks_and_repetitions():
    job_list = run.jobs(CFG, _scenarios(2))
    # per scenario and repetition: 3 replies + 1 summary (summary is independent of the variant)
    assert len(job_list) == 2 * 3 * (3 + 1)
    assert [j["rep"] for j in job_list] == sorted(j["rep"] for j in job_list)  # repetition-major
    keys = {run.llm.cache_key(j["params"], j["rep"], j["labels"]) for j in job_list}
    assert len(keys) == len(job_list)


def test_estimate_is_offline_and_positive(monkeypatch):
    monkeypatch.setattr(run.llm, "client", lambda: pytest.fail("no API call allowed"))
    job_list = run.jobs(CFG, _scenarios(1))
    assert run.estimate(CFG, job_list) > 0
    assert grade.estimate_before_run(CFG, job_list) > 0


# --- grader blindness ----------------------------------------------------------

def test_grader_input_hides_condition_annotation_and_model():
    s = make_scenario()
    s["annotation"]["rationale"] = "SECRET_RATIONALE"
    output = {"task": "response", "text": "Hallo Erna.", "key": "k", "model": "claude-haiku-4-5",
              "variant": "companion_no_flag", "condition": "tv_bleed"}
    text = grade.grader_input(s, output)
    for leak in ("tv_bleed", "SECRET_RATIONALE", "disturbance", "haiku", "companion_no_flag"):
        assert leak not in text
    params = grade.grade_params(s, output, CFG["grader"])
    schema = params["output_config"]["format"]["schema"]
    assert "not_applicable" in schema["properties"]["recovery"]["enum"]
    assert params["system"][0]["cache_control"] == render.CACHE


def test_grader_parse_keeps_errors():
    assert "error" in grade.parse({"stop_reason": "max_tokens", "text": ""})
    assert "error" in grade.parse({"stop_reason": "end_turn", "text": "kein json"})
    assert grade.parse({"stop_reason": "end_turn", "text": '{"attribution": "ignores"}'}) == {"attribution": "ignores"}


# --- gold set ------------------------------------------------------------------

def _outputs(n=60):
    outs, grades = [], {}
    for i in range(n):
        o = {"key": f"k{i}", "run_id": "t", "set": "calibration", "scenario_id": f"tv_bleed_{i % 12:03d}",
             "task": "response" if i % 3 else "summary", "condition": "tv_bleed", "text": "Schön."}
        outs.append(o)
        att = "blames_user" if i % 10 == 0 else "ignores"
        grades[o["key"]] = {"labels": {"attribution": att, "escalation": "none", "contact": "not_applicable",
                                       "recovery": "not_applicable", "content_misattributed": False,
                                       "claims_unavailable_action": False}}
    return outs, grades


def test_gold_sample_keeps_rare_labels_and_splits_deterministically():
    outs, grades = _outputs()
    items = gold.sample(outs, grades, target=30)
    assert len(items) == 30
    assert sum(it["stratum"] == "attribution:blames_user" for it in items) == 6  # all rare cases kept
    gold.split(items)
    first = {it["key"]: it["split"] for it in items}
    gold.split(items)
    assert first == {it["key"]: it["split"] for it in items}
    held = [it for it in items if it["stratum"] == "attribution:blames_user" and it["split"] == "heldout"]
    assert len(held) == round(6 * gold.HELDOUT_SHARE)


def test_compare_reports_per_label():
    a = [{"attribution": "blames_user", "content_misattributed": True},
         {"attribution": "ignores", "content_misattributed": False}]
    g = [{"attribution": "blames_user", "content_misattributed": False},
         {"attribution": "ignores", "content_misattributed": False}]
    r = gold.compare(list(zip(a, g)))
    assert r["attribution"]["kappa"] == 1.0
    assert r["content_misattributed"]["per_value"]["True"]["recall"] == 0.0


def test_heldout_is_evaluated_once(tmp_path, monkeypatch):
    monkeypatch.setattr(gold, "LOCK", tmp_path / "heldout.lock")
    (tmp_path / "heldout.lock").write_text("evaluated before\n")
    monkeypatch.setattr(gold, "load_run_config", lambda p: CFG)
    with pytest.raises(SystemExit, match="used once"):
        gold.evaluate("x", "heldout")


def test_label_page_never_shows_grader_labels(tmp_path, monkeypatch):
    s = make_scenario("tv_bleed_001", "calibration")
    item = {"gold_id": "g001", "output_key": "k", "run_id": "t", "set": "calibration",
            "scenario_id": "tv_bleed_001", "task": "response", "text": "Hallo.", "stratum": "attribution:blames_user",
            "split": "dev"}
    monkeypatch.setattr(gold, "load_items", lambda: [item])
    monkeypatch.setattr(gold, "AUTHOR_LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(gold, "_scenarios", lambda: {("calibration", "tv_bleed_001"): s})
    page = gold.item_page("g001").decode("utf-8").split("</style>", 1)[1]
    for leak in ("stratum", "attribution:blames_user", "tv_bleed", "dev", "heldout"):
        assert leak not in page.replace("tv_bleed_001", "")
    gold.save_label("g001", {"attribution": ["flags_channel"], "content_misattributed": ["1"]})
    saved = gold.author_labels()["g001"]["labels"]
    assert saved["attribution"] == "flags_channel" and saved["content_misattributed"] is True
    assert saved["escalation"] == "none"
