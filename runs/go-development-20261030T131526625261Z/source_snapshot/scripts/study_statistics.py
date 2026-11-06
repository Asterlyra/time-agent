"""Primary paired estimates; complete formal batches only, task-cluster resampling."""
import collections
import random


def primary_statistics(manifest, rows, *, iterations=10000, seed=911):
    by_id={r['manifest']['run_id']:r for r in rows}
    if set(by_id)!={e['run_id'] for e in manifest}:
        raise ValueError('primary inference requires the complete planned matrix')
    models=sorted({e['model_id'] for e in manifest})
    blocks=collections.defaultdict(dict);families={}
    for entry in manifest:
        if entry['profile']!='fast_to_slow':continue
        result=by_id[entry['run_id']]['result']
        blocks[(entry['task_id'],entry['model_id'],entry['repeat'])][entry['condition']]=int(result['deadline_success'])
        families[entry['task_id']]=entry['task_family']
    deltas=collections.defaultdict(lambda:collections.defaultdict(list))
    for (task,model,repeat),values in blocks.items():
        if not {'B','C'}<=set(values):raise ValueError('incomplete B/C block')
        deltas[task][model].append(values['C']-values['B'])
    tasks=sorted(deltas)
    if not tasks or any(set(deltas[t])!=set(models) for t in tasks):raise ValueError('model/task matrix incomplete')
    strata=collections.defaultdict(list)
    for task in tasks:strata[families[task]].append(task)
    def estimate(sample):
        out={}
        for model in models:
            values=[d for task in sample for d in deltas[task][model]]
            out[model]=sum(values)/len(values)
        out['equal_model_mean']=sum(out.values())/len(models)
        return out
    point=estimate(tasks);draws={k:[] for k in point};rng=random.Random(seed)
    for _ in range(iterations):
        sample=[rng.choice(group) for family,group in sorted(strata.items()) for _ in group]
        for k,v in estimate(sample).items():draws[k].append(v)
    intervals={}
    for k,v in draws.items():
        v.sort();intervals[k]=[v[int(.025*(iterations-1))],v[int(.975*(iterations-1))]]
    return {'primary':'fast_to_slow C-B deadline success difference','point':point,
        'bootstrap_95_percentile':intervals,'task_clusters':len(tasks),'task_strata':{k:len(v) for k,v in strata.items()},
        'iterations':iterations,'seed':seed,'method':'task-cluster paired bootstrap, stratified by family, fixed model equal mean',
        'limits':'Fixed three-model set and related templates; repeated runs are not independent tasks; individual intervals are exploratory, not multiplicity-adjusted.'}
