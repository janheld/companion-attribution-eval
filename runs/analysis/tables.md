## H1

| Model | Task | Condition | blames_user | clean | Difference (clustered 95 %) | Verdict | Mean length (chars) |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 | replies | tv_bleed | 3/270 (1.1 % [0.4, 3.2]) | 0/270 (0.0 % [0.0, 1.4]) | +1.1 pp [+0.0, +2.6] | tendency | 184 |
| Haiku 4.5 | replies | stt_errors | 0/270 (0.0 % [0.0, 1.4]) | 0/270 (0.0 % [0.0, 1.4]) | +0.0 pp [+0.0, +0.0] | no difference | 184 |
| Haiku 4.5 | summaries | tv_bleed | 0/90 (0.0 % [0.0, 4.1]) | 0/90 (0.0 % [0.0, 4.1]) | +0.0 pp [+0.0, +0.0] | no difference | 726 |
| Haiku 4.5 | summaries | stt_errors | 1/90 (1.1 % [0.2, 6.0]) | 0/90 (0.0 % [0.0, 4.1]) | +1.1 pp [+0.0, +3.3] | tendency | 726 |
| Haiku 5.5 | replies | tv_bleed | 11/270 (4.1 % [2.3, 7.1]) | 0/270 (0.0 % [0.0, 1.4]) | +4.1 pp [+0.4, +10.4] | clear | 269 |
| Haiku 5.5 | replies | stt_errors | 1/270 (0.4 % [0.1, 2.1]) | 0/270 (0.0 % [0.0, 1.4]) | +0.4 pp [+0.0, +1.1] | tendency | 269 |
| Haiku 5.5 | summaries | tv_bleed | 1/90 (1.1 % [0.2, 6.0]) | 0/90 (0.0 % [0.0, 4.1]) | +1.1 pp [+0.0, +3.3] | tendency | 779 |
| Haiku 5.5 | summaries | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 0/90 (0.0 % [0.0, 4.1]) | +0.0 pp [+0.0, +0.0] | no difference | 779 |
| Sonnet 5.5 | replies | tv_bleed | 2/270 (0.7 % [0.2, 2.7]) | 0/270 (0.0 % [0.0, 1.4]) | +0.7 pp [+0.0, +1.9] | tendency | 340 |
| Sonnet 5.5 | replies | stt_errors | 0/270 (0.0 % [0.0, 1.4]) | 0/270 (0.0 % [0.0, 1.4]) | +0.0 pp [+0.0, +0.0] | no difference | 340 |
| Sonnet 5.5 | summaries | tv_bleed | 3/90 (3.3 % [1.1, 9.3]) | 0/90 (0.0 % [0.0, 4.1]) | +3.3 pp [+0.0, +8.9] | tendency | 854 |
| Sonnet 5.5 | summaries | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 0/90 (0.0 % [0.0, 4.1]) | +0.0 pp [+0.0, +0.0] | no difference | 854 |

## H2

| Model | Condition | Summaries | Replies | Difference (paired, clustered 95 %) | Verdict |
|---|---|---|---|---|---|
| Haiku 4.5 | tv_bleed | 0/90 (0.0 % [0.0, 4.1]) | 3/270 (1.1 % [0.4, 3.2]) | -1.1 pp [-2.6, +0.0] | no difference |
| Haiku 4.5 | stt_errors | 1/90 (1.1 % [0.2, 6.0]) | 0/270 (0.0 % [0.0, 1.4]) | +1.1 pp [+0.0, +3.3] | tendency |
| Haiku 5.5 | tv_bleed | 1/90 (1.1 % [0.2, 6.0]) | 11/270 (4.1 % [2.3, 7.1]) | -3.0 pp [-7.4, -0.4] | clear, opposite |
| Haiku 5.5 | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 1/270 (0.4 % [0.1, 2.1]) | -0.4 pp [-1.1, +0.0] | no difference |
| Sonnet 5.5 | tv_bleed | 3/90 (3.3 % [1.1, 9.3]) | 2/270 (0.7 % [0.2, 2.7]) | +2.6 pp [-0.7, +7.4] | tendency |
| Sonnet 5.5 | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 0/270 (0.0 % [0.0, 1.4]) | +0.0 pp [+0.0, +0.0] | no difference |

## H3

| Model | companion_no_flag | companion_may_flag | Difference (paired, clustered 95 %) | Verdict |
|---|---|---|---|---|
| Haiku 4.5 | 1/180 (0.6 % [0.1, 3.1]) | 0/180 (0.0 % [0.0, 2.1]) | +0.6 pp [+0.0, +1.7] | tendency |
| Haiku 5.5 | 2/180 (1.1 % [0.3, 4.0]) | 4/180 (2.2 % [0.9, 5.6]) | -1.1 pp [-2.8, +0.0] | no difference |
| Sonnet 5.5 | 0/180 (0.0 % [0.0, 2.1]) | 0/180 (0.0 % [0.0, 2.1]) | +0.0 pp [+0.0, +0.0] | no difference |

## H4

| Model | accepts_correction | clustered 95 % | > 50 % | partial or persists | clustered 95 % | ≥ 10 % | Distribution |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 | 174/180 (96.7 % [92.9, 98.5]) | [91.7, 100.0] | clear | 6/180 (3.3 % [1.5, 7.1]) | [0.0, 8.3] | clear, opposite | accepts_correction 174, partial 6 |
| Haiku 5.5 | 158/180 (87.8 % [82.2, 91.8]) | [76.7, 96.1] | clear | 22/180 (12.2 % [8.2, 17.8]) | [3.9, 23.3] | tendency | accepts_correction 158, partial 13, persists 9 |
| Sonnet 5.5 | 169/180 (93.9 % [89.4, 96.6]) | [86.1, 99.4] | clear | 11/180 (6.1 % [3.4, 10.6]) | [0.6, 13.9] | no difference | accepts_correction 169, partial 11 |

## blames_all

| Model | Condition | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|---|
| Haiku 4.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | tv_bleed | 2/90 | 1/90 | 0/90 | 0/90 |
| Haiku 4.5 | stt_errors | 0/90 | 0/90 | 0/90 | 1/90 |
| Haiku 4.5 | incoherent_user | 12/90 | 8/90 | 6/90 | 3/90 |
| Haiku 4.5 | recovery | 1/60 | 2/60 | 1/60 | 7/60 |
| Haiku 5.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | tv_bleed | 5/90 | 2/90 | 4/90 | 1/90 |
| Haiku 5.5 | stt_errors | 1/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | incoherent_user | 15/90 | 5/90 | 5/90 | 2/90 |
| Haiku 5.5 | recovery | 6/60 | 6/60 | 1/60 | 20/60 |
| Sonnet 5.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | tv_bleed | 2/90 | 0/90 | 0/90 | 3/90 |
| Sonnet 5.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | incoherent_user | 27/90 | 5/90 | 6/90 | 13/90 |
| Sonnet 5.5 | recovery | 2/60 | 2/60 | 0/60 | 3/60 |

## incoherent

| Model | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|
| **blames_user** | | | | |
| Haiku 4.5 | 12/90 | 8/90 | 6/90 | 3/90 |
| Haiku 5.5 | 15/90 | 5/90 | 5/90 | 2/90 |
| Sonnet 5.5 | 27/90 | 5/90 | 6/90 | 13/90 |
| **asks_clarification** | | | | |
| Haiku 4.5 | 25/90 | 23/90 | 24/90 | 4/90 |
| Haiku 5.5 | 13/90 | 13/90 | 16/90 | 3/90 |
| Sonnet 5.5 | 34/90 | 39/90 | 45/90 | 21/90 |
| **concern_or_crisis** | | | | |
| Haiku 4.5 | 3/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | 7/90 | 2/90 | 2/90 | 0/90 |
| Sonnet 5.5 | 18/90 | 0/90 | 3/90 | 0/90 |
| **crisis** | | | | |
| Haiku 4.5 | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | 4/90 | 1/90 | 0/90 | 0/90 |
| Sonnet 5.5 | 9/90 | 0/90 | 1/90 | 0/90 |
| **records_as_fact** | | | | |
| Haiku 4.5 | 4/90 | 6/90 | 5/90 | 53/90 |
| Haiku 5.5 | 15/90 | 15/90 | 18/90 | 59/90 |
| Sonnet 5.5 | 1/90 | 2/90 | 0/90 | 51/90 |

## neutral

| Model | Condition | neutral | companion (both variants) | Difference (paired, clustered 95 %) | Verdict |
|---|---|---|---|---|---|
| Haiku 4.5 | tv_bleed | 2/90 (2.2 % [0.6, 7.7]) | 1/180 (0.6 % [0.1, 3.1]) | +1.7 pp [-1.1, +5.0] | tendency |
| Haiku 4.5 | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 0/180 (0.0 % [0.0, 2.1]) | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | incoherent_user | 12/90 (13.3 % [7.8, 21.9]) | 14/180 (7.8 % [4.7, 12.6]) | +5.6 pp [-2.2, +14.4] | tendency |
| Haiku 5.5 | tv_bleed | 5/90 (5.6 % [2.4, 12.4]) | 6/180 (3.3 % [1.5, 7.1]) | +2.2 pp [-0.6, +5.6] | tendency |
| Haiku 5.5 | stt_errors | 1/90 (1.1 % [0.2, 6.0]) | 0/180 (0.0 % [0.0, 2.1]) | +1.1 pp [+0.0, +3.3] | tendency |
| Haiku 5.5 | incoherent_user | 15/90 (16.7 % [10.4, 25.7]) | 10/180 (5.6 % [3.0, 9.9]) | +11.1 pp [+3.9, +19.4] | clear |
| Sonnet 5.5 | tv_bleed | 2/90 (2.2 % [0.6, 7.7]) | 0/180 (0.0 % [0.0, 2.1]) | +2.2 pp [+0.0, +5.6] | tendency |
| Sonnet 5.5 | stt_errors | 0/90 (0.0 % [0.0, 4.1]) | 0/180 (0.0 % [0.0, 2.1]) | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | incoherent_user | 27/90 (30.0 % [21.5, 40.1]) | 11/180 (6.1 % [3.4, 10.6]) | +23.9 pp [+12.8, +35.6] | clear |

## position

| Model | Task | Position | blames_user | content_misattributed |
|---|---|---|---|---|
| Haiku 4.5 | replies | final_turn | 3/270 (1.1 % [0.4, 3.2]) | 18/270 (6.7 % [4.3, 10.3]) |
| Haiku 4.5 | replies | history | 0/270 (0.0 % [0.0, 1.4]) | 2/270 (0.7 % [0.2, 2.7]) |
| Haiku 4.5 | summaries | final_turn | 1/90 (1.1 % [0.2, 6.0]) | 24/90 (26.7 % [18.6, 36.6]) |
| Haiku 4.5 | summaries | history | 0/90 (0.0 % [0.0, 4.1]) | 25/90 (27.8 % [19.6, 37.8]) |
| Haiku 5.5 | replies | final_turn | 12/270 (4.4 % [2.6, 7.6]) | 79/270 (29.3 % [24.2, 34.9]) |
| Haiku 5.5 | replies | history | 0/270 (0.0 % [0.0, 1.4]) | 1/270 (0.4 % [0.1, 2.1]) |
| Haiku 5.5 | summaries | final_turn | 1/90 (1.1 % [0.2, 6.0]) | 45/90 (50.0 % [39.9, 60.1]) |
| Haiku 5.5 | summaries | history | 0/90 (0.0 % [0.0, 4.1]) | 35/90 (38.9 % [29.5, 49.2]) |
| Sonnet 5.5 | replies | final_turn | 1/270 (0.4 % [0.1, 2.1]) | 10/270 (3.7 % [2.0, 6.7]) |
| Sonnet 5.5 | replies | history | 1/270 (0.4 % [0.1, 2.1]) | 10/270 (3.7 % [2.0, 6.7]) |
| Sonnet 5.5 | summaries | final_turn | 2/90 (2.2 % [0.6, 7.7]) | 21/90 (23.3 % [15.8, 33.1]) |
| Sonnet 5.5 | summaries | history | 1/90 (1.1 % [0.2, 6.0]) | 26/90 (28.9 % [20.5, 39.0]) |

## content_misattributed

| Model | Condition | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|---|
| Haiku 4.5 | tv_bleed | 12/90 | 1/90 | 4/90 | 13/90 |
| Haiku 4.5 | stt_errors | 1/90 | 1/90 | 1/90 | 36/90 |
| Haiku 4.5 | recovery | 3/60 | 1/60 | 0/60 | 20/60 |
| Haiku 5.5 | tv_bleed | 27/90 | 23/90 | 27/90 | 42/90 |
| Haiku 5.5 | stt_errors | 0/90 | 2/90 | 1/90 | 38/90 |
| Haiku 5.5 | recovery | 8/60 | 7/60 | 3/60 | 31/60 |
| Sonnet 5.5 | tv_bleed | 12/90 | 7/90 | 0/90 | 18/90 |
| Sonnet 5.5 | stt_errors | 1/90 | 0/90 | 0/90 | 29/90 |
| Sonnet 5.5 | recovery | 4/60 | 3/60 | 1/60 | 13/60 |

## records_as_fact

| Model | Condition | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|---|
| Haiku 4.5 | incoherent_user | 4/90 | 6/90 | 5/90 | 53/90 |
| Haiku 4.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | tv_bleed | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | stt_errors | 0/90 | 0/90 | 0/90 | 1/90 |
| Haiku 5.5 | incoherent_user | 15/90 | 15/90 | 18/90 | 59/90 |
| Haiku 5.5 | clean | 0/90 | 0/90 | 0/90 | 1/90 |
| Haiku 5.5 | tv_bleed | 1/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | incoherent_user | 1/90 | 2/90 | 0/90 | 51/90 |
| Sonnet 5.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | tv_bleed | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |

## escalation

| Model | Condition | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|---|
| Haiku 4.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | tv_bleed | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | incoherent_user | 3/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | recovery | 0/60 | 0/60 | 0/60 | 0/60 |
| Haiku 5.5 | clean | 0/90 | 0/90 | 2/90 | 0/90 |
| Haiku 5.5 | tv_bleed | 3/90 | 0/90 | 1/90 | 0/90 |
| Haiku 5.5 | stt_errors | 1/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | incoherent_user | 7/90 | 2/90 | 2/90 | 0/90 |
| Haiku 5.5 | recovery | 5/60 | 3/60 | 0/60 | 0/60 |
| Sonnet 5.5 | clean | 2/90 | 1/90 | 0/90 | 0/90 |
| Sonnet 5.5 | tv_bleed | 1/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | incoherent_user | 18/90 | 0/90 | 3/90 | 0/90 |
| Sonnet 5.5 | recovery | 1/60 | 0/60 | 0/60 | 0/60 |

## crisis

| Model | Condition | replies neutral | replies no_flag | replies may_flag | summaries |
|---|---|---|---|---|---|
| Haiku 4.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | tv_bleed | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | incoherent_user | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 4.5 | recovery | 0/60 | 0/60 | 0/60 | 0/60 |
| Haiku 5.5 | clean | 0/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | tv_bleed | 1/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | stt_errors | 1/90 | 0/90 | 0/90 | 0/90 |
| Haiku 5.5 | incoherent_user | 4/90 | 1/90 | 0/90 | 0/90 |
| Haiku 5.5 | recovery | 3/60 | 1/60 | 0/60 | 0/60 |
| Sonnet 5.5 | clean | 2/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | tv_bleed | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | stt_errors | 0/90 | 0/90 | 0/90 | 0/90 |
| Sonnet 5.5 | incoherent_user | 9/90 | 0/90 | 1/90 | 0/90 |
| Sonnet 5.5 | recovery | 0/60 | 0/60 | 0/60 | 0/60 |

## contact

| Model | Variant | supports_and_releases | supports_and_continues | redirects_to_self | not_applicable |
|---|---|---|---|---|---|
| Haiku 4.5 | neutral | 78/90 | 12/90 | 0/90 | 0/90 |
| Haiku 4.5 | no_flag | 84/90 | 5/90 | 1/90 | 0/90 |
| Haiku 4.5 | may_flag | 89/90 | 1/90 | 0/90 | 0/90 |
| Haiku 5.5 | neutral | 83/90 | 5/90 | 2/90 | 0/90 |
| Haiku 5.5 | no_flag | 83/90 | 6/90 | 1/90 | 0/90 |
| Haiku 5.5 | may_flag | 79/90 | 10/90 | 1/90 | 0/90 |
| Sonnet 5.5 | neutral | 79/90 | 11/90 | 0/90 | 0/90 |
| Sonnet 5.5 | no_flag | 88/90 | 2/90 | 0/90 | 0/90 |
| Sonnet 5.5 | may_flag | 89/90 | 1/90 | 0/90 | 0/90 |

## unavailable

| Model | Request in last turn | all variants | neutral | no_flag | may_flag |
|---|---|---|---|---|---|
| Haiku 4.5 | yes | 38/126 (30.2 % [22.8, 38.7]) | 32/42 | 3/42 | 3/42 |
| Haiku 4.5 | no | 0/414 (0.0 % [0.0, 0.9]) | 0/138 | 0/138 | 0/138 |
| Haiku 5.5 | yes | 14/126 (11.1 % [6.7, 17.8]) | 14/42 | 0/42 | 0/42 |
| Haiku 5.5 | no | 2/414 (0.5 % [0.1, 1.7]) | 1/138 | 1/138 | 0/138 |
| Sonnet 5.5 | yes | 5/126 (4.0 % [1.7, 9.0]) | 5/42 | 0/42 | 0/42 |
| Sonnet 5.5 | no | 0/414 (0.0 % [0.0, 0.9]) | 0/138 | 0/138 | 0/138 |

## practical

| Model | Task | Variant | Input | Cache read | Cache write | Output | Length (chars) | TTFT median / p90 (s) | Total median / p90 (s) |
|---|---|---|---|---|---|---|---|---|---|
| Haiku 4.5 | replies | neutral | 1263 | 0 | 0 | 93 | 260 | 0.46 / 0.50 | 1.37 / 2.18 |
| Haiku 4.5 | replies | no_flag | 3422 | 0 | 441 | 54 | 147 | 0.47 / 0.51 | 1.03 / 1.33 |
| Haiku 4.5 | replies | may_flag | 3322 | 0 | 592 | 54 | 146 | 0.47 / 0.51 | 1.02 / 1.32 |
| Haiku 4.5 | summaries | summarizer | 1161 | 0 | 0 | 252 | 726 | 0.46 / 0.53 | 2.69 / 3.23 |
| Haiku 5.5 | replies | neutral | 4 | 0 | 1708 | 171 | 349 | 0.61 / 1.17 | 1.54 / 2.52 |
| Haiku 5.5 | replies | no_flag | 4 | 3557 | 1698 | 111 | 226 | 0.61 / 0.97 | 1.25 / 1.92 |
| Haiku 5.5 | replies | may_flag | 4 | 3634 | 1699 | 113 | 231 | 0.63 / 1.17 | 1.30 / 1.99 |
| Haiku 5.5 | summaries | summarizer | 4 | 841 | 728 | 388 | 779 | 0.65 / 1.23 | 2.25 / 3.17 |
| Sonnet 5.5 | replies | neutral | 4 | 0 | 1700 | 381 | 593 | 0.94 / 3.59 | 3.66 / 5.93 |
| Sonnet 5.5 | replies | no_flag | 4 | 3558 | 1689 | 229 | 212 | 1.06 / 4.04 | 2.21 / 4.79 |
| Sonnet 5.5 | replies | may_flag | 4 | 3635 | 1690 | 228 | 214 | 1.06 / 3.99 | 2.24 / 4.83 |
| Sonnet 5.5 | summaries | summarizer | 4 | 842 | 728 | 423 | 854 | 1.15 / 2.34 | 3.76 / 5.04 |

## acc_cells

| Model | Task | Cell | blames_user | content_misattributed |
|---|---|---|---|---|
| Haiku 4.5 | replies | clean, neutral | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Haiku 4.5 | replies | clean, primed | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Haiku 4.5 | replies | 1 disturbance, neutral | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 4.5 | replies | 1 disturbance, primed | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 4.5 | replies | 3 disturbances, neutral | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 4.5 | replies | 3 disturbances, primed | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 4.5 | summaries | clean, neutral | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Haiku 4.5 | summaries | clean, primed | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Haiku 4.5 | summaries | 1 disturbance, neutral | 0/36 (0.0 % [0.0, 9.6]) | 12/36 (33.3 % [20.2, 49.7]) |
| Haiku 4.5 | summaries | 1 disturbance, primed | 0/36 (0.0 % [0.0, 9.6]) | 13/36 (36.1 % [22.5, 52.4]) |
| Haiku 4.5 | summaries | 3 disturbances, neutral | 0/36 (0.0 % [0.0, 9.6]) | 16/36 (44.4 % [29.5, 60.4]) |
| Haiku 4.5 | summaries | 3 disturbances, primed | 0/36 (0.0 % [0.0, 9.6]) | 19/36 (52.8 % [37.0, 68.0]) |
| Haiku 5.5 | replies | clean, neutral | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Haiku 5.5 | replies | clean, primed | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Haiku 5.5 | replies | 1 disturbance, neutral | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 5.5 | replies | 1 disturbance, primed | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Haiku 5.5 | replies | 3 disturbances, neutral | 0/108 (0.0 % [0.0, 3.4]) | 1/108 (0.9 % [0.2, 5.1]) |
| Haiku 5.5 | replies | 3 disturbances, primed | 1/108 (0.9 % [0.2, 5.1]) | 1/108 (0.9 % [0.2, 5.1]) |
| Haiku 5.5 | summaries | clean, neutral | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Haiku 5.5 | summaries | clean, primed | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Haiku 5.5 | summaries | 1 disturbance, neutral | 0/36 (0.0 % [0.0, 9.6]) | 13/36 (36.1 % [22.5, 52.4]) |
| Haiku 5.5 | summaries | 1 disturbance, primed | 0/36 (0.0 % [0.0, 9.6]) | 16/36 (44.4 % [29.5, 60.4]) |
| Haiku 5.5 | summaries | 3 disturbances, neutral | 0/36 (0.0 % [0.0, 9.6]) | 21/36 (58.3 % [42.2, 72.9]) |
| Haiku 5.5 | summaries | 3 disturbances, primed | 0/36 (0.0 % [0.0, 9.6]) | 20/36 (55.6 % [39.6, 70.5]) |
| Sonnet 5.5 | replies | clean, neutral | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Sonnet 5.5 | replies | clean, primed | 0/36 (0.0 % [0.0, 9.6]) | 0/36 (0.0 % [0.0, 9.6]) |
| Sonnet 5.5 | replies | 1 disturbance, neutral | 0/108 (0.0 % [0.0, 3.4]) | 1/108 (0.9 % [0.2, 5.1]) |
| Sonnet 5.5 | replies | 1 disturbance, primed | 1/108 (0.9 % [0.2, 5.1]) | 2/108 (1.9 % [0.5, 6.5]) |
| Sonnet 5.5 | replies | 3 disturbances, neutral | 0/108 (0.0 % [0.0, 3.4]) | 0/108 (0.0 % [0.0, 3.4]) |
| Sonnet 5.5 | replies | 3 disturbances, primed | 0/108 (0.0 % [0.0, 3.4]) | 4/108 (3.7 % [1.4, 9.1]) |
| Sonnet 5.5 | summaries | clean, neutral | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Sonnet 5.5 | summaries | clean, primed | 0/12 (0.0 % [0.0, 24.2]) | 0/12 (0.0 % [0.0, 24.2]) |
| Sonnet 5.5 | summaries | 1 disturbance, neutral | 0/36 (0.0 % [0.0, 9.6]) | 10/36 (27.8 % [15.8, 44.0]) |
| Sonnet 5.5 | summaries | 1 disturbance, primed | 0/36 (0.0 % [0.0, 9.6]) | 9/36 (25.0 % [13.8, 41.1]) |
| Sonnet 5.5 | summaries | 3 disturbances, neutral | 0/36 (0.0 % [0.0, 9.6]) | 16/36 (44.4 % [29.5, 60.4]) |
| Sonnet 5.5 | summaries | 3 disturbances, primed | 0/36 (0.0 % [0.0, 9.6]) | 19/36 (52.8 % [37.0, 68.0]) |

## acc_diffs

| Model | Task | Comparison | Label | a | b | Difference (paired by base, clustered 95 %) | Verdict |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 | replies | 3 vs. 1 disturbance | blames_user | 0/216 | 0/216 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | replies | 3 vs. 1 disturbance | content_misattributed | 0/216 | 0/216 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | replies | primed vs. neutral memory (disturbed) | blames_user | 0/216 | 0/216 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | replies | primed vs. neutral memory (disturbed) | content_misattributed | 0/216 | 0/216 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | replies | primed vs. neutral memory (clean) | blames_user | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | replies | primed vs. neutral memory (clean) | content_misattributed | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | summaries | 3 vs. 1 disturbance | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | summaries | 3 vs. 1 disturbance | content_misattributed | 35/72 | 25/72 | +13.9 pp [-6.9, +36.1] | tendency |
| Haiku 4.5 | summaries | primed vs. neutral memory (disturbed) | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | summaries | primed vs. neutral memory (disturbed) | content_misattributed | 32/72 | 28/72 | +5.6 pp [+0.0, +15.3] | tendency |
| Haiku 4.5 | summaries | primed vs. neutral memory (clean) | blames_user | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 4.5 | summaries | primed vs. neutral memory (clean) | content_misattributed | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | replies | 3 vs. 1 disturbance | blames_user | 1/216 | 0/216 | +0.5 pp [+0.0, +1.4] | tendency |
| Haiku 5.5 | replies | 3 vs. 1 disturbance | content_misattributed | 2/216 | 0/216 | +0.9 pp [+0.0, +2.8] | tendency |
| Haiku 5.5 | replies | primed vs. neutral memory (disturbed) | blames_user | 1/216 | 0/216 | +0.5 pp [+0.0, +1.4] | tendency |
| Haiku 5.5 | replies | primed vs. neutral memory (disturbed) | content_misattributed | 1/216 | 1/216 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | replies | primed vs. neutral memory (clean) | blames_user | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | replies | primed vs. neutral memory (clean) | content_misattributed | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | summaries | 3 vs. 1 disturbance | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | summaries | 3 vs. 1 disturbance | content_misattributed | 41/72 | 29/72 | +16.7 pp [-1.4, +41.7] | tendency |
| Haiku 5.5 | summaries | primed vs. neutral memory (disturbed) | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | summaries | primed vs. neutral memory (disturbed) | content_misattributed | 36/72 | 34/72 | +2.8 pp [+0.0, +6.9] | tendency |
| Haiku 5.5 | summaries | primed vs. neutral memory (clean) | blames_user | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |
| Haiku 5.5 | summaries | primed vs. neutral memory (clean) | content_misattributed | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | replies | 3 vs. 1 disturbance | blames_user | 0/216 | 1/216 | -0.5 pp [-1.4, +0.0] | no difference |
| Sonnet 5.5 | replies | 3 vs. 1 disturbance | content_misattributed | 4/216 | 3/216 | +0.5 pp [-0.9, +2.3] | tendency |
| Sonnet 5.5 | replies | primed vs. neutral memory (disturbed) | blames_user | 1/216 | 0/216 | +0.5 pp [+0.0, +1.4] | tendency |
| Sonnet 5.5 | replies | primed vs. neutral memory (disturbed) | content_misattributed | 6/216 | 1/216 | +2.3 pp [-0.9, +6.5] | tendency |
| Sonnet 5.5 | replies | primed vs. neutral memory (clean) | blames_user | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | replies | primed vs. neutral memory (clean) | content_misattributed | 0/36 | 0/36 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | summaries | 3 vs. 1 disturbance | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | summaries | 3 vs. 1 disturbance | content_misattributed | 35/72 | 19/72 | +22.2 pp [-8.3, +54.2] | tendency |
| Sonnet 5.5 | summaries | primed vs. neutral memory (disturbed) | blames_user | 0/72 | 0/72 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | summaries | primed vs. neutral memory (disturbed) | content_misattributed | 28/72 | 26/72 | +2.8 pp [-2.8, +9.7] | tendency |
| Sonnet 5.5 | summaries | primed vs. neutral memory (clean) | blames_user | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |
| Sonnet 5.5 | summaries | primed vs. neutral memory (clean) | content_misattributed | 0/12 | 0/12 | +0.0 pp [+0.0, +0.0] | no difference |