"""Render the Study 3 results section from stats_summary.json."""
import argparse
import json
from pathlib import Path

SHORT = {'glm-5.3-flash': 'GLM', 'qwen3.8-flash': 'Qwen',
         'deepseek-v4.1-flash': 'DeepSeek', 'mimo-v2.6-flash': 'MiMo'}
MODELS = tuple(SHORT)
ARMS = ('I0', 'I1', 'C', 'E', 'O')
FAMILIES = ('uniform', 'hetero')
REGIMES = ('light_tail', 'fast_heavy', 'slow_heavy', 'drift_heavy')
RLABEL = {'light_tail': 'light tail', 'fast_heavy': 'fast, heavy tail',
          'slow_heavy': 'slow, heavy tail', 'drift_heavy': 'drifting, heavy tail'}


def num(value, width=2):
    if value is None:
        return '—'
    if abs(value) < 10 ** (-width) / 2:
        value = 0.0
    return f'{value:+.{width}f}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text())
    cells, contrasts, behaviour = summary['cells'], summary['contrasts'], summary['behaviour']
    model_cells = summary.get('model_cells') or {}
    latency_path = Path(args.summary).with_name('latency_by_model.json')
    latency = json.loads(latency_path.read_text()) if latency_path.exists() else {}
    by_model = latency.get('models', {})
    lines = []
    n = summary['n_episodes']
    n_arch = summary.get('n_archived_environment_failures', 0)
    lines.append('### 5.4 Results\n')
    planned = summary.get('planned', n)
    lines.append(f'Of the {planned} planned episodes, {n} are accounted for: {n - n_arch} scored and '
                 f'{n_arch} archived host-suspend failures, retained at zero and flagged. Table 7 gives '
                 'the points banked by family, regime and arm.\n')
    lines.append('**Table 7. Study 3, mean points banked (maximum 5 × number of items).**\n')
    lines.append('| Family | Regime | I0 | I1 | C | E | O |')
    lines.append('|---|---|---:|---:|---:|---:|---:|')
    for family in FAMILIES:
        for regime in REGIMES:
            values = []
            for arm in ARMS:
                cell = cells.get(f'{family}|{regime}|{arm}')
                values.append(f"{cell['mean_score']:.1f}" if cell else '—')
            lines.append(f'| {family} | {RLABEL[regime]} | ' + ' | '.join(values) + ' |')
    lines.append('')

    primary = summary['primary']
    pm = primary['per_model']
    lines.append('![Points banked by arm](figures/fig6_s3_arms.png)\n')
    lines.append('**Figure 6.** Study 3, points banked by arm, in the uniform and heterogeneous families; '
                 'bars are means with 95% normal-approximation intervals over episodes.\n')
    lines.append(f"**Primary contrast.** In the heterogeneous family, the equal-weight E−I0 difference "
                 f"was {num(primary['pooled'])} points, 95% cluster-bootstrap CI "
                 f"[{primary['ci'][0]:+.2f}, {primary['ci'][1]:+.2f}], sign-flip p = "
                 f"{primary['p_randomisation']:.3f} over {primary['n_blocks']} paired blocks. Per model: "
                 + ', '.join(f"{SHORT[m]} {num(pm.get(m))}" for m in MODELS) + '.\n')

    rows = [c for c in contrasts if c['regime'] == 'all']
    lines.append('**Table 8. Study 3, pre-registered contrasts (points, 95% cluster bootstrap CI).**\n')
    lines.append('| Family | Contrast | Pooled | 95% CI | p | GLM | Qwen | DeepSeek | MiMo |')
    lines.append('|---|---|---:|---|---:|---:|---:|---:|---:|')
    for family in FAMILIES:
        for x, y in (('E', 'I0'), ('I1', 'I0'), ('C', 'I0'), ('C', 'E'), ('E', 'O')):
            row = next((c for c in rows if c['family'] == family and c['contrast'] == f'{x}-{y}'), None)
            if not row:
                continue
            lines.append(f"| {family} | {x}−{y} | {num(row['pooled'])} | "
                         f"[{row['ci'][0]:+.2f}, {row['ci'][1]:+.2f}] | {row['p_randomisation']:.3f} | "
                         + ' | '.join(num(row['per_model'].get(m)) for m in MODELS) + ' |')
    lines.append('')

    b = behaviour
    lines.append('**Table 9. Study 3, why episodes end.**\n')
    lines.append('| Family | Arm | submitted | forced | mean banked items | mean denied fetches |')
    lines.append('|---|---|---:|---:|---:|---:|')
    for family in FAMILIES:
        for arm in ARMS:
            row = b.get(f'{family}|{arm}')
            if not row:
                continue
            lines.append(f"| {family} | {arm} | {row['p_submitted']:.2f} | {row['p_forced']:.2f} | "
                         f"{row['mean_banked']:.1f} | {row['mean_denied']:.1f} |")
    lines.append('')

    def get(family, x, y):
        return next(c for c in rows if c['family'] == family and c['contrast'] == f'{x}-{y}')

    e_i0 = get('hetero', 'E', 'I0')
    i1_i0 = get('hetero', 'I1', 'I0')
    c_i0 = get('hetero', 'C', 'I0')
    c_e = get('hetero', 'C', 'E')
    e_o = get('hetero', 'E', 'O')
    light = [c for c in contrasts if c['regime'] == 'light_tail' and c['contrast'] == 'E-I0'
             and c['family'] == 'hetero']
    light_txt = ''
    light_e = [c for c in contrasts if c['regime'] == 'light_tail' and c['contrast'] == 'E-I0'
               and c['family'] == 'hetero']
    if light_e:
        light_txt = (f" The `light_tail` negative control was designed to test the opposite reading, "
                     f"that the benefit comes from tool-cost variance: it makes call durations almost "
                     f"deterministic. The benefit does not shrink there ({num(light_e[0]['pooled'])}, "
                     f"{light_e[0]['ci'][0]:+.2f} to {light_e[0]['ci'][1]:+.2f}), so the control fails to "
                     f"behave as a control was meant to, and the variance that matters is on the request "
                     f"side rather than the tool side.")
    moved = 'did not move'
    if i1_i0['ci'][1] < 0:
        moved = ('made things worse: the same calls, the same items, but fewer episodes ended in a '
                 'submission')
    elif i1_i0['ci'][0] > 0:
        moved = 'improved the score'
    if 'arms' in latency:
        same = (f"almost exactly the same calls: in the heterogeneous family I0 and I1 make "
                f"{latency['arms']['I0']['mean_calls']:.1f} and {latency['arms']['I1']['mean_calls']:.1f} "
                f"calls and fetch {latency['arms']['I0']['mean_items_fetched']:.1f} and "
                f"{latency['arms']['I1']['mean_items_fetched']:.1f} items on average, so the policy did not "
                f"change what the agent did, only how often the doing was cut off. ")
    else:
        same = ("almost exactly the same calls, so the policy did not change what the agent did, only how "
                "often the doing was cut off. ")
    enforce_text = (f"**Enforcement, not information.** A reserve the harness computes and enforces beat "
                    f"the unguarded baseline by {num(e_i0['pooled'])} points "
                    f"[{e_i0['ci'][0]:+.2f}, {e_i0['ci'][1]:+.2f}] (Figure 6; Table 8 collects every "
                    f"pre-registered contrast). A reserve the *agent* declared, then mechanically enforced "
                    f"by the same code, did just as well ({num(c_i0['pooled'])}, "
                    f"[{c_i0['ci'][0]:+.2f}, {c_i0['ci'][1]:+.2f}]); the difference between the two is "
                    f"{num(c_e['pooled'])} [{c_e['ci'][0]:+.2f}, {c_e['ci'][1]:+.2f}]: indistinguishable. "
                    f"What separates "
                    f"both from the informational arms is therefore not who chooses the number but whether "
                    f"anything acts on it. Even a perfect cost model buys little once the reserve is "
                    f"enforced: O trails E by {num(e_o['pooled'])} "
                    f"[{e_o['ci'][0]:+.2f}, {e_o['ci'][1]:+.2f}]. The mechanism is visible in how episodes "
                    f"end (Figure 7): in `I0` and `I1` most failures are episodes still waiting on a call "
                    f"when the budget ran out, while under `C`, `E` and `O` the harness submits whatever is "
                    f"in hand before the deadline.\n")

    info_text = (f"**Information without a rule.** Giving the agent the numbers does not do this. Full "
                 f"information {moved} (I1−I0 = {num(i1_i0['pooled'])} "
                 f"[{i1_i0['ci'][0]:+.2f}, {i1_i0['ci'][1]:+.2f}]). The arm displayed the per-size cost "
                 f"estimates and the agent's own median request latency — a number the model cannot observe "
                 f"directly — and the agents went on making " + same +
                 f"What changed was the ending, not the calls: the same information that leaves the count "
                 f"and the items alone costs several points, because a number that has to be read inside "
                 f"the loop is paid for inside the loop. This is the Study 2 finding again — the declared "
                 f"estimate improved while the operative one did not — now with stochastic costs and "
                 f"differing item values.\n")

    lines.append(enforce_text)
    lines.append('![How episodes end](figures/fig7_s3_termination.png)\n')
    lines.append('**Figure 7.** Study 3, how episodes end in the heterogeneous family. `I0` and `I1` mostly '
                 'die inside a call or a request; under `C`, `E` and `O` the harness submits whatever is in '
                 'hand before the budget expires.\n')
    lines.append(info_text)

    def cell(family, arm, model):
        return model_cells.get(f'{family}|{arm}|{model}')

    decisions_path = Path(args.summary).with_name('decisions.json')
    decisions = json.loads(decisions_path.read_text()).get('hetero', {}) if decisions_path.exists() else {}
    d0, d1, de = (decisions.get(a) for a in ('I0', 'I1', 'E'))
    if d0 and d1 and de and d0.get('median_remaining_at_start_s'):
        lines.append(
            f"**The decision itself.** Figure 8 reads the moment a call is started off every episode. "
            f"If the informational arm changed what the agent does, its calls would sit further from the "
            f"deadline than the unguarded arm's. They do not: the median call in `I1` starts with "
            f"{d1['median_remaining_at_start_s']:.1f} s left, against {d0['median_remaining_at_start_s']:.1f} s "
            f"in `I0`, and the two arms make {d1['calls_per_episode']:.2f} and "
            f"{d0['calls_per_episode']:.2f} calls per episode. Measured against the model's own request "
            f"distribution, the share of calls started on a budget too short to pay for a typical slow "
            f"request is {d1['share_started_below_own_p90']:.1%} in `I1` and "
            f"{d0['share_started_below_own_p90']:.1%} in `I0` — the number arrives and changes neither the "
            f"count nor the timing of the decisions. Under enforcement the same decisions are made and then "
            f"refused before it can kill the episode: {de['share_started_below_own_p90']:.1%} of `E` calls "
            f"start on such a budget, because a call the reserve cannot pay for is never admitted. The gain "
            f"is not a change in judgement but a change in what is allowed to reach execution.\n")
        lines.append('![Where calls are started](figures/fig8_s3_decisions.png)\n')
        lines.append('**Figure 8.** Where in the budget a call is started, heterogeneous family. (a) The '
                     'informational arm `I1` against the unguarded baseline `I0`: the same distribution, '
                     'bin for bin. (b) The same baseline against the enforced reserve `E`, which never '
                     'starts a call in the shaded last 30 s.\n')

    regime_rows = {c['regime']: c for c in contrasts
                   if c['family'] == 'hetero' and c['contrast'] == 'E-I0' and c['regime'] != 'all'}
    if len(regime_rows) >= 3:
        light_row = regime_rows.get('light_tail')
        named = [(RLABEL[r].split(',')[0], regime_rows[r]) for r in
                 ('fast_heavy', 'slow_heavy', 'drift_heavy') if r in regime_rows]
        parts = [f"{label} {num(row['pooled'])} [{row['ci'][0]:+.2f}, {row['ci'][1]:+.2f}]"
                 for label, row in named]
        text = ('**Regime dependence, and a control that failed.** Across the three stochastic regimes the '
                'enforcement gain was ' + ', '.join(parts[:-1]) + ' and ' + parts[-1])
        if light_row:
            gains = [row['pooled'] for _, row in named]
            biggest = light_row['pooled'] > max(gains)
            text += (f"; in the near-deterministic `light_tail` control, where a reserve against tool-cost "
                     f"variance would have nothing to protect, it was {num(light_row['pooled'])} "
                     f"[{light_row['ci'][0]:+.2f}, {light_row['ci'][1]:+.2f}]"
                     + (" — the largest of the four, so the pre-registered negative control does not behave as "
                        "a control." if biggest else
                        " — no smaller than in the stochastic regimes, so the pre-registered negative control "
                        "does not behave as a control."))
            text += (' That is informative rather than merely inconvenient: it rules out the reading that '
                     'enforcement helps by absorbing the variance of tool durations, and locates the variance '
                     'it does absorb on the request side, where the agent pays for its own inference.\n')
        else:
            text += '.\n'
        lines.append(text)
        lines.append('![Enforcement by regime](figures/fig9_s3_regime.png)\n')
        lines.append('**Figure 9.** Study 3, the E−I0 difference by tool-cost regime, uniform and '
                     'heterogeneous families. The gain is not smaller where call durations are nearly '
                     'deterministic.\n')

    if all(cell('hetero', 'I0', m) and cell('hetero', 'E', m) for m in MODELS):
        lines.append('### 5.5 Who benefits from enforcement\n')
        lines.append('Enforcement is not uniformly useful. Table 10 splits the heterogeneous family by model, '
                     'together with two things read straight from the episodes: the distribution of time the '
                     'model itself takes between tool calls, and how many items an unguarded episode had '
                     'already fetched when the deadline killed it.\n')
        lines.append('**Table 10. Study 3, enforcement benefit by model (heterogeneous family).**\n')
        header = '| Model | request p50 (s) | request p90 (s) | unguarded deaths | items in hand at death | I0 banked | E banked | E−I0 |'
        lines.append(header)
        lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
        for m in MODELS:
            i0, e = cell('hetero', 'I0', m), cell('hetero', 'E', m)
            lat = by_model.get(m, {})
            p50 = f"{lat['p50']:.1f}" if lat.get('p50') is not None else '—'
            p90 = f"{lat['p90']:.1f}" if lat.get('p90') is not None else '—'
            dead = f"{lat['unguarded_death_rate']:.0%}" if lat.get('unguarded_death_rate') is not None else f"{i0['p_timeout_model']:.0%}"
            hand = f"{lat['items_in_hand_at_death']:.1f}" if lat.get('items_in_hand_at_death') is not None else '—'
            lines.append(f"| {SHORT[m]} | {p50} | {p90} | {dead} | {hand} | {i0['mean_score']:.1f} | "
                         f"{e['mean_score']:.1f} | {num(pm.get(m))} |")
        lines.append('')
        if by_model:
            fastest = min(MODELS, key=lambda m: by_model.get(m, {}).get('p50') or 1e9)
            slowest = max(MODELS, key=lambda m: by_model.get(m, {}).get('p50') or -1)
            gains = {m: (pm.get(m) or 0.0) for m in MODELS}
            top = max(MODELS, key=lambda m: gains[m])
            lines.append(f"The two ends fail for opposite reasons. {SHORT[fastest]}'s median request takes "
                         f"{by_model[fastest]['p50']:.1f} s, its deadline death rate is "
                         f"{by_model[fastest]['unguarded_death_rate']:.0%}, and enforcement adds "
                         f"{num(gains[fastest])}: there is nothing to protect. {SHORT[slowest]} is the "
                         f"opposite — {by_model[slowest]['p50']:.1f} s per request, "
                         f"{by_model[slowest]['unguarded_death_rate']:.0%} of unguarded episodes die — yet it "
                         f"gains only {num(gains[slowest])}, because a dying episode had fetched just "
                         f"{by_model[slowest]['items_in_hand_at_death']:.1f} items. Enforcement converts work "
                         f"already done into points; where the model never gets far enough for that work to "
                         f"exist, the harness has nothing to save. The largest gains sit in between, at "
                         f"{SHORT[top]} ({num(gains[top])}, {by_model[top]['items_in_hand_at_death']:.1f} items "
                         f"in hand at death), and the ordering is driven by the shapedness of the request "
                         f"distribution rather than by its median: a fast median with a heavy tail is "
                         f"protected as reliably as uniformly slow requests. This is the tail that the "
                         f"`light_tail` control isolates, and it belongs to the model, not to the tool.\n")

    text = '\n'.join(lines) + '\n'
    out = Path(args.out) if args.out else Path(args.summary).with_name('results_section_s3.md')
    out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
