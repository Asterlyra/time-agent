"""One-shot assembly: statistics -> results section -> figures -> manuscript -> docx."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = '[S2 RESULTS]'


def run(*args):
    print('$', ' '.join(args), flush=True)
    subprocess.run(args, check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--skip-stats', action='store_true')
    args = parser.parse_args()
    batch = Path(args.batch)
    summary = batch / 'stats_summary.json'
    if not args.skip_stats:
        run('.venv/bin/python', '-m', 'scripts.study2_stats', str(batch))
    section = batch / 'results_section.md'
    run('.venv/bin/python', '-m', 'scripts.paper_results_section', str(summary))
    run('.venv/bin/python', '-m', 'scripts.paper_figures', '--s1',
        '--s2-batch', str(batch), '--s2-summary', str(summary))

    manuscript = ROOT / 'paper' / 'main.md'
    text = manuscript.read_text()
    if MARKER not in text:
        raise SystemExit('results marker already replaced; edit paper/main.md manually')
    manuscript.write_text(text.replace(MARKER, section.read_text().strip()))
    run('/Users/atlas/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3',
        'scripts/build_paper_docx.py')
    print('assembled')


if __name__ == '__main__':
    main()
