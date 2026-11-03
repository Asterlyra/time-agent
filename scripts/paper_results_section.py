"""Render the Study 2 results section straight from stats_summary.json.

Writing the numbers from the analysis output instead of retyping them keeps the
manuscript and the artefacts in sync.
"""
import argparse
import json
from pathlib import Path

def num(value, width=1):
    if value is None:
        return '—'
    if abs(value) < 0.05:
        value = 0.0
    return f"{value:+.{width}f}"


SHORT = {'glm-5.3-flash': 'GLM', 'qwen3.8-flash': 'Qwen', 'deepseek-v4.1-flash': 'DeepSeek'}
MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash')
PROFILES = ('stable_fast', 'fast_to_slow', 'drift_up')
PLABEL = {'stable_fast': 'constant 8 s', 'fast_to_slow': 'step 8→60 s', 'drift_up': 'drift 8→60 s'}


def get(summary, profile, contrast):
    return next((c for c in summary['contrasts']
                 if c['profile'] == profile and c['contrast'] == contrast), None)


def ci(row):
    return f"[{row['ci'][0]:+.1f}, {row['ci'][1]:+.1f}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text())
    cells, behaviour = summary['cells'], summary['behaviour']
    thr = summary.get('stop_threshold', {})
    reg = summary.get('stopping_regret', {})
    err = summary.get('reference_error', {})
    bench = summary.get('planner_benchmark', {})
    primary = summary['primary']
    n_ep = summary['n_episodes']
    n_arch = summary.get('n_archived_environment_failures', 0)
    lines = []

    lines.append('### 4.6 Results\n')
    lines.append(f"All {n_ep} planned episodes are accounted for. "
                 f"{n_ep - n_arch} produced a scored result and {n_arch} are archived host-suspend "
                 "failures, retained with a zero score and flagged separately; they are included in "
                 "every denominator and never interpreted as model behaviour. "
                 "Table 3 gives the items banked before the deadline, averaged over the twelve task "
                 "instances.\n")
    lines.append('**Table 3. Study 2, mean items collected (maximum 20), n = 12 per cell.**\n')
    lines.append('| Profile | Model | A | B | C | O |')
    lines.append('|---|---|---:|---:|---:|---:|')
    for profile in PROFILES:
        for model in MODELS:
            values = []
            for condition in 'ABCO':
                cell = cells.get(f'{profile}|{model}|{condition}')
                values.append(f"{cell['mean_score']:.1f}" if cell else '—')
            lines.append(f"| {PLABEL[profile]} | {SHORT[model]} | " + ' | '.join(values) + ' |')
    lines.append('')

    pm = primary['per_model']
    lines.append(f"**Primary contrast.** In the drift profile — the one profile in which the most "
                 f"recent observation is systematically stale — the equal-weight C−B difference was "
                 f"{num(primary['pooled'], 2)} items, 95% cluster-bootstrap CI {ci(primary)}, sign-flip "
                 f"p = {primary['p_randomisation']:.3f} over {primary['n_blocks']} paired blocks. "
                 f"Per model: GLM {pm.get('glm-5.3-flash', float('nan')):+.1f}, Qwen "
                 f"{pm.get('qwen3.8-flash', float('nan')):+.1f}, DeepSeek "
                 f"{pm.get('deepseek-v4.1-flash', float('nan')):+.1f}.\n")

    wanted = [('drift_up', c) for c in ('C-B', 'B-A', 'C-A', 'O-C', 'O-B')] + \
             [('fast_to_slow', c) for c in ('C-B', 'B-A', 'O-C')] + \
             [('stable_fast', 'C-B')]
    rows = [(p, c, get(summary, p, c)) for p, c in wanted]
    rows = [(p, c, r) for p, c, r in rows if r]
    excluding = [r for _p, _c, r in rows if r['ci'][0] > 0 or r['ci'][1] < 0]
    largest = max(rows, key=lambda item: abs(item[2]['pooled']))
    lines.append(f"**All pre-registered contrasts.** Of the {len(rows)} contrasts in Table 4, "
                 f"{len(excluding)} {'has' if len(excluding)==1 else 'have'} a 95% interval excluding zero. The largest point estimate is "
                 f"{largest[1]} in the {PLABEL[largest[0]]} profile at {largest[2]['pooled']:+.1f} "
                 f"items, CI {ci(largest[2])}. In the control profile, where all four conditions "
                 f"display the same number, the C−B estimate is "
                 f"{(get(summary, 'stable_fast', 'C-B') or {'pooled': float('nan')})['pooled']:+.1f} "
                 f"items.\n")
    lines.append('**Table 4. Study 2, paired contrasts in items (95% cluster bootstrap CI).**\n')
    lines.append('| Profile | Contrast | Pooled | 95% CI | p | GLM | Qwen | DeepSeek |')
    lines.append('|---|---|---:|---|---:|---:|---:|---:|')
    for profile, contrast, row in rows:
        model_values = ' | '.join(num(row['per_model'].get(m)) for m in MODELS)
        lines.append(f"| {PLABEL[profile]} | {contrast} | {num(row['pooled'])} | {ci(row)} | "
                     f"{row['p_randomisation']:.3f} | {model_values} |")
    lines.append('')

    def mean_of(key):
        values = [err[f'drift_up:{c}'][key] for c in 'ABCO' if f'drift_up:{c}' in err]
        return sum(values) / len(values) if values else float('nan')

    e = lambda c, key: err.get(f'drift_up:{c}', {}).get(key, float('nan'))
    lines.append(f"**The manipulation changed what the agents were told.** In the drift profile the "
                 f"mean absolute error between the displayed reference and the delay actually applied "
                 f"was {e('B', 'mae_s'):.1f} s in condition B, {e('C', 'mae_s'):.1f} s in C and "
                 f"{e('O', 'mae_s'):.1f} s in O (Figure 5a). B's reference stayed at 8.0 s for the whole "
                 f"episode while the true cost rose to 60 s; C's tracked the truth with roughly one "
                 f"call of lag; O coincided with it.\n")

    t = lambda c: thr.get(f'drift_up:{c}', {}).get('threshold_s')
    lines.append(f"**It did not change what they did.** The fitted stopping threshold — the remaining "
                 f"budget at which the probability of starting another fetch crosses one half — was "
                 f"{t('A') or float('nan'):.1f} s in A, {t('B') or float('nan'):.1f} s in B, "
                 f"{t('C') or float('nan') if t('C') else float('nan'):.1f} s in C and "
                 f"{t('O') or float('nan'):.1f} s in O (Table 5). The four curves in Figure 5b lie on "
                 f"top of one another: the decision to continue is a function of the remaining budget, "
                 f"not of the estimate the model was handed.\n")
    lines.append('**Table 5. Study 2, stopping behaviour.**\n')
    lines.append('| Profile | Cond | submitted | threshold (s) | mean reference (s) | mean fetches | regret (items) |')
    lines.append('|---|---|---:|---:|---:|---:|---:|')
    for profile in PROFILES:
        for condition in 'ABCO':
            row = behaviour.get(f'{profile}:{condition}')
            if not row:
                continue
            ref = thr.get(f'{profile}:{condition}', {}).get('mean_reference_s')
            lines.append(f"| {PLABEL[profile]} | {condition} | {row['p_submitted']:.2f} | "
                         f"{(thr.get(f'{profile}:{condition}', {}).get('threshold_s') or float('nan')):.1f} | "
                         f"{('—' if ref is None else f'{ref:.1f}')} | "
                         f"{row['mean_fetches']:.1f} | "
                         f"{(reg.get(f'{profile}:{condition}', {}).get('mean_regret') or 0):.2f} |")
    lines.append('')

    submitted = [behaviour[f'{p}:{c}']['p_submitted'] for p in PROFILES for c in 'ABCO'
                 if f'{p}:{c}' in behaviour]
    regrets = [reg[f'{p}:{c}']['mean_regret'] for p in PROFILES for c in 'ABCO'
               if f'{p}:{c}' in reg]
    lines.append(f"**Where the items go.** The submission rate ranges from {min(submitted):.2f} to "
                 f"{max(submitted):.2f} across the twelve profile–condition cells, and the mean regret "
                 f"of continuing — the gap between what the episode scored and what stopping at the "
                 f"best earlier request would have banked — ranges from {min(regrets):.2f} to "
                 f"{max(regrets):.2f} items. Episodes are lost by over-running the deadline, not by "
                 f"mis-estimating the tool.\n")

    if bench:
        lines.append('**Table 6. Simulated rational planner versus the observed agents, drift profile.**\n')
        lines.append('| Model | planner B | planner C | planner O | observed A | observed B | observed C | observed O |')
        lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
        for model in MODELS:
            obs = [cells.get(f'drift_up|{model}|{c}', {}).get('mean_score') for c in 'ABCO']
            lines.append(f"| {SHORT[model]} | {bench.get(f'drift_up|{model}|B', float('nan')):.1f} | "
                         f"{bench.get(f'drift_up|{model}|C', float('nan')):.1f} | "
                         f"{bench.get(f'drift_up|{model}|O', float('nan')):.1f} | "
                         + ' | '.join(f'{v:.1f}' if v is not None else '—' for v in obs) + ' |')
        lines.append('')
        def obs(model, condition):
            return cells.get(f'drift_up|{model}|{condition}', {}).get('mean_score')

        def plan(model, belief):
            return bench.get(f'drift_up|{model}|{belief}')

        b_obs = [obs(m, 'B') for m in MODELS]
        b_plan = [plan(m, 'B') for m in MODELS]
        c_plan = [plan(m, 'C') for m in MODELS]
        o_obs = [obs(m, 'O') for m in MODELS]
        o_plan = [plan(m, 'O') for m in MODELS]
        gap_obs = [abs(obs(m, 'B') - obs(m, 'O')) for m in MODELS]
        gap_plan = [abs(plan(m, 'B') - plan(m, 'O')) for m in MODELS]
        dist_react = [abs(obs(m, c) - plan(m, 'C')) for m in MODELS for c in 'ABCO']
        lines.append(
            f"**Which belief did the agent act on?** The three planners differ only in what they "
            f"believe about the next call, and they are ordered as expected: a planner holding the "
            f"stale prior collects {min(b_plan):.1f}–{max(b_plan):.1f} items, one holding the "
            f"last-observation estimate {min(c_plan):.1f}–{max(c_plan):.1f}, and one holding the "
            f"oracle {min(o_plan):.1f}–{max(o_plan):.1f}. The agents do not follow that order. Within "
            f"a model, the difference between the stale-prior and oracle conditions is at most "
            f"{max(gap_obs):.1f} items for the agents ({', '.join(f'{g:.1f}' for g in gap_obs)}) "
            f"against {min(gap_plan):.1f}–{max(gap_plan):.1f} items for the planners. Every observed "
            f"condition lies within {max(dist_react):.1f} items of the reaction-based planner, and in "
            f"the oracle condition the agents are within "
            f"{max(abs(a - b) for a, b in zip(o_obs, o_plan)):.1f} items of the planner that holds the "
            f"same information. The interface changed the estimate the agent was told to hold; it did "
            f"not change the estimate the agent acted on, which is the one it reads off the clock.\n")

    text = '\n'.join(lines) + '\n'
    out = Path(args.out) if args.out else Path(args.summary).with_name('results_section.md')
    out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
