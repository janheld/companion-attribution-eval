import copy
import difflib

import pytest

from cae import freeze, generate, llm, prompts, render, schema


def make_scenario(sid="tv_bleed_001", set_name="testset"):
    history = []
    for i in range(6):
        if i % 2 == 0:
            history.append({"role": "user", "timestamp": f"09:{40 + i}", "text": f"Satz {i}"})
        else:
            history.append({"role": "assistant", "timestamp": "", "text": f"Antwort {i}"})
    s = {
        "id": sid, "set": set_name, "kind": "attribution", "condition": "tv_bleed", "version": 1,
        "status": "draft", "review": {"comment": "", "reviewed_at": None}, "content_hash": "",
        "content": {
            "user_context": {
                "name": "Erna Beispiel", "address_form": "du", "dialect": "none",
                "relationship_phase": {"phase": "Vertraut", "days": 120},
                "time_of_day": "Dienstag, 09:40", "last_conversation_note": "",
                "caregiver_notes": [], "knowledge_blocks": [{"topic": "Familie", "text": "Ein Sohn."}],
                "recent_sessions": [{"date": "Montag", "summary": "Sprach über den Garten.", "notes": ["Garten"]}],
            },
            "history": history,
            "final_user_turn": {"timestamp": "09:47", "text": "Und auf der A1 drei Kilometer Stau."},
        },
        "annotation": {"disturbance_position": "final_turn",
                       "disturbances": [{"turn_index": 6, "span": "auf der A1 drei Kilometer Stau", "type": "traffic"}],
                       "contact_type": None, "rationale": "test"},
    }
    s["content_hash"] = schema.content_hash(s)
    return s


@pytest.fixture
def tmp_scenarios(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(freeze, "SCENARIO_DIR", tmp_path)
    monkeypatch.setattr(freeze, "FROZEN_DIR", tmp_path / "frozen")
    return tmp_path


def test_hash_ignores_review_fields():
    s = make_scenario()
    h = schema.content_hash(s)
    s["status"] = "approved"
    s["review"]["comment"] = "passt"
    assert schema.content_hash(s) == h


def test_edit_after_approval_resets_to_draft():
    s = make_scenario()
    s["status"] = "approved"
    assert not schema.sync_status(s)
    s["content"]["final_user_turn"]["text"] = "geändert"
    assert schema.sync_status(s)
    assert s["status"] == "draft"


def test_valid_scenario_has_no_problems():
    assert schema.validate(make_scenario()) == []


def test_validation_catches_disturbance_in_clean():
    s = make_scenario()
    s["condition"] = "clean"
    assert schema.validate(s)


def test_run_gate_refuses_unapproved_and_changed(tmp_scenarios):
    a, b = make_scenario("tv_bleed_001"), make_scenario("tv_bleed_002")
    a["status"] = b["status"] = "approved"
    schema.save(a); schema.save(b)
    freeze.freeze("testset")
    assert len(freeze.load_frozen("testset")) == 2

    b["content"]["final_user_turn"]["text"] = "anders"
    schema.save(b)  # edited after freezing: hash mismatch, falls back to draft
    with pytest.raises(SystemExit):
        freeze.load_frozen("testset")


def test_freeze_refuses_draft(tmp_scenarios):
    schema.save(make_scenario())
    with pytest.raises(SystemExit):
        freeze.freeze("testset")


def test_cache_key_differs_per_repetition():
    params = {"model": "m", "messages": []}
    assert llm.cache_key(params, 0) != llm.cache_key(params, 1)
    assert llm.cache_key(params, 0) == llm.cache_key(dict(params), 0)


def test_variants_differ_only_in_the_asr_rule():
    no_flag = prompts.system_prompt("companion_no_flag").splitlines()
    may_flag = prompts.system_prompt("companion_may_flag").splitlines()
    changed = [l for l in difflib.ndiff(no_flag, may_flag) if l[:1] in "+-"]
    rule_no = prompts._read("asr_rule_no_flag.de.md")
    rule_may = prompts._read("asr_rule_may_flag.de.md")
    assert changed == [f"- {rule_no}", f"+ {rule_may}"]


def test_thinking_settings_map_per_model():
    p = llm.build_params("claude-haiku-4-5", {"thinking": "off"}, "s", [])
    assert "thinking" not in p
    p = llm.build_params("claude-haiku-5-5", {"thinking": "off"}, "s", [])
    assert p["thinking"] == {"type": "disabled"}
    p = llm.build_params("claude-sonnet-5-5", {"thinking": "adaptive", "effort": "low"}, "s", [])
    assert p["thinking"] == {"type": "adaptive"} and p["output_config"]["effort"] == "low"
    with pytest.raises(ValueError):
        llm.build_params("claude-opus-5-5", {"thinking": "off"}, "s", [])


def test_annotation_never_rendered():
    s = make_scenario()
    s["annotation"]["rationale"] = "GEHEIM"
    system, messages = render.response_request(s, "prompt")
    assert "GEHEIM" not in str(system) + str(messages)
    assert messages[-1]["content"][0]["text"].startswith("[09:47]")


def test_spec_allocation_is_balanced():
    cfg = generate.load_config()
    specs = generate.make_specs("main", cfg)
    tv = [s for s in specs if s["condition"] == "tv_bleed"]
    assert len(tv) == 30
    assert sum(s["disturbance_position"] == "final_turn" for s in tv) == 15
    assert len({s["id"] for s in specs}) == len(specs)


def test_action_request_only_allowed_in_clean_and_contact():
    s = make_scenario()
    s["annotation"]["unavailable_action_request"] = True
    assert any("unavailable action" in p for p in schema.validate(s))


def test_action_request_must_match_spec():
    s = make_scenario()
    s["spec"] = {"action_request": "Wetter nachschauen"}
    s["annotation"]["unavailable_action_request"] = False
    assert any("does not match the spec" in p for p in schema.validate(s))


def test_action_requests_allocated_only_where_configured():
    specs = generate.make_specs("main", generate.load_config())
    with_request = {s["condition"] for s in specs if s["action_request"]}
    assert with_request == {"clean", "contact"}
    assert sum(1 for s in specs if s["condition"] == "clean" and s["action_request"]) in range(6, 10)


def test_names_unique_and_side_names_capped():
    from collections import Counter
    from cae.people import SIDE_CAP
    specs = generate.make_specs("main", generate.load_config())
    assert len({s["first_name"] for s in specs}) == len(specs)
    assert len({s["last_name"] for s in specs}) == len(specs)
    users = {s["first_name"] for s in specs} | {s["last_name"] for s in specs}
    side = Counter(n for s in specs for n in s["side_older"] + s["side_younger"] + s["side_surnames"])
    assert not set(side) & users
    assert max(side.values()) <= SIDE_CAP


def test_interest_share_capped():
    from collections import Counter
    cfg = generate.load_config()
    specs = generate.make_specs("main", cfg)
    counts = Counter(i for s in specs for i in s["interests"])
    assert max(counts.values()) <= len(specs) * cfg["people"]["interest_max_share"]


def test_calibration_keeps_fixed_and_kept_genders():
    cfg = generate.load_config()
    specs = {s["id"]: s for s in generate.make_specs("calibration", cfg)}
    assert specs["clean_001"]["first_name"] == "Hermine"
    for sid, gender in cfg["sets"]["calibration"]["keep_gender"].items():
        assert specs[sid]["gender"] == gender
