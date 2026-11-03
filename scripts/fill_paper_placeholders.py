"""Fill the Study 3 prose placeholders from the statistics summary.

Keeps the abstract, introduction and results section consistent with the artefacts
instead of retyping numbers.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fmt(v, w=2):
    return f'{v:+.{w}f}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary')
    parser.add_argument('--paper', default=str(ROOT / 'paper' / 'main.md'))
    args = parser.parse_args()
    s = json.loads(Path(args.summary).read_text())
    primary = s['primary']

    def get(family, regime, x, y):
        return next((c for c in s['contrasts'] if c['family'] == family
                     and c['regime'] == regime and c['contrast'] == f'{x}-{y}'), None)

    e_i0 = get('hetero', 'all', 'E', 'I0')
    i1_i0 = get('hetero', 'all', 'I1', 'I0')
    c_i0 = get('hetero', 'all', 'C', 'I0')
    c_e = get('hetero', 'all', 'C', 'E')
    e_o = get('hetero', 'all', 'E', 'O')
    light = get('hetero', 'light_tail', 'E', 'I0')
    fast = get('hetero', 'fast_heavy', 'E', 'I0')
    slow = get('hetero', 'slow_heavy', 'E', 'I0')
    drift = get('hetero', 'drift_heavy', 'E', 'I0')
    ci = lambda row: f"[{row['ci'][0]:+.2f}, {row['ci'][1]:+.2f}]"

    def info_phrase(row, short=False):
        """Describe the informational arm by the sign of its own estimate, not by expectation."""
        if row['ci'][1] < 0:
            return (f"cost the score {abs(row['pooled']):.2f} points (95% CI {ci(row)})" if short
                    else f"made the score worse ({fmt(row['pooled'])}, 95% CI {ci(row)})")
        if row['ci'][0] > 0:
            return (f"added {fmt(row['pooled'])} points (95% CI {ci(row)})" if short
                    else f"helped ({fmt(row['pooled'])}, 95% CI {ci(row)})")
        return (f"moved nothing ({fmt(row['pooled'])}, 95% CI {ci(row)})" if short
                else f"changed nothing ({fmt(row['pooled'])}, 95% CI {ci(row)})")

    if c_e['ci'][0] <= 0 <= c_e['ci'][1]:
        source = (f"and it made no difference whether the reserve came from the harness or from the "
                  f"agent's own declaration ({fmt(c_e['pooled'])}, 95% CI {ci(c_e)})")
    else:
        winner = 'the harness' if c_e['pooled'] < 0 else "the agent's own declaration"
        source = (f"and {winner} was the better source of the number ({fmt(c_e['pooled'])}, "
                  f"95% CI {ci(c_e)})")
    abstract = (f"enforcing a deadline reserve raised the points banked by {fmt(e_i0['pooled'])} "
                f"(95% CI {ci(e_i0)}, p = {e_i0['p_randomisation']:.4f}), {source}; information alone, "
                f"including the agent's own measured request latency, {info_phrase(i1_i0)}")
    summary = (f"enforcing a deadline reserve raised the points banked by {fmt(e_i0['pooled'])} "
               f"(95% CI {ci(e_i0)}, p = {e_i0['p_randomisation']:.4f}); information alone, including the "
               f"agent's own measured request latency, {info_phrase(i1_i0)}, and it made no difference "
               f"whether the declared reserve came from the agent or from the harness "
               f"({fmt(c_e['pooled'])}, 95% CI {ci(c_e)})")
    claim = (f"that what changes deadline behaviour is enforcement rather than information: a "
             f"mechanically enforced reserve gains {fmt(e_i0['pooled'])} points while the same "
             f"information given to the agent {info_phrase(i1_i0, short=True)}")
    paper = Path(args.paper)
    text = paper.read_text()
    for token, value in (('[S3 ABSTRACT RESULT]', abstract), ('[S3 SUMMARY]', summary),
                         ('[S3 CLAIM]', claim)):
        if token in text:
            text = text.replace(token, value)
    paper.write_text(text)
    print(json.dumps({'abstract': abstract, 'summary': summary, 'claim': claim},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
