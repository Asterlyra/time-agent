"""Final scientific report from a complete frozen matrix; never tunes runs.

Development preview is explicitly descriptive. Main estimates reuse the frozen
task-cluster bootstrap. The publisher is separate from running experiment code.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR','/private/tmp/time-agent-matplotlib')

from scripts.matrix import digest,write_new
from scripts.study_statistics import primary_statistics
from src.adapters.opencode_go import MODELS


def load_complete(batch,preview=False):
    batch=Path(batch).resolve();config=json.loads((batch/'config.json').read_text());manifest=json.loads((batch/'manifest.json').read_text())
    if digest(config)!=json.loads((batch/'config_hash.json').read_text())['sha256'] or digest(manifest)!=config['manifest_hash']:
        raise ValueError('configuration or manifest changed')
    expected=216 if preview else 1080
    if config['stage']!=('development' if preview else 'formal') or len(manifest)!=expected:
        raise ValueError('expected complete development preview or complete formal 1080 matrix')
    if set(config['models'])!=set(MODELS):raise ValueError('unexpected model set')
    hashes=json.loads((batch/'source_snapshot_hashes.json').read_text())
    root=Path(__file__).resolve().parent.parent
    for path,sha in hashes.items():
        p=batch/'source_snapshot'/Path(path).relative_to(root)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('archived source changed')
    if digest(hashes)!=config['code_hash']:raise ValueError('archived code hash mismatch')
    rows=[]
    for entry in manifest:
        path=batch/'episodes'/(entry['run_id']+'.json')
        row=json.loads(path.read_text())
        if row['manifest']!=entry or row['result']['metadata']['config_hash']!=digest(config):raise ValueError('episode integrity mismatch')
        rows.append(row)
    return batch,config,manifest,rows


def outcome(result):
    if result['deadline_success']:return 'Correct'
    reason=result['termination_reason']
    if reason=='submitted':return 'Wrong submission'
    if reason.startswith('timeout'):return 'Tool timeout' if 'tool' in reason else 'Model timeout'
    return reason


def pairs(rows):
    blocks=collections.defaultdict(dict)
    for row in rows:
        e=row['manifest']
        if e['profile']=='fast_to_slow' and e['condition'] in ('B','C'):
            blocks[(e['task_id'],e['model_id'],e['repeat'])][e['condition']]=row
    result=[]
    for combo in ((True,False),(False,True),(False,False),(True,True)):
        selected=None
        for key,block in sorted(blocks.items()):
            if set(block)=={'B','C'} and (bool(block['C']['result']['deadline_success']),bool(block['B']['result']['deadline_success']))==combo:
                selected=(key,block);break
        result.append((combo,selected))
    return result


def publish(batch,output,preview=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    batch,config,manifest,rows=load_complete(batch,preview)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    models=list(MODELS);profiles=('stable_fast','fast_to_slow','slow_to_fast');colors=['#64748b','#db9b39','#197f9d']
    source={'batch':str(batch),'config_hash':digest(config),'manifest_hash':digest(manifest),
        'publisher_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'mode':'development preview' if preview else 'formal',
        'episodes':len(rows),'success':sum(r['result']['deadline_success'] for r in rows)}
    write_new(output/'source.json',source);(output/'publisher_source.py').write_bytes(Path(__file__).read_bytes())
    def save(fig,name):
        if preview:
            fig.text(.5,-.025,'Development preview only; no formal effect estimate',ha='center',fontsize=9,color='#475569')
        fig.tight_layout();fig.savefig(output/(name+'.png'),dpi=180,bbox_inches='tight')
        fig.savefig(output/(name+'.svg'),bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(3,3,figsize=(12,9),sharey=True)
    table=[]
    for i,profile in enumerate(profiles):
        for j,model in enumerate(models):
            ax=axes[i,j];values=[];labels=[]
            for condition in 'ABC':
                z=[r['result'] for r in rows if r['manifest']['model_id']==model and r['manifest']['profile']==profile and r['manifest']['condition']==condition]
                n=len(z);s=sum(r['deadline_success'] for r in z);values.append(s/n);labels.append(f'{condition}\n{s}/{n}')
                table.append({'model':model,'profile':profile,'condition':condition,'n':n,'success':s})
            ax.bar(labels,values,color=colors);ax.set_ylim(0,1.08);ax.set_title(model if i==0 else profile,fontsize=9)
            if j==0:ax.set_ylabel(profile+'\nDeadline success')
    fig.suptitle('Development preview only' if preview else 'Frozen formal experiment: success by model and latency',fontsize=12)
    save(fig,'success_by_latency')
    categories=sorted({outcome(r['result']) for r in rows});fig,ax=plt.subplots(figsize=(10,4));bottom=[0]*3
    for category in categories:
        counts=[sum(r['manifest']['model_id']==model and outcome(r['result'])==category for r in rows) for model in models]
        ax.bar(models,counts,bottom=bottom,label=category);bottom=[a+b for a,b in zip(bottom,counts)]
    ax.legend(loc='upper left',bbox_to_anchor=(1,1));ax.set_ylabel('Episodes');ax.set_title('Correct answers, wrong submissions and termination causes');save(fig,'outcomes')
    chosen=pairs(rows);present=[(combo,value) for combo,value in chosen if value is not None]
    if present:
        fig,axes=plt.subplots(len(present),1,figsize=(12,2.5*len(present)),squeeze=False)
        for ax,(combo,(key,block)) in zip(axes[:,0],present):
            for y,condition in enumerate('BC'):
                result=block[condition]['result'];budget=result['budget_s'];change=budget*result['shift_fraction']
                for event in result['events']:
                    if event.get('event_type')=='model_request' and 'response_end_offset_s' in event:
                        start=event['request_start_offset_s'];end=event['response_end_offset_s'];color='#94a3b8'
                    elif event.get('event_type')=='tool' and 'tool_end_offset_s' in event:
                        start=event['tool_start_offset_s'];end=event['tool_end_offset_s'];color='#166c8b' if event.get('injected_target_s',0)>3 else '#55b6ae'
                    else:continue
                    ax.barh(y,max(0,end-start),left=start,height=.45,color=color,hatch='//' if event.get('is_censored') else None)
                ax.plot(result['elapsed_s'],y,'o',color='#15803d' if result['deadline_success'] else '#b91c1c')
                ax.vlines(change,y-.35,y+.35,color='#a855f7',linestyle=':');ax.vlines(budget,y-.35,y+.35,color='#b91c1c',linestyle='--')
            ax.set_yticks([0,1],[f'B: {outcome(block["B"]["result"])}',f'C: {outcome(block["C"]["result"])}'])
            ax.set_xlim(0,max(r['result']['budget_s'] for r in block.values())+3)
            ax.set_title(f'{key[1]} | {key[0]} | repeat {key[2]} | fast_to_slow',fontsize=9);ax.set_xlabel('Wall-clock seconds')
        fig.legend(handles=[Patch(color='#94a3b8',label='Model request'),Patch(color='#55b6ae',label='Fast target tool'),Patch(color='#166c8b',label='Slow target tool')],loc='upper center',ncol=3)
        fig.suptitle('First paired case per C/B outcome: dotted=change, dashed=deadline',y=1.01,fontsize=11)
        save(fig,'paired_timelines')
    stats=None
    if not preview:
        stats=primary_statistics(manifest,rows);write_new(output/'primary_statistics.json',stats)
        names=models+['equal_model_mean'];fig,ax=plt.subplots(figsize=(9,4))
        for i,name in enumerate(names):
            estimate=stats['point'][name]*100;lo,hi=[v*100 for v in stats['bootstrap_95_percentile'][name]]
            ax.plot([lo,hi],[i,i],color='#197f9d',linewidth=2);ax.plot(estimate,i,'o',color='#197f9d')
            ax.annotate(f'{estimate:+.1f} [{lo:+.1f}, {hi:+.1f}]',(hi,i),xytext=(7,0),textcoords='offset points',va='center',fontsize=8)
        ax.axvline(0,color='#64748b',linestyle='--');ax.set_yticks(range(4),names);ax.set_xlabel('C minus B deadline success (percentage points)')
        ax.set_title('Primary: fast_to_slow, paired task-cluster bootstrap 95% intervals');ax.margins(x=.35);save(fig,'primary_effect')
    write_new(output/'counts.json',table)
    lines=['# 三模型工具延迟实验结果','',f'批次：`{batch.name}`；配置哈希：`{digest(config)}`。',
        '', '这是开发预览，仅作描述，未计算正式效果区间。' if preview else '这是完整冻结清单的正式结果；没有根据测试集结果修改配置或删除失败。',
        '',f'完成 {len(rows)} 次，截止前数值与证据同时正确 {source["success"]} 次。',
        '',f'模型：{", ".join(models)}。预算 {config["budget_s"]} 秒，变化点 {config["budget_s"]*config["shift_fraction"]:.2f} 秒，快/慢目标 2/15 秒；并发 `{config["concurrency"]}`。',
        '', 'A/B/C 共同看到时间、校准和历史。A 无额外摘要，B 初始固定均值，C 最近最多三条完整同类工具均值。',
        '', '| 模型 | 延迟模式 | 条件 | 正确/完成 |','|---|---|---|---:|']
    for row in table:lines.append(f'| {row["model"]} | {row["profile"]} | {row["condition"]} | {row["success"]}/{row["n"]} |')
    if stats:
        estimate=stats['point']['equal_model_mean']*100;lo,hi=[v*100 for v in stats['bootstrap_95_percentile']['equal_model_mean']]
        lines+=['','## 预先指定的主要比较','',f'fast_to_slow 下，三模型等权 C−B 为 **{estimate:+.2f} 个百分点**，按任务实例聚类、任务族分层的 10,000 次配对 bootstrap 95% 区间为 **[{lo:+.2f}, {hi:+.2f}]** 个百分点。']
        interpretation='区间完全高于零，支持所测设置下正向差异。' if lo>0 else '区间完全低于零，支持所测设置下负向差异。' if hi<0 else '区间包含零，当前数据未给出方向确定的差异证据；这不等于证明两种方法等效。'
        lines+=['',interpretation,'','![主要差值及区间](primary_effect.png)']
    lines+=['','## 图','', '![分模型与延迟模式成功率](success_by_latency.png)','', '![正确、错误和终止原因](outcomes.png)']
    if present:lines+=['','![主环境配对时间线](paired_timelines.png)']
    lines+=['','时间线按任务、模型、重复编号排序，在四种 C/B 成败组合中各选第一对；未出现的组合列为缺失，不挑最有利案例。']
    for combo,value in chosen:
        if value is None:lines.append(f'- C/B={combo}：没有对应配对。')
    lines+=['','## 可支持的结论与限制','',
        '- 三个模型是固定 Go 别名和同一实验框架的组合，不能外推到所有模型或所有 agent；服务端默认推理设置与具体供应路径并未完全固定。',
        '- 完整任务只有 20 个独立测试实例，模板结构相关；重复与条件不是额外独立任务。单模型区间是探索性结果，未做多重检验校正。' if not preview else '- 开发实例重复用于可行性校准，不能当作正式测试或独立任务扩容。',
        '- 请求墙钟包含网络、服务、生成和客户端处理；不是纯推理时间。工具阶段按调用开始时刻判定，超时调用为删失。',
        '- 成功率或工具次数改变不足以单独证明策略适应；固定公开前缀探针另行报告，不混入本矩阵。',
        '- 所有失败保留。模型服务异常和未知用量需要结合原始记录单列，不能将未报告消耗当作零。',
        '', '[统计明细](primary_statistics.json)' if stats else '[描述性计数](counts.json)']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print(output/'report.md')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch');parser.add_argument('--output',required=True);parser.add_argument('--development-preview',action='store_true');args=parser.parse_args()
    publish(args.batch,args.output,args.development_preview)
