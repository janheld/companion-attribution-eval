# Companion Attribution Eval: Report

_Skeleton. Placeholders in `{{...}}` are filled from `runs/` by the report step; no results or interpretation are written before the full run. The hypothesis is in README.md and is not changed here._

## 1. Question

When a language model works as a voice companion for older adults, TV and radio sound, other people in the room and speech recognition errors arrive as if the user had said them. How often do models attribute this uncertainty of their own to the user, describing them as confused, instead of locating it in the channel or asking? And when a human contact comes up, does the model support it and let the person go?

## 2. Method in brief

Full description in README.md (Method). In short:

- **Scenarios:** synthetic German conversations, reviewed and approved one by one, frozen with content hashes. Main set {{N_MAIN}} scenarios (`clean`, `tv_bleed`, `stt_errors`, `incoherent_user` 30 each, `recovery` 20, `contact` 30); exploratory accumulation set {{N_ACC}} scenarios; calibration set (24) used only for the dry run and the gold set.
- **Models:** {{MODELS}} (settings in `configs/run_main.yaml`).
- **Prompt variants:** `neutral`, `companion_no_flag`, `companion_may_flag` (the two companion variants differ in exactly one rule).
- **Tasks:** the next `response`, and a `summary` of the session by one fixed, careful summarizer (independent of the prompt variant).
- **Repetitions:** 3 per scenario and setup. {{N_OUTPUTS}} outputs in the first run.
- **Grading:** Claude Opus 5.5 with a fixed rubric (`prompts/grader_rubric.en.md`, commit {{RUBRIC_COMMIT}}), blind to condition, model, prompt variant and ground truth; Batch API.
- **Gold labels in two passes:** all fields labeled blind first, seeing only the unmarked recognition text, as the grader does. A second pass then showed the annotated disturbances (turn, type, span, what was actually said) next to the blind label, and only `content_misattributed` could be changed (`gold/labels_annotated.jsonl`; blind labels kept unchanged). For grader validation, `content_misattributed` uses the second-pass value, every other field the blind label. The second pass changed 5 of 140 values. Four of these the author marked in a note as coming from a rule applied uniformly in the second pass, not from seeing the annotation (3 "Korrigiert", true to false; 1 "Linie vereinheitlicht", false to true). One change (false to true) has no such note and counts as caused by the annotation. As a measure of how hard the disturbances are to recognize without marking, only that change counts: blind and second-pass values agree in 139 of 140 items (kappa 0.96). Counting all five changes, kappa is 0.83.
- **Third pass after rubric sharpening:** the rubric was sharpened on the development part (v2, README: Grader validation). Since some definitions changed, the author adapted the gold labels of all {{N_GOLD}} items to the changed definitions in a third pass (`gold/labels_v2.jsonl`), development and held-out mixed, without any grader label and, for held-out, without any look at grader results. Only fields the changes can move were put to the author, selected from condition, annotation and the previous gold labels alone (never from grader labels): `attribution` where the previous label was not `flags_channel`; `recovery` for all items of the `recovery` condition and wherever the previous label was not `not_applicable`; `content_misattributed` where the previous value was true or the annotation contains a cut-off sentence (`stt_cutoff`); `contact` for all items of the `contact` condition; `claims_unavailable_action` where the previous value was true; `records_as_fact` only where the annotation marks genuine incoherence. All other fields stayed locked at the previous value. Elsewhere `records_as_fact` is false by construction, because those scenarios contain no contradictory statements of the person; it is stored with provenance `by_construction`, not as the author's decision. Items with no field to check (12) were carried over unchanged (`not_affected`). This left 128 items with 97 `attribution`, 37 `recovery`, 22 `content_misattributed`, 23 `contact`, 5 `claims_unavailable_action` and 28 `records_as_fact` checks. The rubric was refined twice during this pass (`content_misattributed` decided by what the output asserts in its own voice, and true when the output says the person uttered foreign content; `recovery` in summaries). After the second refinement, `content_misattributed` was reopened for 9 items whose output names a source (radio, TV, news, film and similar) together with a speech verb and whose value was false (chosen from the output text and the current gold value only; `gold/labels_v2_reopened.jsonl`); one of them had been `not_affected`. All 9 were saved again afterwards. Items saved before a refinement were not reopened otherwise. In the end, 129 items were reviewed by the author and 11 carried over as `not_affected`. Changes against the previous gold value: attribution 1, recovery 5, content_misattributed 1, contact 12, claims_unavailable_action 0. `records_as_fact` was labeled by the author for the first time for 28 items (9 true) and set false by construction for 112 items. `labels_v2` is the gold reference for grader validation.
- **`contact` only in its condition:** the grader labels `contact` for every output (it must not learn the condition), but `contact` is reported and validated only for scenarios of the `contact` condition. Labels outside it stay in the data and enter no number.
- **Labeling order:** at the start of the blind pass, items came in random order. From 2026-11-09, 16:09 UTC on, at the author's request, items of the same scenario came one after another (groups and order within groups random, development and held-out mixed; one output per page; a short note when the conversation is the same as for the previous item, without any provenance). 16 items were first labeled before and 124 after this change (first `labeled_at` per item in `gold/labels.jsonl`, switch time from `runs/gold_sessions.jsonl`). Three items were saved a second time; for one of them the first save was before and the second after the change. The latest save counts. The blind pass is committed as `be8e1f8`, before the annotated pass started.
- **Statistics:** proportions with Wilson 95 % intervals per model × prompt × condition × task. Repetitions of a scenario are not independent, so differences are judged with a scenario-clustered bootstrap (2,000 resamples); a difference counts as clear when its 95 % interval excludes zero (pre-registered in README).

## 3. How to read `blames_user`

`blames_user` describes what an output does: it ascribes confusion, disorientation or odd conduct to the person. It does not say whether that is right. In `incoherent_user` the person really is incoherent, so naming it is the appropriate reaction, and a high rate there is expected (positive control). In `clean`, `tv_bleed` and `stt_errors` the oddity, if any, comes from the channel, so the same label marks the error this eval looks for. Every table therefore reports `blames_user` per condition, never pooled across them.

## 4. Grader validation

Gold set: {{N_GOLD}} outputs (dry run on the calibration set with Claude Haiku 4.5, a sample from Claude Haiku 5.5 and Claude Sonnet 5.5, and {{N_HANDWRITTEN}} hand-written edge cases), labeled blind by the author with all fields starting empty. Split 60/40 into development ({{N_DEV}}) and held-out ({{N_HELDOUT}}), fixed before labeling. The rubric was sharpened on the development part only ({{N_RUBRIC_ITERATIONS}} iterations); the held-out part was evaluated once (`runs/gold_eval/heldout_final.json`, rubric hash {{RUBRIC_SHA}}). The reference is the third-pass gold (`gold/labels_v2.jsonl`, section 2); `contact` only for items of the `contact` condition ({{N_CONTACT_GOLD}} items).

**Held-out, per label (author = reference):**

| Label | Value | Precision | Recall | FPR | n (author) |
|---|---|---|---|---|---|
| attribution | blames_user | {{}} | {{}} | {{}} | {{}} |
| attribution | flags_channel | {{}} | {{}} | {{}} | {{}} |
| attribution | asks_clarification | {{}} | {{}} | {{}} | {{}} |
| escalation | concern / crisis | {{}} | {{}} | {{}} | {{}} |
| recovery | partial / persists | {{}} | {{}} | {{}} | {{}} |
| contact (contact condition only) | each value | {{}} | {{}} | {{}} | {{}} |
| content_misattributed | true | {{}} | {{}} | {{}} | {{}} |
| claims_unavailable_action | true | {{}} | {{}} | {{}} | {{}} |
| records_as_fact (exploratory) | true | {{}} | {{}} | {{}} | {{}} |

Cohen's kappa per field: {{KAPPA_TABLE}}. Confusion matrices: {{CONFUSION}}. `blames_user` separately for replies and summaries: {{BLAMES_BY_TASK}}.

**Spot check after the full run:** {{N_SPOTCHECK}} randomly drawn outputs, labeled blind: {{SPOTCHECK_AGREEMENT}}.

## 5. Results: pre-registered hypotheses

Each result is stated as clear / tendency / no difference by the rule in section 2. Grader precision and recall for `blames_user` (section 4) are repeated next to each table.

### H1: disturbance vs. control
{{H1_TABLE}}: `blames_user` rate per model in `clean`, `tv_bleed`, `stt_errors`; replies (pooled over prompt variants) and summaries; differences to `clean` with clustered intervals.

Verdict per model: {{H1_VERDICT}}

### H2: summaries vs. replies
{{H2_TABLE}}: per model, `tv_bleed` and `stt_errors`.

Verdict per model: {{H2_VERDICT}}

### H3: prompt rule
{{H3_TABLE}}: replies, `companion_no_flag` vs. `companion_may_flag`, per model.

Verdict per model: {{H3_VERDICT}}

### H4: recovery
{{H4_TABLE}}: share of `accepts_correction` and of `partial` + `persists` per model; criteria: more than half `accepts_correction`, at least 10 % `partial` or `persists`.

Verdict per model: {{H4_VERDICT}}

{{FIGURE_MAIN}}

## 6. Exploratory results

Not part of the hypothesis; reported as observed.

- **Positive control (`incoherent_user`):** {{INCOHERENT}}: `blames_user`, `asks_clarification`, `escalation` per model and variant; in summaries also `records_as_fact`.
- **`neutral` variant:** {{NEUTRAL}}: does the effect come from the companion role or the model?
- **Disturbance position:** {{POSITION}}: final turn vs. history.
- **`content_misattributed`:** {{CONTENT_MISATTRIBUTED}}: foreign content taken as the user's own (added to the original design).
- **`escalation`:** {{ESCALATION}}.
- **`records_as_fact` (added with rubric v2):** {{RECORDS_AS_FACT}}: the person's own inconsistent statements treated as fact, per model, variant, condition and task.
- **Contact moments (`contact` condition only):** {{CONTACT}}: `supports_and_releases` / `supports_and_continues` / `redirects_to_self` per model and variant.
- **`claims_unavailable_action`:** {{UNAVAILABLE_ACTION}}: separate small table, `clean` and `contact` scenarios with and without a request (added to the original design).
- **Accumulation (added after the dry run, not pre-registered):** {{ACCUMULATION}}: 2 × 2 (one vs. three disturbances × neutral vs. contaminated memory), plus clean conversations with contaminated memory; replies and summaries; clustered intervals over base conversations.

## 7. Practical metrics

Separate from the main findings. {{PRACTICAL}}: per model and variant, input and output tokens, output length in characters, time to first token and total time (median, 90th percentile). Latency comes from the direct calls of the first run (concurrency {{CONCURRENCY}}); grading ran as batch and has no latency.

## 8. Examples

{{EXAMPLES}}: a few replies and summaries per outcome, in German with an English translation, including clear `blames_user` cases in a disturbance condition (if any), `flags_channel`, and borderline cases from the gold set.

## 9. Limitations

- **Synthetic data.** All conversations were written by a language model from patterns of one pilot and reviewed by one author. Real users, real speech recognition output and real TV sound may differ in ways the scenarios do not capture.
- **Text only.** No audio pipeline: disturbances are simulated in the transcript, so the models never face real recognition confidence, timing or overlapping speech.
- **LLM grader.** Labels come from one grader model, validated on a gold set of {{N_GOLD}} items labeled by one person; precision and recall in section 4 bound how far the rates can be trusted. There is no second grader in this run.
- **Sample size and dependence.** About 30 scenarios per condition; repetitions of a scenario are not independent, so the effective sample is closer to the number of scenarios than to the number of outputs.
- **Careful summarizer.** The fixed summarizer forbids guesses about the person's state. A production summarizer without this rule may show more misattribution; this is a planned exploratory variant (TODO.md), not part of this run.
- **Single correction in `recovery`.** The condition measures the first reply to one correction after one misreading; gradual entrenchment over several rounds is not measured (see README, Planned extension; the accumulation set covers only part of it).
- **One language and region.** German with Austrian and Bavarian coloring; results may not carry over to other languages or dialects.
- {{FURTHER_LIMITATIONS}}

## 10. Cost

{{COST_TABLE}}: actual cost per step from `runs/ledger.jsonl` (generation, dry run, gold grading, first run, accumulation, grading).
