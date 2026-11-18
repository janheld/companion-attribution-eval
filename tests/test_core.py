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


def _new_set_cfg(cfg):
    """A future set of main-set size under the current name rules (not v1)."""
    cfg["sets"]["future"] = {**cfg["sets"]["main"], "name_rules": None, "extra_side_names": {}}
    return cfg


def test_names_unique_and_side_names_capped():
    from collections import Counter
    from cae.people import look_alike
    cfg = _new_set_cfg(generate.load_config())
    specs = generate.make_specs("future", cfg)
    assert len({s["first_name"] for s in specs}) == len(specs)
    assert len({s["last_name"] for s in specs}) == len(specs)
    users = {s["first_name"] for s in specs} | {s["last_name"] for s in specs}
    side = Counter(n for s in specs for n in s["side_older"] + s["side_younger"] + s["side_surnames"])
    assert not set(side) & users
    assert max(side.values()) <= cfg["people"]["side_name_cap"]
    for s in specs:
        given = [s["first_name"]] + s["side_older"] + s["side_younger"]
        assert not any(look_alike(a, b) for i, a in enumerate(given) for b in given[i + 1:]), given


def test_v1_sets_keep_their_name_rules():
    from collections import Counter
    specs = generate.make_specs("main", generate.load_config())
    side = Counter(n for s in specs for n in s["side_older"] + s["side_younger"] + s["side_surnames"])
    assert max(side.values()) <= 3


def test_household_fits_relatives():
    cfg = _new_set_cfg(generate.load_config())
    for s in generate.make_specs("future", cfg):
        if s["household"] == "lebt allein, nie verheiratet":
            assert not any(w in s["relatives"] for w in ("Sohn", "Tochter", "Enkelin", "Söhne"))


def test_recovery_correction_styles_and_incoherence_forms():
    from collections import Counter
    specs = generate.make_specs("main", generate.load_config())
    rec = [s for s in specs if s["condition"] == "recovery"]
    assert all(s["correction_style"] for s in rec)
    assert {s["correction_style"] for s in rec if s["recovery_difficulty"] == "hard"} >= {"brief", "implicit"}
    assert not any(s["correction_style"] == "implicit" for s in rec if s["recovery_difficulty"] != "hard")
    forms = Counter(s["incoherence_form"] for s in specs if s["condition"] == "incoherent_user")
    assert max(forms.values()) <= 3


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


def test_context_format_is_unified():
    assert render.phase_label(14) == "Kennenlernen"
    assert render.phase_label(15) == "Vertraut werden"
    assert render.phase_label(162) == "Vertraut"
    assert render.session_date("Dienstag, vor 2 Tagen", "Donnerstag, 09:40") == "Dienstag, vor 2 Tagen"
    assert render.session_date("vor 2 Tagen", "Donnerstag, 09:40") == "Dienstag, vor 2 Tagen"
    assert render.session_date("Montag", "Donnerstag, 09:40") == "Montag, vor 3 Tagen"
    assert render.session_date("gestern", "Donnerstag, 09:40") == "Mittwoch, vor 1 Tag"


def test_recovery_misreading_must_match_spec():
    s = make_scenario()
    s["condition"] = "recovery"
    s["annotation"]["disturbance_position"] = "history"
    s["annotation"]["disturbances"] = [{"turn_index": 4, "span": "Satz 4", "type": "tv_film"}]
    s["spec"] = {"misreading": "Du klingst heute ein bisschen durcheinander. Bist du vielleicht müde?"}
    assert any("scripted misreading" in p for p in schema.validate(s))


def test_stt_error_words_are_not_people():
    from cae import people
    s = make_scenario("stt_errors_001")
    s["condition"] = "stt_errors"
    s["content"]["history"][2]["text"] = "Ich hab Emma gesagt"
    s["annotation"]["disturbances"] = [{"turn_index": 2, "span": "Emma", "type": "stt_phonetic"}]
    assert not any("Emma" in p for p in people.set_problems([s], {}, generate.load_config()))


def test_occasions_fit_time_of_day_and_are_capped():
    from collections import Counter
    cfg = generate.load_config()
    specs = generate.make_specs("main", cfg)
    assert all(s["time_of_day"] in cfg["occasions"][s["occasion"]] for s in specs)
    assert max(Counter(s["occasion"] for s in specs).values()) <= len(specs) * cfg["occasion_max_share"]


def test_near_identical_openings_are_flagged():
    from cae import checks
    a, b, c = make_scenario("a"), make_scenario("b"), make_scenario("c")
    a["content"]["history"][0]["text"] = "Na, Mira, bist no munter? I kann net schlafen."
    b["content"]["history"][0]["text"] = "Na, Mira, bist noch munter? I kann eh net schlafen."
    c["content"]["history"][0]["text"] = "Stell dir vor, die Post hat heute schon wieder nichts gebracht."
    assert checks.opening_problems([a, b, c]) == ["near-identical openings: a / b"]


def test_time_check_finds_past_weekday_in_old_summary():
    from cae import checks
    s = make_scenario()
    ctx = s["content"]["user_context"]
    ctx["time_of_day"] = "Montag, 12:00"
    s["content"]["history"][0]["timestamp"] = "12:00"
    ctx["recent_sessions"] = [{"date": "Mittwoch, vor 5 Tagen", "summary": "Ausflug am Donnerstag geplant.", "notes": []}]
    s["content"]["history"][2]["text"] = "Am Donnerstag ist der Ausflug."
    assert any("am Donnerstag" in p for p in checks.time_problems(s))
    ctx["recent_sessions"][0]["summary"] = "Ausflug am Donnerstag nächster Woche geplant."
    assert not any("am Donnerstag" in p for p in checks.time_problems(s))


def test_time_check_finds_wrong_summary_weekday():
    from cae import checks
    s = make_scenario()
    s["content"]["user_context"]["time_of_day"] = "Montag, 09:40"
    s["content"]["user_context"]["recent_sessions"] = [{"date": "Freitag, vor 2 Tagen", "summary": "x", "notes": []}]
    assert any("does not fit today" in p for p in checks.time_problems(s))


def test_paired_bootstrap_keeps_pairs():
    from cae import stats
    a = [{"scenario_id": f"s{i}", "v": 1 if i < 5 else 0} for i in range(10)]
    b = [{"scenario_id": f"s{i}", "v": 1 if i < 5 else 0} for i in range(10)]
    point, lo, hi = stats.cluster_bootstrap_paired(a, b, lambda r: r["v"])
    assert point == lo == hi == 0.0   # identical pairs: every resample gives zero difference
