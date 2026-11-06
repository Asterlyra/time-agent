### 4.6 Results

All 432 planned episodes are accounted for. 426 produced a scored result and 6 are archived host-suspend failures, retained with a zero score and flagged separately; they are included in every denominator and never interpreted as model behaviour. Table 3 gives the items banked before the deadline, averaged over the twelve task instances.

**Table 3. Study 2, mean items collected (maximum 20), n = 12 per cell.**

| Profile | Model | A | B | C | O |
|---|---|---:|---:|---:|---:|
| constant 8 s | GLM | 13.5 | 12.8 | 9.8 | 12.8 |
| constant 8 s | Qwen | 1.3 | 1.9 | 1.5 | 1.8 |
| constant 8 s | DeepSeek | 7.1 | 7.4 | 9.3 | 9.3 |
| step 8→60 s | GLM | 3.2 | 3.8 | 5.2 | 4.2 |
| step 8→60 s | Qwen | 2.0 | 1.7 | 2.5 | 2.0 |
| step 8→60 s | DeepSeek | 3.2 | 3.8 | 4.0 | 4.2 |
| drift 8→60 s | GLM | 7.5 | 7.0 | 7.3 | 7.2 |
| drift 8→60 s | Qwen | 2.2 | 1.8 | 1.7 | 2.4 |
| drift 8→60 s | DeepSeek | 6.2 | 5.7 | 4.3 | 4.9 |

**Primary contrast.** In the drift profile — the one profile in which the most recent observation is systematically stale — the equal-weight C−B difference was -0.36 items, 95% cluster-bootstrap CI [-1.1, +0.4], sign-flip p = 0.442 over 12 paired blocks. Per model: GLM +0.3, Qwen -0.1, DeepSeek -1.3.

**All pre-registered contrasts.** Of the 9 contrasts in Table 4, 1 has a 95% interval excluding zero. The largest point estimate is C-A in the drift 8→60 s profile at -0.9 items, CI [-1.6, -0.0]. In the control profile, where all four conditions display the same number, the C−B estimate is -0.5 items.

**Table 4. Study 2, paired contrasts in items (95% cluster bootstrap CI).**

| Profile | Contrast | Pooled | 95% CI | p | GLM | Qwen | DeepSeek |
|---|---|---:|---|---:|---:|---:|---:|
| drift 8→60 s | C-B | -0.4 | [-1.1, +0.4] | 0.442 | +0.3 | -0.1 | -1.3 |
| drift 8→60 s | B-A | -0.5 | [-1.3, +0.3] | 0.303 | -0.5 | -0.5 | -0.5 |
| drift 8→60 s | C-A | -0.9 | [-1.6, -0.0] | 0.078 | -0.2 | -0.6 | -1.8 |
| drift 8→60 s | O-C | +0.4 | [-0.4, +1.2] | 0.425 | -0.2 | +0.8 | +0.6 |
| drift 8→60 s | O-B | +0.0 | [-1.0, +1.0] | 0.983 | +0.2 | +0.7 | -0.8 |
| step 8→60 s | C-B | +0.8 | [-0.3, +2.0] | 0.224 | +1.4 | +0.8 | +0.2 |
| step 8→60 s | B-A | +0.3 | [-0.8, +1.4] | 0.560 | +0.6 | -0.3 | +0.7 |
| step 8→60 s | O-C | -0.5 | [-1.5, +0.5] | 0.424 | -1.1 | -0.5 | +0.2 |
| constant 8 s | C-B | -0.5 | [-2.0, +0.9] | 0.523 | -3.0 | -0.4 | +1.9 |

**The manipulation changed what the agents were told.** In the drift profile the mean absolute error between the displayed reference and the delay actually applied was 8.0 s in condition B, 3.6 s in C and 1.5 s in O (Figure 5a). B's reference stayed at 8.0 s for the whole episode while the true cost rose to 60 s; C's tracked the truth with roughly one call of lag; O coincided with it.

**It did not change what they did.** The fitted stopping threshold — the remaining budget at which the probability of starting another fetch crosses one half — was 56.8 s in A, 54.9 s in B, 57.9 s in C and 62.0 s in O (Table 5). The four curves in Figure 5b lie on top of one another: the decision to continue is a function of the remaining budget, not of the estimate the model was handed.

**Table 5. Study 2, stopping behaviour.**

| Profile | Cond | submitted | threshold (s) | mean reference (s) | mean fetches | regret (items) |
|---|---|---:|---:|---:|---:|---:|
| constant 8 s | A | 0.75 | 8.1 | — | 8.2 | 0.78 |
| constant 8 s | B | 0.78 | 7.1 | 8.0 | 8.8 | 1.42 |
| constant 8 s | C | 0.75 | 15.1 | 8.0 | 8.3 | 1.42 |
| constant 8 s | O | 0.78 | 13.3 | 8.0 | 8.9 | 0.97 |
| step 8→60 s | A | 0.69 | 68.6 | — | 4.4 | 1.56 |
| step 8→60 s | B | 0.69 | 68.7 | 8.0 | 4.5 | 1.36 |
| step 8→60 s | C | 0.89 | 84.2 | 18.1 | 4.4 | 0.39 |
| step 8→60 s | O | 0.81 | 84.7 | 23.1 | 4.4 | 0.81 |
| drift 8→60 s | A | 0.94 | 56.8 | — | 5.7 | 0.31 |
| drift 8→60 s | B | 0.86 | 54.9 | 8.0 | 5.5 | 0.67 |
| drift 8→60 s | C | 0.78 | 57.9 | 14.4 | 5.5 | 1.03 |
| drift 8→60 s | O | 0.86 | 62.0 | 18.0 | 5.5 | 0.67 |

**Where the items go.** The submission rate ranges from 0.69 to 0.94 across the twelve profile–condition cells, and the mean regret of continuing — the gap between what the episode scored and what stopping at the best earlier request would have banked — ranges from 0.31 to 1.56 items. Episodes are lost by over-running the deadline, not by mis-estimating the tool.

**Table 6. Simulated rational planner versus the observed agents, drift profile.**

| Model | planner B | planner C | planner O | observed A | observed B | observed C | observed O |
|---|---:|---:|---:|---:|---:|---:|---:|
| GLM | 2.2 | 5.8 | 7.2 | 7.5 | 7.0 | 7.3 | 7.2 |
| Qwen | 2.0 | 2.8 | 3.2 | 2.2 | 1.8 | 1.7 | 2.4 |
| DeepSeek | 2.3 | 5.0 | 6.0 | 6.2 | 5.7 | 4.3 | 4.9 |

**Which belief did the agent act on?** The three planners differ only in what they believe about the next call, and they are ordered as expected: a planner holding the stale prior collects 2.0–2.3 items, one holding the last-observation estimate 2.8–5.8, and one holding the oracle 3.2–7.2. The agents do not follow that order. Within a model, the difference between the stale-prior and oracle conditions is at most 0.8 items for the agents (0.2, 0.7, 0.8) against 1.2–4.9 items for the planners. Every observed condition lies within 1.7 items of the reaction-based planner, and in the oracle condition the agents are within 1.1 items of the planner that holds the same information. The interface changed the estimate the agent was told to hold; it did not change the estimate the agent acted on, which is the one it reads off the clock.

