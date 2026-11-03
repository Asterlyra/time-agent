"""Render the Study 2 markdown tables used in the manuscript from stats_summary.json."""
import argparse
import json
from pathlib import Path

SHORT = {'glm-5.3-flash': 'GLM', 'qwen3.8-flash': 'Qwen', 'deepseek-v4.1-flash': 'DeepSeek'}
PROFILES = ('stable_fast', 'fast_to_slow', 'drift_up')
PLABEL = {'stable_fast': 'constant 8 s', 'fast_to_slow': 'step 8->60 s', 'drift_up': 'drift 8->60 s'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text())
    cells = summary['cells']
    lines = []
    lines.append('| Profile | Model | A | B | C | O |')
    lines.append('|---|---|---:|---:|---:|---:|')
    for profile in PROFILES:
        for model in ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash'):
            values = []
            for condition in 'ABCO':
                cell = cells.get(f'{profile}|{model}|{condition}')
                values.append(f"{cell['mean_score']:.1f}" if cell else '—')
            lines.append(f"| {PLABEL[profile]} | {SHORT[model]} | " + ' | '.join(values) + ' |')
    lines.append('')
    lines.append('| Profile | Contrast | Pooled | 95% CI | p (sign-flip) | per model (GLM / Qwen / DS) |')
    lines.append('|---|---|---:|---|---:|---|')
    wanted = [('drift_up', c) for c in ('C-B', 'B-A', 'C-A', 'O-C', 'O-B')] + \
             [('fast_to_slow', c) for c in ('C-B', 'B-A', 'O-C')] + \
             [('stable_fast', 'C-B')]
    for profile, contrast in wanted:
        row = next((c for c in summary['contrasts']
                    if c['profile'] == profile and c['contrast'] == contrast), None)
        if not row:
            continue
        pm = row['per_model']
        per = ' / '.join(f"{pm.get(m, float('nan')):+.1f}" for m in
                         ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash'))
        lines.append(f"| {PLABEL[profile]} | {contrast} | {row['pooled']:+.1f} | "
                     f"[{row['ci'][0]:+.1f}, {row['ci'][1]:+.1f}] | "
                     f"{row['p_randomisation']:.3f} | {per} |")
    lines.append('')
    lines.append('| Profile | Cond | submitted | mean last-fetch remaining (s) | mean fetches |')
    lines.append('|---|---|---:|---:|---:|')
    for profile in PROFILES:
        for condition in 'ABCO':
            b = summary['behaviour'].get(f'{profile}:{condition}')
            if not b:
                continue
            lines.append(f"| {PLABEL[profile]} | {condition} | {b['p_submitted']:.2f} | "
                         f"{(b['mean_last_fetch_remaining_s'] or 0):.1f} | {b['mean_fetches']:.1f} |")
    text = '\n'.join(lines) + '\n'
    out = Path(args.out) if args.out else Path(args.summary).with_name('tables.md')
    out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
