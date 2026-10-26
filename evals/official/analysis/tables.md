# Eval summary

pass@1 = mean reward over graded rollouts. Intervals are 95%: per group, a percentile bootstrap resampling tasks (2000 resamples, seed 0); per task, Wilson. Truncated = no reply, or the last call ended with finish_reason == length. Infra errors (never graded) are excluded from every rate. A task bootstrap has zero width when every task has the same rate (e.g. all 4/4): it ignores sampling noise within a task. Output-token statistics leave out no-reply rollouts (timed out before the first response; their token count is not recorded). pass@8 = mean over tasks of the unbiased 1 - C(n-c, 8)/C(n, 8), same task bootstrap; tasks with fewer than 8 graded rollouts have none and are left out (the tasks counted are shown). Mixed = 0 < hits < graded rollouts (1-7 of 8 at k=8). pass@1 compiled = hits over graded rollouts that are not compile_error or no_submission.

|  | group | role | runs |
|---|---|---|---|
| G1 | nvidia/nemotron-3-nano-30b-a3b · null · max_tokens=65536 | calibration model | closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b |
| G2 | openai/gpt-6-sol · null · max_tokens=65536 |  | closure-bench--openai--gpt-6-sol--null--2fc9e854 |
| G3 | qwen/qwen3.8-27b · null · max_tokens=65536 |  | closure-bench--qwen--qwen3.8-27b--null--ec46d01c |

## Per group

|  | rollouts | pass@1 [bootstrap 95%] | task mean | pass@8 [bootstrap 95%] | tasks mixed / no hit / all hit | pass@1 untruncated [bootstrap 95%] | pass@1 compiled [bootstrap 95%] | truncated | in tokens | out tokens | turns | run.sh calls (rollouts) | sim s | submission |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G1 | 208 (+0 infra) | 8% [2%, 14%] | 8% | 27% [12%, 46%] | 7 / 19 / 0 | 8% [2%, 14%] | 17% [6%, 30%] (n=96) | 0% | 23288 | 23612 | 1.0 | 0.0 (0) | 9.2 | reply 208 |
| G2 | 208 (+0 infra) | 84% [74%, 94%] | 84% | 100% [100%, 100%] | 9 / 0 / 17 | 84% [74%, 94%] | 96% [90%, 100%] (n=182) | 0% | 21633 | 1816 | 1.0 | 0.0 (0) | 6.9 | reply 208 |
| G3 | 207 (+1 infra) | 67% [56%, 77%] | 67% | 96% [88%, 100%] (25 tasks) | 19 / 1 / 6 | 72% [62%, 81%] | 80% [70%, 89%] (n=173) | 7% | 23459 | 40633 | 1.0 | 0.0 (0) | 6.4 | none 18, reply 189 |

## pass@1 by tag

|  | tag | tasks | rollouts | pass@1 [bootstrap 95%] | task mean | pass@8 [bootstrap 95%] | tasks mixed / no hit / all hit | pass@1 untruncated [bootstrap 95%] | truncated |
|---|---|---|---|---|---|---|---|---|---|
| G1 | padded | 5 | 40 (+0 infra) | 2% [0%, 8%] | 2% | 20% [0%, 60%] | 1 / 4 / 0 | 2% [0%, 8%] | 0% |
| G1 | untagged | 21 | 168 (+0 infra) | 9% [3%, 17%] | 9% | 29% [10%, 48%] | 6 / 15 / 0 | 9% [3%, 17%] | 0% |
| G2 | padded | 5 | 40 (+0 infra) | 100% [100%, 100%] | 100% | 100% [100%, 100%] | 0 / 0 / 5 | 100% [100%, 100%] | 0% |
| G2 | untagged | 21 | 168 (+0 infra) | 80% [67%, 92%] | 80% | 100% [100%, 100%] | 9 / 0 / 12 | 80% [67%, 92%] | 0% |
| G3 | padded | 5 | 40 (+0 infra) | 62% [48%, 82%] | 62% | 100% [100%, 100%] | 4 / 0 / 1 | 66% [53%, 84%] | 5% |
| G3 | untagged | 21 | 167 (+1 infra) | 68% [55%, 79%] | 68% | 95% [85%, 100%] (20 tasks) | 15 / 1 / 5 | 73% [61%, 83%] | 7% |

## Outcomes per group (graded rollouts)

|  | no_submission | policy_violation | illegal_stimulus | compile_error | timeout | runtime_error | no_finish | missed | hit |
|---|---|---|---|---|---|---|---|---|---|
| G1 | 3 | 1 | 17 | 109 | 21 | 3 | 0 | 38 | 16 |
| G2 | 0 | 0 | 0 | 26 | 0 | 0 | 0 | 7 | 175 |
| G3 | 18 | 0 | 15 | 16 | 0 | 7 | 0 | 13 | 138 |

## pass@1 per task (Wilson 95%)

| task | G1 | G2 | G3 |
|---|---|---|---|
| uart/R12 | 0% [0%, 32%] (n=8) | 75% [41%, 93%] (n=8) | 75% [41%, 93%] (n=8) |
| uart/R13 | 0% [0%, 32%] (n=8) | 12% [2%, 47%] (n=8) | 62% [31%, 86%] (n=8) |
| uart/R14 | 0% [0%, 32%] (n=8) | 50% [22%, 78%] (n=8) | 71% [36%, 92%] (n=7) |
| uart/R15 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 50% [22%, 78%] (n=8) |
| uart/R16 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 88% [53%, 98%] (n=8) |
| uart/R17 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/R18 | 25% [7%, 59%] (n=8) | 100% [68%, 100%] (n=8) | 88% [53%, 98%] (n=8) |
| uart/R19 | 25% [7%, 59%] (n=8) | 88% [53%, 98%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/R20 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 62% [31%, 86%] (n=8) |
| uart/R21 | 12% [2%, 47%] (n=8) | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/R22 | 38% [14%, 69%] (n=8) | 100% [68%, 100%] (n=8) | 88% [53%, 98%] (n=8) |
| uart/R23 | 0% [0%, 32%] (n=8) | 38% [14%, 69%] (n=8) | 75% [41%, 93%] (n=8) |
| uart/R24 | 62% [31%, 86%] (n=8) | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/R25 | 0% [0%, 32%] (n=8) | 75% [41%, 93%] (n=8) | 50% [22%, 78%] (n=8) |
| uart/R26 | 0% [0%, 32%] (n=8) | 38% [14%, 69%] (n=8) | 0% [0%, 32%] (n=8) |
| uart/R27 | 0% [0%, 32%] (n=8) | 88% [53%, 98%] (n=8) | 62% [31%, 86%] (n=8) |
| uart/R28 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 62% [31%, 86%] (n=8) |
| uart/R29 | 0% [0%, 32%] (n=8) | 25% [7%, 59%] (n=8) | 62% [31%, 86%] (n=8) |
| uart/T5 | 25% [7%, 59%] (n=8) | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/T6 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 38% [14%, 69%] (n=8) |
| uart/T7 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 50% [22%, 78%] (n=8) |
| uart/T8 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| uart/T9 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 12% [2%, 47%] (n=8) |
| uart/T10 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 38% [14%, 69%] (n=8) |
| uart/T11 | 12% [2%, 47%] (n=8) | 100% [68%, 100%] (n=8) | 50% [22%, 78%] (n=8) |
| uart/T12 | 0% [0%, 32%] (n=8) | 100% [68%, 100%] (n=8) | 50% [22%, 78%] (n=8) |

## Per task detail

### G1: nvidia/nemotron-3-nano-30b-a3b · null · max_tokens=65536

| task | n | pass@1 [Wilson 95%] | untruncated | truncated | out tokens finished (mean / median) | out tokens truncated (mean / median) | outcomes | turns | sim s |
|---|---|---|---|---|---|---|---|---|---|
| uart/R12 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 29157 / 29198 | – | compile_error 3, missed 5 | 1.0 | 4.1 |
| uart/R13 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 20328 / 20663 | – | compile_error 6, missed 2 | 1.0 | 2.1 |
| uart/R14 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 24306 / 25490 | – | compile_error 5, timeout 3 | 1.0 | 25.6 |
| uart/R15 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 27969 / 27192 | – | compile_error 4, timeout 1, runtime_error 1, missed 2 | 1.0 | 10.7 |
| uart/R16 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 20248 / 20575 | – | illegal_stimulus 1, compile_error 5, timeout 1, missed 1 | 1.0 | 10.2 |
| uart/R17 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 27634 / 25488 | – | compile_error 2, runtime_error 1, missed 5 | 1.0 | 5.0 |
| uart/R18 | 8 | 25% [7%, 59%] | 25% [7%, 59%] | 0% | 20022 / 19566 | – | compile_error 4, timeout 2, hit 2 | 1.0 | 18.2 |
| uart/R19 | 8 | 25% [7%, 59%] | 25% [7%, 59%] | 0% | 17926 / 17506 | – | compile_error 4, runtime_error 1, missed 1, hit 2 | 1.0 | 4.1 |
| uart/R20 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 32858 / 30708 | – | policy_violation 1, compile_error 7 | 1.0 | 0.0 |
| uart/R21 | 8 | 12% [2%, 47%] | 12% [2%, 47%] | 0% | 12384 / 11353 | – | compile_error 5, missed 2, hit 1 | 1.0 | 2.8 |
| uart/R22 | 8 | 38% [14%, 69%] | 38% [14%, 69%] | 0% | 17727 / 16634 | – | no_submission 1, compile_error 2, timeout 1, missed 1, hit 3 | 1.0 | 11.7 |
| uart/R23 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 16688 / 17182 | – | no_submission 1, compile_error 4, timeout 2, missed 1 | 1.0 | 17.9 |
| uart/R24 | 8 | 62% [31%, 86%] | 62% [31%, 86%] | 0% | 21039 / 19328 | – | compile_error 2, timeout 1, hit 5 | 1.0 | 13.2 |
| uart/R25 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 34381 / 34594 | – | compile_error 5, timeout 2, missed 1 | 1.0 | 17.5 |
| uart/R26 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 23569 / 23246 | – | compile_error 3, missed 5 | 1.0 | 5.6 |
| uart/R27 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 42471 / 43132 | – | compile_error 5, timeout 3 | 1.0 | 24.9 |
| uart/R28 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 25248 / 23595 | – | compile_error 7, timeout 1 | 1.0 | 8.2 |
| uart/R29 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 30167 / 27527 | – | compile_error 5, timeout 1, missed 2 | 1.0 | 9.8 |
| uart/T5 | 8 | 25% [7%, 59%] | 25% [7%, 59%] | 0% | 20365 / 18165 | – | illegal_stimulus 2, compile_error 4, hit 2 | 1.0 | 3.1 |
| uart/T6 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 23796 / 22700 | – | compile_error 5, missed 3 | 1.0 | 2.2 |
| uart/T7 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 24349 / 22799 | – | illegal_stimulus 2, compile_error 4, timeout 1, missed 1 | 1.0 | 10.5 |
| uart/T8 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 19640 / 17624 | – | illegal_stimulus 1, compile_error 6, missed 1 | 1.0 | 1.5 |
| uart/T9 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 20009 / 18804 | – | illegal_stimulus 4, compile_error 3, timeout 1 | 1.0 | 11.5 |
| uart/T10 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 20777 / 20019 | – | illegal_stimulus 2, compile_error 3, missed 3 | 1.0 | 4.4 |
| uart/T11 | 8 | 12% [2%, 47%] | 12% [2%, 47%] | 0% | 19300 / 18910 | – | illegal_stimulus 4, compile_error 1, timeout 1, missed 1, hit 1 | 1.0 | 13.4 |
| uart/T12 | 8 | 0% [0%, 32%] | 0% [0%, 32%] | 0% | 21548 / 20042 | – | no_submission 1, illegal_stimulus 1, compile_error 5, missed 1 | 1.0 | 1.5 |

### G2: openai/gpt-6-sol · null · max_tokens=65536

| task | n | pass@1 [Wilson 95%] | untruncated | truncated | out tokens finished (mean / median) | out tokens truncated (mean / median) | outcomes | turns | sim s |
|---|---|---|---|---|---|---|---|---|---|
| uart/R12 | 8 | 75% [41%, 93%] | 75% [41%, 93%] | 0% | 2024 / 2036 | – | compile_error 2, hit 6 | 1.0 | 8.0 |
| uart/R13 | 8 | 12% [2%, 47%] | 12% [2%, 47%] | 0% | 2266 / 2214 | – | compile_error 7, hit 1 | 1.0 | 1.3 |
| uart/R14 | 8 | 50% [22%, 78%] | 50% [22%, 78%] | 0% | 2802 / 2652 | – | compile_error 4, hit 4 | 1.0 | 4.1 |
| uart/R15 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 2719 / 2736 | – | hit 8 | 1.0 | 7.3 |
| uart/R16 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1461 / 1493 | – | hit 8 | 1.0 | 7.0 |
| uart/R17 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 924 / 918 | – | hit 8 | 1.0 | 11.6 |
| uart/R18 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1474 / 1524 | – | hit 8 | 1.0 | 8.9 |
| uart/R19 | 8 | 88% [53%, 98%] | 88% [53%, 98%] | 0% | 1360 / 1318 | – | compile_error 1, hit 7 | 1.0 | 7.4 |
| uart/R20 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 2038 / 1986 | – | hit 8 | 1.0 | 9.9 |
| uart/R21 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1283 / 1279 | – | hit 8 | 1.0 | 7.0 |
| uart/R22 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1156 / 1130 | – | hit 8 | 1.0 | 7.2 |
| uart/R23 | 8 | 38% [14%, 69%] | 38% [14%, 69%] | 0% | 2231 / 2267 | – | compile_error 3, missed 2, hit 3 | 1.0 | 5.3 |
| uart/R24 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1826 / 1644 | – | hit 8 | 1.0 | 7.4 |
| uart/R25 | 8 | 75% [41%, 93%] | 75% [41%, 93%] | 0% | 1898 / 1995 | – | compile_error 2, hit 6 | 1.0 | 6.1 |
| uart/R26 | 8 | 38% [14%, 69%] | 38% [14%, 69%] | 0% | 1750 / 1592 | – | missed 5, hit 3 | 1.0 | 7.9 |
| uart/R27 | 8 | 88% [53%, 98%] | 88% [53%, 98%] | 0% | 2240 / 2209 | – | compile_error 1, hit 7 | 1.0 | 8.1 |
| uart/R28 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1504 / 1582 | – | hit 8 | 1.0 | 7.2 |
| uart/R29 | 8 | 25% [7%, 59%] | 25% [7%, 59%] | 0% | 1935 / 2085 | – | compile_error 6, hit 2 | 1.0 | 2.7 |
| uart/T5 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1565 / 1634 | – | hit 8 | 1.0 | 6.7 |
| uart/T6 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1679 / 1604 | – | hit 8 | 1.0 | 6.7 |
| uart/T7 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1663 / 1697 | – | hit 8 | 1.0 | 6.8 |
| uart/T8 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 2108 / 2064 | – | hit 8 | 1.0 | 6.9 |
| uart/T9 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1789 / 1826 | – | hit 8 | 1.0 | 7.0 |
| uart/T10 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1607 / 1570 | – | hit 8 | 1.0 | 6.8 |
| uart/T11 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1967 / 1958 | – | hit 8 | 1.0 | 6.5 |
| uart/T12 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 1943 / 1913 | – | hit 8 | 1.0 | 6.4 |

### G3: qwen/qwen3.8-27b · null · max_tokens=65536

| task | n | pass@1 [Wilson 95%] | untruncated | truncated | out tokens finished (mean / median) | out tokens truncated (mean / median) | outcomes | turns | sim s |
|---|---|---|---|---|---|---|---|---|---|
| uart/R12 | 8 | 75% [41%, 93%] | 75% [41%, 93%] | 0% | 47554 / 44748 | – | compile_error 2, hit 6 | 1.0 | 5.1 |
| uart/R13 | 8 | 62% [31%, 86%] | 62% [31%, 86%] | 0% | 43713 / 44181 | – | compile_error 2, runtime_error 1, hit 5 | 1.0 | 5.2 |
| uart/R14 | 7 (+1) | 71% [36%, 92%] | 83% [44%, 97%] | 14% | 45530 / 45634 | 65536 / 65536 | no_submission 1, missed 1, hit 5 | 1.0 | 6.9 |
| uart/R15 | 8 | 50% [22%, 78%] | 57% [25%, 84%] | 12% | 39096 / 36701 | 65536 / 65536 | no_submission 1, missed 3, hit 4 | 1.0 | 6.9 |
| uart/R16 | 8 | 88% [53%, 98%] | 88% [53%, 98%] | 0% | 38535 / 42266 | – | compile_error 1, hit 7 | 1.0 | 6.4 |
| uart/R17 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 28177 / 28122 | – | hit 8 | 1.0 | 8.3 |
| uart/R18 | 8 | 88% [53%, 98%] | 88% [53%, 98%] | 0% | 29738 / 29694 | – | runtime_error 1, hit 7 | 1.0 | 8.7 |
| uart/R19 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 28334 / 28282 | – | hit 8 | 1.0 | 7.1 |
| uart/R20 | 8 | 62% [31%, 86%] | 62% [31%, 86%] | 0% | 39238 / 40086 | – | compile_error 1, runtime_error 2, hit 5 | 1.0 | 7.2 |
| uart/R21 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 35054 / 33342 | – | hit 8 | 1.0 | 7.6 |
| uart/R22 | 8 | 88% [53%, 98%] | 88% [53%, 98%] | 0% | 42769 / 42127 | – | missed 1, hit 7 | 1.0 | 7.7 |
| uart/R23 | 8 | 75% [41%, 93%] | 75% [41%, 93%] | 0% | 44600 / 44434 | – | compile_error 2, hit 6 | 1.0 | 5.5 |
| uart/R24 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 30979 / 28306 | – | hit 8 | 1.0 | 7.5 |
| uart/R25 | 8 | 50% [22%, 78%] | 50% [22%, 78%] | 0% | 39058 / 42280 | – | compile_error 3, missed 1, hit 4 | 1.0 | 4.6 |
| uart/R26 | 8 | 0% [0%, 32%] | 0% [0%, 39%] | 25% | 28786 / 27157 | 65536 / 65536 | no_submission 2, compile_error 1, runtime_error 1, missed 4 | 1.0 | 5.2 |
| uart/R27 | 8 | 62% [31%, 86%] | 71% [36%, 92%] | 12% | 41274 / 41091 | 65536 / 65536 | no_submission 2, compile_error 1, hit 5 | 1.0 | 4.8 |
| uart/R28 | 8 | 62% [31%, 86%] | 62% [31%, 86%] | 0% | 38203 / 41782 | – | compile_error 1, runtime_error 2, hit 5 | 1.0 | 9.0 |
| uart/R29 | 8 | 62% [31%, 86%] | 62% [31%, 86%] | 0% | 43198 / 46117 | – | compile_error 2, missed 1, hit 5 | 1.0 | 5.3 |
| uart/T5 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 31932 / 30740 | – | hit 8 | 1.0 | 7.5 |
| uart/T6 | 8 | 38% [14%, 69%] | 50% [19%, 81%] | 25% | 45307 / 45343 | 65536 / 65536 | no_submission 2, illegal_stimulus 2, missed 1, hit 3 | 1.0 | 5.8 |
| uart/T7 | 8 | 50% [22%, 78%] | 50% [22%, 78%] | 0% | 38852 / 36384 | – | illegal_stimulus 4, hit 4 | 1.0 | 7.2 |
| uart/T8 | 8 | 100% [68%, 100%] | 100% [68%, 100%] | 0% | 46660 / 44513 | – | hit 8 | 1.0 | 6.6 |
| uart/T9 | 8 | 12% [2%, 47%] | 20% [4%, 62%] | 38% | 38077 / 40469 | 65536 / 65536 | no_submission 3, illegal_stimulus 4, hit 1 | 1.0 | 4.5 |
| uart/T10 | 8 | 38% [14%, 69%] | 38% [14%, 69%] | 0% | 38824 / 35628 | – | illegal_stimulus 5, hit 3 | 1.0 | 7.3 |
| uart/T11 | 8 | 50% [22%, 78%] | 57% [25%, 84%] | 12% | 46008 / 46550 | 65536 / 65536 | no_submission 3, missed 1, hit 4 | 1.0 | 4.0 |
| uart/T12 | 8 | 50% [22%, 78%] | 80% [38%, 96%] | 38% | 43469 / 40970 | 65536 / 65536 | no_submission 4, hit 4 | 1.0 | 4.1 |

