"""Descriptive suspension sensitivity, separate from the frozen primary estimator.

No API calls or result mutation. CLI requires the complete formal matrix and an
explicit review chain. Bounds change only reviewed environment endpoints, hold
all other endpoints fixed, and are NOT confidence intervals or causal effects.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from scripts.matrix import digest, write_new


def sensitivity(manifest, rows, reviewed_ids):
    expected = {e['run_id']: e for e in manifest}
    actual = {r['manifest']['run_id']: r for r in rows}
    if (len(expected) != len(manifest) or len(actual) != len(rows)
            or set(expected) != set(actual)):
        raise ValueError('requires unique complete planned matrix')
    environmental = set()
    for ident, row in actual.items():
        if row['manifest'] != expected[ident]:
            raise ValueError('row identity mismatch')
        result = row['result']
        if result['termination_reason'] == 'environment_interruption':
            environmental.add(ident)
            if result['deadline_success'] or result.get('valid_submission'):
                raise ValueError('environment interruption has accepted success/submission')
    if environmental != set(reviewed_ids):
        raise ValueError('environment IDs must exactly match review')

    cells = collections.defaultdict(list)
    blocks = collections.defaultdict(dict)
    segments = collections.defaultdict(list)
    for row in rows:
        e, r = row['manifest'], row['result']
        cells[(e['model_id'], e['profile'], e['condition'])].append(row)
        segment = r.get('metadata', {}).get('continuation_review_sha256', 'original')
        segments[segment].append(row)
        if e['profile'] == 'fast_to_slow' and e['condition'] in ('B', 'C'):
            key = (e['model_id'], e['task_id'], e['repeat'])
            if e['condition'] in blocks[key]:
                raise ValueError('duplicate paired cell')
            blocks[key][e['condition']] = (row, segment)

    pairs = collections.defaultdict(list)
    for (model, task, repeat), block in blocks.items():
        if set(block) != {'B', 'C'}:
            raise ValueError('incomplete B/C pair')
        b, bs = block['B']; c, cs = block['C']
        be = b['manifest']['run_id'] in environmental
        ce = c['manifest']['run_id'] in environmental
        observed = int(c['result']['deadline_success']) - int(b['result']['deadline_success'])
        pairs[model].append({'observed': observed, 'lower': observed-int(be),
                             'upper': observed+int(ce), 'affected': be or ce,
                             'cross_segment': bs != cs})
    models = sorted({e['model_id'] for e in manifest})
    if set(pairs) != set(models):
        raise ValueError('model missing primary pairs')
    estimates = {}
    for model in models:
        values = pairs[model]; clean = [x for x in values if not x['affected']]
        estimates[model] = {
            'pairs': len(values), 'affected_pairs': sum(x['affected'] for x in values),
            'cross_segment_pairs': sum(x['cross_segment'] for x in values),
            'observed': sum(x['observed'] for x in values)/len(values),
            'endpoint_bounds': [sum(x[k] for x in values)/len(values) for k in ('lower', 'upper')],
            'unaffected_pairs_n': len(clean),
            'unaffected_pairs_descriptive': sum(x['observed'] for x in clean)/len(clean) if clean else None,
        }
    equal = {'observed': sum(x['observed'] for x in estimates.values())/len(models),
             'endpoint_bounds': [sum(x['endpoint_bounds'][i] for x in estimates.values())/len(models) for i in (0, 1)],
             'unaffected_pairs_descriptive': None}
    if all(x['unaffected_pairs_descriptive'] is not None for x in estimates.values()):
        equal['unaffected_pairs_descriptive'] = sum(x['unaffected_pairs_descriptive'] for x in estimates.values())/len(models)
    cell_table = []
    for (model, profile, condition), values in sorted(cells.items()):
        n = len(values); success = sum(x['result']['deadline_success'] for x in values)
        affected = sum(x['manifest']['run_id'] in environmental for x in values)
        cell_table.append({'model': model, 'profile': profile, 'condition': condition,
                           'n': n, 'success': success, 'environment_failures': affected,
                           'endpoint_bounds': [success/n, (success+affected)/n]})
    segment_table = []
    for segment, values in sorted(segments.items()):
        starts = [x['result']['start_utc'] for x in values if 'start_utc' in x['result']]
        ends = [x['result']['end_utc'] for x in values if 'end_utc' in x['result']]
        segment_table.append({'review_digest': segment, 'n': len(values),
                              'first_start_utc': min(starts) if starts else None,
                              'last_end_utc': max(ends) if ends else None,
                              'by_model': dict(collections.Counter(x['manifest']['model_id'] for x in values)),
                              'environment_failures': sum(x['manifest']['run_id'] in environmental for x in values)})
    return {'environment_ids': sorted(environmental), 'primary_profile': 'fast_to_slow',
            'contrast': 'C-B', 'models': estimates, 'equal_model_mean': equal,
            'cells': cell_table, 'segments': segment_table,
            'limits': 'Observed full-matrix endpoints remain primary. Bounds vary only reviewed interrupted endpoints over 0/1; not confidence intervals and not a recovered no-suspension experiment. Other outcomes may also depend on calendar/load. Unaffected-pair estimates are selected descriptive sensitivity, not replacement primary inference. Segment comparisons are confounded with task/order/model composition.'}


def verify_reviews(batch, rows, review_path):
    """Verify every immutable census and assign each continuation to its review."""
    path = Path(review_path); reviews = {}; paths = []
    while True:
        path = path.resolve()
        if str(path) in paths:
            raise ValueError('cyclic review chain')
        paths.append(str(path)); review = json.loads(path.read_text())
        if Path(review['batch']).resolve() != batch.resolve():
            raise ValueError('review batch mismatch')
        reviews[digest(review)] = review
        for rel, sha in review['immutable_file_hashes'].items():
            if hashlib.sha256((batch/rel).read_bytes()).hexdigest() != sha:
                raise ValueError('reviewed immutable file changed')
        for ident, sha in review['result_hashes'].items():
            if hashlib.sha256((batch/'episodes'/(ident+'.json')).read_bytes()).hexdigest() != sha:
                raise ValueError('reviewed result changed')
        if not review.get('previous_review'):
            break
        path = Path(review['previous_review'])
        previous = json.loads(path.read_text())
        # Historical review links used file-byte SHA-256; later links used
        # canonical JSON digest. Verify either explicit encoding, not a bypass.
        if review['previous_review_sha256'] not in (
                digest(previous), hashlib.sha256(path.read_bytes()).hexdigest()):
            raise ValueError('review chain digest mismatch')
    first = review
    for row in rows:
        meta = row['result']['metadata']; ident = row['manifest']['run_id']
        ref = meta.get('continuation_review_sha256')
        if ref is None:
            if ident not in first['result_hashes']:
                raise ValueError('unexplained original segment')
        elif ref not in reviews or meta.get('continuation_driver_sha256') != reviews[ref]['source_sha256'] or ident in reviews[ref]['result_hashes']:
            raise ValueError('invalid continuation provenance')
    return paths


def main():
    from scripts.publish_study_report import load_complete
    parser = argparse.ArgumentParser(); parser.add_argument('batch')
    parser.add_argument('--review', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    batch, config, manifest, rows = load_complete(args.batch)
    paths = verify_reviews(batch, rows, args.review)
    review = json.loads(Path(args.review).read_text())
    report = sensitivity(manifest, rows, review['resolved_environment_ids'])
    report.update(batch=str(batch), config_hash=digest(config), review_chain=paths,
                  analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write_new(Path(args.output), report)
    print(json.dumps({'output': args.output, 'episodes': len(rows), 'environment_failures': len(report['environment_ids'])}))


if __name__ == '__main__':
    main()
