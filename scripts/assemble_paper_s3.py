"""One-shot assembly of the three-study manuscript from the S3 batch."""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = '[S3 RESULTS]'


def run(*args):
    print('$', ' '.join(map(str, args)), flush=True)
    subprocess.run(args, check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--skip-stats', action='store_true')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    summary = batch / 'stats_summary.json'
    if not args.skip_stats:
        run('.venv/bin/python', '-m', 'scripts.study3_stats', str(batch))
        run('.venv/bin/python', '-m', 'scripts.study3_latency', str(batch))
        run('.venv/bin/python', '-m', 'scripts.study3_decisions', str(batch))
        run('.venv/bin/python', '-m', 'scripts.study3_metrics', str(batch))
    run('.venv/bin/python', '-m', 'scripts.paper_results_section_s3', str(summary))
    run('.venv/bin/python', '-m', 'scripts.paper_figures', '--s1',
        '--s2-batch', str(ROOT / 'runs' / 's2-formal-20261102T035658599154Z'),
        '--s2-summary', str(ROOT / 'runs' / 's2-formal-20261102T035658599154Z' / 'stats_summary.json'),
        '--s3-batch', str(batch), '--s3-summary', str(summary))
    # Assembly is repeatable: the template keeps the placeholders, main.md is the output.
    manuscript = ROOT / 'paper' / 'main.md'
    template = ROOT / 'paper' / 'main_template.md'
    if not template.exists():
        if MARKER not in manuscript.read_text():
            raise SystemExit('neither a template nor a manuscript with the results marker')
        template.write_text(manuscript.read_text())
    text = template.read_text()
    if MARKER not in text:
        raise SystemExit('template lost its results marker')
    manuscript.write_text(text.replace(MARKER, (batch / 'results_section_s3.md').read_text().strip()))
    run('.venv/bin/python', '-m', 'scripts.fill_paper_placeholders', str(summary))
    run('/Users/atlas/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3',
        'scripts/build_paper_docx.py')
    print('assembled')


if __name__ == '__main__':
    main()
