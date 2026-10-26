# Calibration

Target band for mean pass@1 across tasks: [30%, 60%]. Set interval: task bootstrap 95% (2000 resamples, seed 0). Per task: Beta prior fitted to all tasks of the group (beta-binomial maximum likelihood, strength a + b capped at the median rollouts per task so the prior never outweighs a task's own data), posterior mean and 80% equal-tailed interval. too_easy: P(p > 0.9) > 0.8; too_hard: P(p < 0.05) > 0.8; in_band: P(0.2 < p < 0.8) > 0.6; else unclear.

## nvidia/nemotron-3-nano-30b-a3b · null · max_tokens=65536

Set: mean pass@1 8% [2%, 14%] -> **below**. Prior Beta(0.213, 2.64). too_easy 0, too_hard 19, in_band 2, unclear 5.

| task | hits/n | posterior mean | 80% interval | P(p>0.9) | P(p<0.05) | P(0.2<p<0.8) | class |
|---|---|---|---|---|---|---|---|
| uart/R12 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R13 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R14 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R15 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R16 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R17 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R18 | 2/8 | 0.20 | [0.07, 0.37] | 0.00 | 0.06 | 0.45 | unclear |
| uart/R19 | 2/8 | 0.20 | [0.07, 0.37] | 0.00 | 0.06 | 0.45 | unclear |
| uart/R20 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R21 | 1/8 | 0.11 | [0.02, 0.24] | 0.00 | 0.30 | 0.16 | unclear |
| uart/R22 | 3/8 | 0.30 | [0.13, 0.48] | 0.00 | 0.01 | 0.74 | in_band |
| uart/R23 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R24 | 5/8 | 0.48 | [0.29, 0.67] | 0.00 | 0.00 | 0.97 | in_band |
| uart/R25 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R26 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R27 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R28 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/R29 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T5 | 2/8 | 0.20 | [0.07, 0.37] | 0.00 | 0.06 | 0.45 | unclear |
| uart/T6 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T7 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T8 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T9 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T10 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |
| uart/T11 | 1/8 | 0.11 | [0.02, 0.24] | 0.00 | 0.30 | 0.16 | unclear |
| uart/T12 | 0/8 | 0.02 | [0.00, 0.06] | 0.00 | 0.88 | 0.01 | too_hard |

Unclear (5), +2 rollouts each: uart/R18, uart/R19, uart/R21, uart/T5, uart/T11

```bash
vf-eval @ outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/configs/eval.toml -m nvidia/nemotron-3-nano-30b-a3b --sampling.max_tokens 65536 --select.include.ids uart/R18 uart/R19 uart/R21 uart/T5 uart/T11 -r 2 -o outputs/official/nemotron
```

## openai/gpt-6-sol · null · max_tokens=65536

Set: mean pass@1 84% [74%, 94%] -> **above**. Prior Beta(0.953, 0.164). too_easy 17, too_hard 0, in_band 4, unclear 5.

| task | hits/n | posterior mean | 80% interval | P(p>0.9) | P(p<0.05) | P(0.2<p<0.8) | class |
|---|---|---|---|---|---|---|---|
| uart/R12 | 6/8 | 0.76 | [0.58, 0.92] | 0.15 | 0.00 | 0.55 | unclear |
| uart/R13 | 1/8 | 0.21 | [0.06, 0.39] | 0.00 | 0.06 | 0.48 | unclear |
| uart/R14 | 4/8 | 0.54 | [0.33, 0.75] | 0.00 | 0.00 | 0.94 | in_band |
| uart/R15 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R16 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R17 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R18 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R19 | 7/8 | 0.87 | [0.73, 0.98] | 0.50 | 0.00 | 0.21 | unclear |
| uart/R20 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R21 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R22 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R23 | 3/8 | 0.43 | [0.23, 0.64] | 0.00 | 0.00 | 0.93 | in_band |
| uart/R24 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R25 | 6/8 | 0.76 | [0.58, 0.92] | 0.15 | 0.00 | 0.55 | unclear |
| uart/R26 | 3/8 | 0.43 | [0.23, 0.64] | 0.00 | 0.00 | 0.93 | in_band |
| uart/R27 | 7/8 | 0.87 | [0.73, 0.98] | 0.50 | 0.00 | 0.21 | unclear |
| uart/R28 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/R29 | 2/8 | 0.32 | [0.14, 0.53] | 0.00 | 0.01 | 0.78 | in_band |
| uart/T5 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T6 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T7 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T8 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T9 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T10 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T11 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |
| uart/T12 | 8/8 | 0.98 | [0.94, 1.00] | 0.95 | 0.00 | 0.01 | too_easy |

Unclear (5), +2 rollouts each: uart/R12, uart/R13, uart/R19, uart/R25, uart/R27

```bash
vf-eval @ outputs/official/gpt-6-sol/closure-bench--openai--gpt-6-sol--null--2fc9e854/configs/eval.toml -m openai/gpt-6-sol --sampling.max_tokens 65536 --select.include.ids uart/R12 uart/R13 uart/R19 uart/R25 uart/R27 -r 2 -o outputs/official/gpt-6-sol
```

## qwen/qwen3.8-27b · null · max_tokens=65536

Set: mean pass@1 67% [56%, 77%] -> **overlaps**. Prior Beta(2, 0.997). too_easy 0, too_hard 0, in_band 16, unclear 10.

| task | hits/n | posterior mean | 80% interval | P(p>0.9) | P(p<0.05) | P(0.2<p<0.8) | class |
|---|---|---|---|---|---|---|---|
| uart/R12 | 6/8 | 0.73 | [0.55, 0.88] | 0.07 | 0.00 | 0.68 | in_band |
| uart/R13 | 5/8 | 0.64 | [0.45, 0.81] | 0.01 | 0.00 | 0.88 | in_band |
| uart/R14 | 5/7 | 0.70 | [0.51, 0.87] | 0.05 | 0.00 | 0.74 | in_band |
| uart/R15 | 4/8 | 0.55 | [0.35, 0.73] | 0.00 | 0.00 | 0.96 | in_band |
| uart/R16 | 7/8 | 0.82 | [0.66, 0.95] | 0.26 | 0.00 | 0.37 | unclear |
| uart/R17 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/R18 | 7/8 | 0.82 | [0.66, 0.95] | 0.26 | 0.00 | 0.37 | unclear |
| uart/R19 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/R20 | 5/8 | 0.64 | [0.45, 0.81] | 0.01 | 0.00 | 0.88 | in_band |
| uart/R21 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/R22 | 7/8 | 0.82 | [0.66, 0.95] | 0.26 | 0.00 | 0.37 | unclear |
| uart/R23 | 6/8 | 0.73 | [0.55, 0.88] | 0.07 | 0.00 | 0.68 | in_band |
| uart/R24 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/R25 | 4/8 | 0.55 | [0.35, 0.73] | 0.00 | 0.00 | 0.96 | in_band |
| uart/R26 | 0/8 | 0.18 | [0.05, 0.34] | 0.00 | 0.09 | 0.38 | unclear |
| uart/R27 | 5/8 | 0.64 | [0.45, 0.81] | 0.01 | 0.00 | 0.88 | in_band |
| uart/R28 | 5/8 | 0.64 | [0.45, 0.81] | 0.01 | 0.00 | 0.88 | in_band |
| uart/R29 | 5/8 | 0.64 | [0.45, 0.81] | 0.01 | 0.00 | 0.88 | in_band |
| uart/T5 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/T6 | 3/8 | 0.45 | [0.27, 0.65] | 0.00 | 0.00 | 0.96 | in_band |
| uart/T7 | 4/8 | 0.55 | [0.35, 0.73] | 0.00 | 0.00 | 0.96 | in_band |
| uart/T8 | 8/8 | 0.91 | [0.79, 0.99] | 0.65 | 0.00 | 0.11 | unclear |
| uart/T9 | 1/8 | 0.27 | [0.12, 0.45] | 0.00 | 0.01 | 0.68 | in_band |
| uart/T10 | 3/8 | 0.45 | [0.27, 0.65] | 0.00 | 0.00 | 0.96 | in_band |
| uart/T11 | 4/8 | 0.55 | [0.35, 0.73] | 0.00 | 0.00 | 0.96 | in_band |
| uart/T12 | 4/8 | 0.55 | [0.35, 0.73] | 0.00 | 0.00 | 0.96 | in_band |

Unclear (10), +2 rollouts each: uart/R16, uart/R17, uart/R18, uart/R19, uart/R21, uart/R22, uart/R24, uart/R26, uart/T5, uart/T8

```bash
vf-eval @ outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/configs/eval.toml -m qwen/qwen3.8-27b --sampling.max_tokens 65536 --select.include.ids uart/R16 uart/R17 uart/R18 uart/R19 uart/R21 uart/R22 uart/R24 uart/R26 uart/T5 uart/T8 -r 2 -o outputs/official/qwen
```

