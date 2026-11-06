### 5.4 Results

All 7,040 planned episodes produced a record. 2,283 of those records are provider refusals: the account moved to balance billing partway through collection, and the request was rejected before the model ran, so they are excluded rather than scored zero — they contain no behaviour to score. The analysis rests on the 4,757 observable episodes, with the 8 host interruptions kept at zero and flagged. Their share is flat across arms (32% in every arm), so the paired contrast is unaffected. Table 7 gives the points banked by family, regime and arm.

Every one of the 64 (task, regime) cells now has all five arms observed, so the paired contrast uses the whole design; the refusals cost completeness while they lasted, not arm balance.

**Table 7. Study 3, mean points banked (maximum 5 × number of items).**

| Family | Regime | I0 | I1 | C | E | O |
|---|---|---:|---:|---:|---:|---:|
| uniform | light tail | 3.1 | 2.7 | 5.9 | 6.3 | 6.1 |
| uniform | fast, heavy tail | 3.2 | 3.4 | 6.3 | 6.5 | 6.3 |
| uniform | slow, heavy tail | 1.3 | 1.5 | 2.5 | 2.4 | 2.6 |
| uniform | drifting, heavy tail | 2.2 | 2.8 | 4.0 | 4.1 | 4.3 |
| hetero | light tail | 12.9 | 9.9 | 19.9 | 20.8 | 20.1 |
| hetero | fast, heavy tail | 14.4 | 13.1 | 19.7 | 20.9 | 21.1 |
| hetero | slow, heavy tail | 10.3 | 7.0 | 15.6 | 14.0 | 15.6 |
| hetero | drifting, heavy tail | 11.6 | 8.9 | 15.2 | 17.7 | 19.2 |

![Points banked by arm](figures/fig6_s3_arms.png)

**Figure 6.** Study 3, points banked by arm, in the uniform and heterogeneous families; bars are means with 95% normal-approximation intervals over episodes.

**Primary contrast.** In the heterogeneous family, the equal-weight E−I0 difference was +6.10 points, 95% cluster-bootstrap CI [+5.20, +6.98], sign-flip p = 0.000 over 16 paired blocks. Per model: GLM -0.31, Qwen +5.27, DeepSeek +9.22, MiMo +10.23.

**Table 8. Study 3, pre-registered contrasts (points, 95% cluster bootstrap CI).**

| Family | Contrast | Pooled | 95% CI | p | GLM | Qwen | DeepSeek | MiMo |
|---|---|---:|---|---:|---:|---:|---:|---:|
| uniform | E−I0 | +2.37 | [+1.82, +2.85] | 0.000 | +1.80 | +1.08 | +3.63 | +2.97 |
| uniform | I1−I0 | -0.07 | [-0.49, +0.35] | 0.781 | -0.10 | +0.00 | -0.07 | -0.09 |
| uniform | C−I0 | +2.25 | [+1.62, +2.85] | 0.000 | +1.37 | +0.96 | +3.01 | +3.66 |
| uniform | C−E | -0.12 | [-0.47, +0.23] | 0.525 | -0.43 | -0.12 | -0.62 | +0.69 |
| uniform | E−O | -0.10 | [-0.40, +0.24] | 0.587 | -0.24 | -0.01 | -0.28 | +0.16 |
| hetero | E−I0 | +6.10 | [+5.20, +6.98] | 0.000 | -0.31 | +5.27 | +9.22 | +10.23 |
| hetero | I1−I0 | -2.94 | [-3.85, -1.94] | 0.001 | -5.86 | -0.07 | -2.48 | -3.35 |
| hetero | C−I0 | +5.52 | [+4.29, +6.85] | 0.000 | +0.60 | +3.41 | +7.39 | +10.67 |
| hetero | C−E | -0.58 | [-1.88, +0.67] | 0.403 | +0.91 | -1.86 | -1.82 | +0.44 |
| hetero | E−O | -0.64 | [-1.57, +0.36] | 0.227 | -1.68 | +0.07 | -2.04 | +1.07 |

**Table 9. Study 3, why episodes end.**

| Family | Arm | submitted | forced | mean banked items | mean denied fetches |
|---|---|---:|---:|---:|---:|
| uniform | I0 | 0.38 | 0.00 | 2.5 | 0.0 |
| uniform | I1 | 0.36 | 0.00 | 2.6 | 0.0 |
| uniform | C | 0.79 | 0.72 | 4.8 | 1.2 |
| uniform | E | 0.92 | 0.89 | 4.9 | 0.3 |
| uniform | O | 0.93 | 0.89 | 4.9 | 0.3 |
| hetero | I0 | 0.44 | 0.00 | 3.0 | 0.0 |
| hetero | I1 | 0.35 | 0.00 | 2.4 | 0.0 |
| hetero | C | 0.76 | 0.69 | 4.1 | 1.2 |
| hetero | E | 0.91 | 0.87 | 4.3 | 0.3 |
| hetero | O | 0.92 | 0.85 | 4.5 | 0.5 |

**Enforcement, not information.** A reserve the harness computes and enforces beat the unguarded baseline by +6.10 points [+5.20, +6.98] (Figure 6; Table 8 collects every pre-registered contrast). A reserve the *agent* declared, then mechanically enforced by the same code, did just as well (+5.52, [+4.29, +6.85]); the difference between the two is -0.58 [-1.88, +0.67]: indistinguishable. What separates both from the informational arms is therefore not who chooses the number but whether anything acts on it. Even a perfect cost model buys little once the reserve is enforced: O trails E by -0.64 [-1.57, +0.36]. The mechanism is visible in how episodes end (Figure 7): in `I0` and `I1` most failures are episodes still waiting on a call when the budget ran out, while under `C`, `E` and `O` the harness submits whatever is in hand before the deadline.

![How episodes end](figures/fig7_s3_termination.png)

**Figure 7.** Study 3, how episodes end in the heterogeneous family. `I0` and `I1` mostly die inside a call or a request; under `C`, `E` and `O` the harness submits whatever is in hand before the budget expires.

**Information without a rule.** Giving the agent the numbers does not do this. Full information made the score worse (I1−I0 = -2.94 [-3.85, -1.94]). The arm displayed the per-size cost estimates and the agent's own median request latency — a number the model cannot observe directly — and the agents went on making almost exactly the same calls: in the heterogeneous family I0 and I1 make 3.6 and 3.6 calls and fetch 3.5 and 3.5 items on average, so the policy did not change what the agent did, only how often the doing was cut off. What changed was the ending, not the calls: the share of episodes that ended in a submission fell from 44% to 35%, and the points fell with it. The obvious explanation is that the extra text makes each request slower; it does not. Request p50 is 11.2 s in `I0` and 10.9 s in `I1`, and request durations by step index are indistinguishable. We report the cost without claiming its mechanism. This is the Study 2 finding again — the declared estimate improved while the operative one did not — now with stochastic costs and differing item values.

**The decision itself.** Figure 8 reads the moment a call is started off every episode. If the informational arm changed what the agent does, its calls would sit further from the deadline than the unguarded arm's. They do not: the median call in `I1` starts with 125.5 s left, against 125.8 s in `I0`, and the two arms make 3.64 and 3.55 calls per episode. Measured against the model's own request distribution, the share of calls started on a budget too short to pay for a typical slow request is 3.0% in `I1` and 2.6% in `I0` — the number arrives and changes neither the count nor the timing of the decisions. Under enforcement the same decisions are made and then refused before it can kill the episode: 0.0% of `E` calls start on such a budget, because a call the reserve cannot pay for is never admitted. The gain is not a change in judgement but a change in what is allowed to reach execution.

![Where calls are started](figures/fig8_s3_decisions.png)

**Figure 8.** Where in the budget a call is started, heterogeneous family. (a) The informational arm `I1` against the unguarded baseline `I0`: the same distribution, bin for bin. (b) The same baseline against the enforced reserve `E`, which never starts a call in the shaded last 30 s.

**Regime dependence, and a control that failed.** Across the three stochastic regimes the enforcement gain was fast +6.62 [+3.80, +9.39], slow +4.32 [+3.28, +5.30] and drifting +6.12 [+3.71, +8.52]; in the near-deterministic `light_tail` control, where a reserve against tool-cost variance would have nothing to protect, it was +7.68 [+5.98, +9.41] — the largest of the four, so the pre-registered negative control does not behave as a control. That is informative rather than merely inconvenient: it rules out the reading that enforcement helps by absorbing the variance of tool durations, and locates the variance it does absorb on the request side, where the agent pays for its own inference.

![Enforcement by regime](figures/fig9_s3_regime.png)

**Figure 9.** Study 3, the E−I0 difference by tool-cost regime, uniform and heterogeneous families. The gain is not smaller where call durations are nearly deterministic.

### 5.5 Who benefits from enforcement

Enforcement is not uniformly useful. Table 10 splits the heterogeneous family by model, together with two things read straight from the episodes: the distribution of time the model itself takes between tool calls, and how many items an unguarded episode had already fetched when the deadline killed it.

**Table 10. Study 3, enforcement benefit by model (heterogeneous family).**

| Model | request p50 (s) | request p90 (s) | unguarded deaths | items in hand at death | I0 banked | E banked | E−I0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GLM | 7.2 | 14.0 | 7% | 8.2 | 24.6 | 24.5 | -0.31 |
| Qwen | 19.3 | 58.1 | 88% | 1.4 | 0.5 | 5.7 | +5.27 |
| DeepSeek | 8.1 | 20.4 | 18% | 6.4 | 16.8 | 25.1 | +9.22 |
| MiMo | 14.2 | 30.0 | 35% | 5.3 | 6.9 | 17.8 | +10.23 |

The two ends fail for opposite reasons. GLM's median request takes 7.2 s, its deadline death rate is 7%, and enforcement adds -0.31: there is nothing to protect. Qwen is the opposite — 19.3 s per request, 88% of unguarded episodes die — yet it gains only +5.27, because a dying episode had fetched just 1.4 items. Enforcement converts work already done into points; where the model never gets far enough for that work to exist, the harness has nothing to save. The largest gains sit in between, at MiMo (+10.23, 5.3 items in hand at death), and the ordering is driven by the shapedness of the request distribution rather than by its median: a fast median with a heavy tail is protected as reliably as uniformly slow requests. This is the tail that the `light_tail` control isolates, and it belongs to the model, not to the tool.

### 5.6 What the points were made of

Points are credited at submission. A collection that is never handed in counts for nothing, so the same work can be worth 22 points or zero depending only on whether someone called stop. Table 11 opens the score into the work collected, the share of it forfeited, and the price per point.

**Table 11. Study 3, collected work, forfeited work and cost (heterogeneous and uniform families).**

| Family | Arm | Banked | of ceiling | Collected | Forfeited share | Submitted | Median slack (s) | mUSD/point | All-zero cells |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Heterogeneous | I0 | 12.31 | 0.26 | 21.5 | 0.55 | 0.45 | 9 | 0.33 | 0.36 |
| Heterogeneous | I1 | 9.70 | 0.20 | 21.4 | 0.64 | 0.35 | 8 | 0.44 | 0.44 |
| Heterogeneous | C | 17.52 | 0.36 | 21.2 | 0.22 | 0.76 | 19 | 0.22 | 0.10 |
| Heterogeneous | E | 18.31 | 0.38 | 20.4 | 0.09 | 0.91 | 40 | 0.18 | 0.01 |
| Heterogeneous | O | 19.00 | 0.39 | 20.5 | 0.08 | 0.92 | 36 | 0.18 | 0.01 |
| Uniform | I0 | 2.47 | 0.15 | 4.9 | 0.62 | 0.38 | 8 | 1.48 | 0.43 |
| Uniform | I1 | 2.64 | 0.16 | 5.3 | 0.63 | 0.37 | 7 | 1.44 | 0.46 |
| Uniform | C | 4.77 | 0.29 | 5.5 | 0.19 | 0.80 | 21 | 0.68 | 0.07 |
| Uniform | E | 4.91 | 0.30 | 5.3 | 0.08 | 0.92 | 37 | 0.53 | 0.01 |
| Uniform | O | 4.93 | 0.31 | 5.2 | 0.07 | 0.93 | 38 | 0.53 | 0.01 |

The five arms collect almost exactly the same amount of work: 20.4 to 21.5 points per episode in the heterogeneous family, and 4.9 to 5.5 in the uniform one. What differs is the share of that work that is handed in: 64% of it is forfeited under I1 and 55% under I0, against 8% under O. Enforcement does not make the agent search better; it stops the search from being thrown away, which is why changing what the agent is told moves the score by little or nothing while changing who may stop moves it by several points in every regime.

Unfinished work is also the expensive kind. A wasted episode is billed in full, so the cost per banked point runs at 0.33 milli-USD under I0 and 0.18 under E (about 1.9× more expensive when nobody enforces anything, Table 11). Reliability moves the same way: 36% of I0 cells never score at all, against 1% of O cells, so enforcement buys a floor as well as a mean.

