"""Figures for the manuscript. Read-only over frozen batches; writes to paper/figures."""
import argparse
import collections
import glob
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

try:                                     # imported as scripts.paper_figures
    from scripts.study3_stats import load as load_study3
except ImportError:                      # run from inside scripts/
    from study3_stats import load as load_study3

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / 'runs' / 'go-formal-20261031T041031911245Z'
FIGDIR = ROOT / 'paper' / 'figures'

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash')
SHORT = {'glm-5.3-flash': 'GLM', 'qwen3.8-flash': 'Qwen', 'deepseek-v4.1-flash': 'DeepSeek'}
S1_COND = {'A': '#9aa0a6', 'B': '#e8a33d', 'C': '#2f7ed8'}
S2_COND = {'A': '#9aa0a6', 'B': '#e8a33d', 'C': '#2f7ed8', 'O': '#4b9e6a'}
PROFILE_LABEL = {'stable_fast': 'constant 8 s', 'fast_to_slow': 'step 8\u219260 s',
                 'drift_up': 'drift 8\u219260 s', 'slow_to_fast': 'step 60\u21928 s'}
S1_PROFILE_LABEL = {'stable_fast': 'stable fast', 'fast_to_slow': 'fast\u2192slow',
                    'slow_to_fast': 'slow\u2192fast'}


def save(fig, name):
    FIGDIR.mkdir(parents=True, exist_ok=True)
    path = FIGDIR / name
    fig.savefig(path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    return path


def load_s1():
    rows = []
    for p in glob.glob(str(S1 / 'episodes' / '*.json')):
        rows.append(json.loads(Path(p).read_text()))
    return rows


def s1_success_figure():
    rows = load_s1()
    profiles = ('stable_fast', 'fast_to_slow', 'slow_to_fast')
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), sharey=True)
    width = 0.26
    for ax, model in zip(axes, MODELS):
        for i, condition in enumerate('ABC'):
            means, errs = [], []
            for profile in profiles:
                z = [r['result']['deadline_success'] for r in rows
                     if r['manifest']['model_id'] == model and r['manifest']['profile'] == profile
                     and r['manifest']['condition'] == condition]
                p = sum(z) / len(z)
                means.append(p)
                errs.append(1.96 * (p * (1 - p) / len(z)) ** .5)
            ax.bar(np.arange(len(profiles)) + (i - 1) * width, means, width,
                   yerr=errs, capsize=2, color=S1_COND[condition], label=condition,
                   edgecolor='white', linewidth=.5)
        ax.set_xticks(range(len(profiles)))
        ax.set_xticklabels([S1_PROFILE_LABEL[p] for p in profiles], fontsize=8)
        ax.set_title(SHORT[model], fontsize=10)
        ax.set_ylim(0, 1.05)
        ax.grid(axis='y', alpha=.3)
    axes[0].set_ylabel('deadline success rate')
    axes[0].legend(title='condition', fontsize=8, title_fontsize=8, loc='lower left')
    fig.suptitle('Study 1: no condition effect on binary success', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .93))
    return save(fig, 'fig1_s1_success.png')


def s2_score_figure(batch, out='fig2_s2_score.png'):
    rows = []
    for p in glob.glob(str(Path(batch) / 'episodes' / '*.json')):
        row = json.loads(Path(p).read_text())
        rows.append((row['manifest'], row['result']))
    profiles = ('stable_fast', 'fast_to_slow', 'drift_up')
    conditions = ('A', 'B', 'C', 'O')
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    width = 0.2
    for ax, model in zip(axes, MODELS):
        for i, condition in enumerate(conditions):
            means, errs = [], []
            for profile in profiles:
                z = [r['score'] for m, r in rows
                     if m['model_id'] == model and m['profile'] == profile and m['condition'] == condition]
                means.append(statistics.mean(z) if z else 0)
                errs.append(1.96 * statistics.stdev(z) / len(z) ** .5 if len(z) > 1 else 0)
            ax.bar(np.arange(len(profiles)) + (i - 1.5) * width, means, width, yerr=errs,
                   capsize=2, color=S2_COND[condition], label=condition,
                   edgecolor='white', linewidth=.5)
        ax.set_xticks(range(len(profiles)))
        ax.set_xticklabels([PROFILE_LABEL[p] for p in profiles], fontsize=8)
        ax.set_title(SHORT[model], fontsize=10)
        ax.grid(axis='y', alpha=.3)
    axes[0].set_ylabel('items scored (max 20)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title='condition', fontsize=8, title_fontsize=8, ncol=4,
               loc='lower center', bbox_to_anchor=(.5, -.04), frameon=False)
    fig.suptitle('Study 2: items collected before the deadline', fontsize=11)
    fig.tight_layout(rect=(0, .04, 1, .93))
    return save(fig, out)


def s2_effect_figure(summary_path, out='fig3_s2_effects.png'):
    summary = json.loads(Path(summary_path).read_text())
    order = [('drift_up', 'C-B'), ('drift_up', 'B-A'), ('drift_up', 'O-C'),
             ('fast_to_slow', 'C-B'), ('fast_to_slow', 'B-A'), ('fast_to_slow', 'O-C')]
    rows = []
    for profile, contrast in order:
        match = [c for c in summary['contrasts'] if c['profile'] == profile and c['contrast'] == contrast]
        if match:
            rows.append((profile, contrast, match[0]))
    fig, ax = plt.subplots(figsize=(7, .45 * len(rows) + 1.4))
    for i, (profile, contrast, c) in enumerate(rows):
        lo, hi = c['ci']
        ax.plot([lo, hi], [i, i], color='#333', lw=2)
        ax.plot([c['pooled']], [i], 'o', color='#2f7ed8', ms=7)
        ax.annotate(f"{c['pooled']:+.1f} [{lo:+.1f}, {hi:+.1f}]",
                    (hi, i), xytext=(6, 0), textcoords='offset points', va='center', fontsize=8)
    ax.axvline(0, color='#999', ls='--', lw=1)
    span = max(abs(v) for _p, _c, row in rows for v in row['ci']) or 1.0
    ax.set_xlim(-span * 1.25, span * 1.9)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{PROFILE_LABEL[p]}  {c}" for p, c, _ in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel('paired difference in items (95% cluster bootstrap CI)')
    fig.tight_layout(rect=(0, 0, 1, .93))
    ax.grid(axis='x', alpha=.3)
    fig.suptitle('Study 2: condition contrasts, equal weight over models', fontsize=11)
    return save(fig, out)


def s2_behaviour_figure(summary_path, out='fig4_s2_behaviour.png'):
    summary = json.loads(Path(summary_path).read_text())
    behaviour = summary['behaviour']
    profiles = ('stable_fast', 'fast_to_slow', 'drift_up')
    conditions = ('A', 'B', 'C', 'O')
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.2))
    width = .2
    for ax, key, ylabel, title in (
            (axes[0], 'p_submitted', 'submitted fraction', '(a) deadline met'),
            (axes[1], 'mean_last_fetch_remaining_s', 's remaining when the last fetch starts',
             '(b) reserve kept before the final fetch')):
        for i, condition in enumerate(conditions):
            vals = [behaviour.get(f'{p}:{c}', {}).get(key) or 0 for p in profiles for c in [condition]]
            ax.bar(np.arange(len(profiles)) + (i - 1.5) * width, vals, width,
                   color=S2_COND[condition], label=condition, edgecolor='white', linewidth=.5)
        ax.set_xticks(range(len(profiles)))
        ax.set_xticklabels([PROFILE_LABEL[p] for p in profiles], fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.grid(axis='y', alpha=.3)
        ax.set_ylabel(ylabel, fontsize=8)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=8, ncol=4, loc='lower center',
               bbox_to_anchor=(.5, -.04), frameon=False)
    fig.suptitle('Study 2: stopping behaviour', fontsize=11)
    fig.tight_layout(rect=(0, .04, 1, .93))
    return save(fig, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--s1', action='store_true')
    parser.add_argument('--s2-batch')
    parser.add_argument('--s2-summary')
    parser.add_argument('--s3-batch')
    parser.add_argument('--s3-summary')
    args = parser.parse_args()
    made = []
    if args.s1:
        made.append(s1_success_figure())
    if args.s2_batch:
        made.append(s2_score_figure(args.s2_batch))
    if args.s2_summary:
        made.append(s2_effect_figure(args.s2_summary))
        made.append(s2_behaviour_figure(args.s2_summary))
    if args.s2_batch and args.s2_summary:
        made.append(s2_information_vs_behaviour(args.s2_batch, args.s2_summary))
    if args.s3_batch:
        made.append(s3_arm_figure(args.s3_batch))
        made.append(s3_termination_figure(args.s3_batch))
        made.append(s3_decision_figure(Path(args.s3_batch) / 'decisions.json'))
    if args.s3_summary:
        made.append(s3_regime_figure(args.s3_summary))
    print('\n'.join(str(p) for p in made))




def s2_information_vs_behaviour(batch, summary_path, out='fig5_s2_information.png'):
    """Left: what each condition was told. Right: what each condition did."""
    rows = []
    for p in glob.glob(str(Path(batch) / 'episodes' / '*.json')):
        row = json.loads(Path(p).read_text())
        entry, result = row['manifest'], row['result']
        if entry['profile'] != 'drift_up':
            continue
        for event in result['events']:
            if event.get('event_type') == 'model_request':
                action = event.get('action')
                rows.append({
                    'condition': entry['condition'],
                    'elapsed': event['request_start_offset_s'],
                    'remaining': event['remaining_at_request_s'],
                    'reference': (event['observation'].get('duration_reference_s') or {}).get('fetch'),
                    'fetched': isinstance(action, dict) and action.get('type') == 'tool',
                })
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
    edges = [0, 25, 50, 75, 100, 125, 150, 175, 200]
    ax = axes[0]
    for condition in ('B', 'C', 'O'):
        xs, ys = [], []
        for lo, hi in zip(edges, edges[1:]):
            z = [r['reference'] for r in rows
                 if r['condition'] == condition and r['reference'] is not None
                 and lo <= r['elapsed'] < hi]
            if z:
                xs.append((lo + hi) / 2)
                ys.append(statistics.mean(z))
        if xs:
            ax.plot(xs, ys, 'o-', ms=4, lw=1.5, color=S2_COND[condition], label=condition)
    truth = [8.0 * 7.5 ** (x / 200.0) for x in edges]
    ax.plot(edges, truth, 'k--', lw=1, label='true delay')
    ax.set_xlabel('elapsed budget (s)', fontsize=8)
    ax.set_ylabel('s per fetch', fontsize=8)
    ax.set_title('(a) what the observation said', fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)

    ax = axes[1]
    edges = [0, 20, 40, 60, 80, 100, 130, 160, 210]
    for condition in ('A', 'B', 'C', 'O'):
        xs, ys = [], []
        for lo, hi in zip(edges, edges[1:]):
            z = [r['fetched'] for r in rows if r['condition'] == condition
                 and lo <= r['remaining'] < hi]
            if len(z) >= 5:
                xs.append((lo + hi) / 2)
                ys.append(sum(z) / len(z))
        if xs:
            ax.plot(xs, ys, 'o-', ms=4, lw=1.5, color=S2_COND[condition], label=condition)
    ax.set_xlabel('remaining budget at the request (s)', fontsize=8)
    ax.set_ylabel('P(make another fetch)', fontsize=8)
    ax.set_title('(b) what the agent did', fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.suptitle('Study 2, drift profile: the information moved, the policy did not', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .93))
    return save(fig, out)


S3_ARM = {'I0': '#9aa0a6', 'I1': '#b7a6d8', 'C': '#cf8f3c', 'E': '#2f7ed8', 'O': '#4b9e6a'}


def s3_arm_figure(batch, out='fig6_s3_arms.png'):
    # Shared loader so the bars use the same denominators as the tables: archived
    # host interruptions enter as zeros instead of silently leaving the sample.
    _config, rows = load_study3(batch)
    families = ('uniform', 'hetero')
    arms = ('I0', 'I1', 'C', 'E', 'O')
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=False)
    for ax, family in zip(axes, families):
        means, errs = [], []
        for arm in arms:
            z = [r['score'] for r in rows if r['family'] == family and r['arm'] == arm]
            means.append(statistics.mean(z) if z else 0)
            errs.append(1.96 * statistics.stdev(z) / len(z) ** .5 if len(z) > 1 else 0)
        ax.bar(range(len(arms)), means, yerr=errs, capsize=3,
               color=[S3_ARM[a] for a in arms], edgecolor='white')
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms)
        ax.set_title(family, fontsize=10)
        ax.grid(axis='y', alpha=.3)
        ax.set_ylabel('points banked')
    fig.suptitle('Study 3: points banked by arm', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .93))
    return save(fig, out)


def s3_termination_figure(batch, out='fig7_s3_termination.png'):
    _config, rows = load_study3(batch)
    arms = ('I0', 'I1', 'C', 'E', 'O')
    kinds = [('submitted', 'submitted by the agent', '#4b9e6a'),
             ('forced_submit', 'submitted by the harness', '#2f7ed8'),
             ('timeout_tool', 'killed during a call', '#d9534f'),
             ('timeout_model', 'killed during a request', '#e8a33d'),
             ('environment_interruption', 'lost to a host interruption', '#8d8d8d'),
             ('other', 'service error', '#c9b8a8')]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    bottom = [0] * len(arms)
    for key, label, color in kinds:
        values = []
        for arm in arms:
            cell = [r for r in rows if r['arm'] == arm and r['family'] == 'hetero']
            if key == 'other':
                hit = sum(1 for r in cell if r['termination'] not in
                          {k for k, _l, _c in kinds if k != 'other'})
            else:
                hit = sum(1 for r in cell if r['termination'] == key)
            values.append(hit / len(cell) if cell else 0)
        ax.bar(range(len(arms)), values, bottom=bottom, color=color, label=label,
               edgecolor='white', linewidth=.5)
        bottom = [a + b for a, b in zip(bottom, values)]
    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels(arms)
    ax.set_ylabel('fraction of episodes')
    ax.set_title('Study 3, heterogeneous family: how episodes end', fontsize=10)
    ax.legend(fontsize=8, loc='upper center', bbox_to_anchor=(.5, -.12), ncol=2, frameon=False)
    ax.grid(axis='y', alpha=.3)
    fig.tight_layout()
    return save(fig, out)


def s3_decision_figure(decisions_path, out='fig8_s3_decisions.png'):
    """Where in the budget the agent chooses to start a call.

    Left: the informational arm against the unguarded one — if the number did
    anything, these two curves would separate. Right: the same decisions under a
    rule, which never start a call the reserve cannot pay for.
    """
    data = json.loads(Path(decisions_path).read_text())['hetero']
    edges = np.arange(0, 225, 15)
    centres = (edges[:-1] + edges[1:]) / 2
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.2), sharey=True)
    panels = (('I0', ['I1'], 'what the number changed: nothing'),
              ('I0', ['E'], 'what the rule changed: no call in the tail'))
    for ax, (base, others, title) in zip(axes, panels):
        total = sum(data[base]['histogram_15s']) or 1
        ax.step(edges, [0] + [v / total for v in data[base]['histogram_15s']],
                where='post', color=S3_ARM[base], lw=2, label=f'{base} (no information)')
        for arm in others:
            t = sum(data[arm]['histogram_15s']) or 1
            ax.step(edges, [0] + [v / t for v in data[arm]['histogram_15s']], where='post',
                    color=S3_ARM[arm], lw=2, label=f'{arm}')
        ax.axvspan(0, 30, color='#d9534f', alpha=.08, lw=0)
        ax.set_xlim(0, 210)
        ax.set_xlabel('seconds left in the budget when the call was started', fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=.3)
        ax.legend(fontsize=8, frameon=False)
    axes[0].set_ylabel('share of calls per 15 s bin')
    fig.suptitle('Study 3, heterogeneous family: the decision, and the rule', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .93))
    return save(fig, out)


def s3_regime_figure(summary_path, out='fig9_s3_regime.png'):
    summary = json.loads(Path(summary_path).read_text())
    regimes = ('light_tail', 'fast_heavy', 'slow_heavy', 'drift_heavy')
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    width = .38
    for i, family in enumerate(('uniform', 'hetero')):
        means, errs = [], []
        for regime in regimes:
            row = next((c for c in summary['contrasts']
                        if c['family'] == family and c['regime'] == regime
                        and c['contrast'] == 'E-I0'), None)
            means.append(row['pooled'] if row else 0)
            errs.append((row['ci'][1] - row['ci'][0]) / 2 if row else 0)
        ax.bar(np.arange(len(regimes)) + (i - .5) * width, means, width, yerr=errs, capsize=3,
               label=family, color=['#cf8f3c', '#2f7ed8'][i], edgecolor='white')
    ax.axhline(0, color='#555', lw=1)
    ax.set_xticks(range(len(regimes)))
    ax.set_xticklabels(['light tail', 'fast,\nheavy tail', 'slow,\nheavy tail', 'drift,\nheavy tail'], fontsize=8)
    ax.set_ylabel('E − I0 (points)')
    ax.set_title('Study 3: the value of enforcement rises with the tail', fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=.3)
    fig.tight_layout()
    return save(fig, out)


if __name__ == '__main__':
    main()
