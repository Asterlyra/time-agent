"""Render a descriptive batch report and standalone matplotlib figures."""
import argparse
import collections
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR','/private/tmp/time-agent-matplotlib')

from scripts.go_study import analyze
from scripts.matrix import write_new
from scripts.study_statistics import primary_statistics


def report(batch,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    batch=Path(batch).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    summary=analyze(batch,verify=False)
    manifest=json.loads((batch/'manifest.json').read_text());config=json.loads((batch/'config.json').read_text())
    rows=[json.loads(p.read_text()) for p in sorted((batch/'episodes').glob('*.json'))]
    models=config['models'];conditions=list('ABC')
    fig,axes=plt.subplots(1,len(models),figsize=(12,4),sharey=True,squeeze=False)
    for ax,model in zip(axes[0],models):
        heights=[];labels=[]
        for condition in conditions:
            z=[r for r in rows if r['manifest']['model_id']==model and r['manifest']['condition']==condition]
            n=len(z);s=sum(r['result']['deadline_success'] for r in z)
            heights.append(s/n if n else 0);labels.append(f'{condition}\n{s}/{n}' if n else f'{condition}\nno runs')
        ax.bar(labels,heights,color=['#64748b','#e6a044','#167d9a']);ax.set_ylim(0,1.1);ax.set_title(model,fontsize=10)
        ax.set_ylabel('Deadline success / completed episodes')
    fig.suptitle(f'{summary["stage"]}: descriptive results; not a condition-effect claim',fontsize=11)
    fig.tight_layout();fig.savefig(output/'success.png',dpi=180);fig.savefig(output/'success.svg');plt.close(fig)
    categories=sorted({r['result']['termination_reason'] for r in rows})
    fig,ax=plt.subplots(figsize=(9,4));bottom=[0]*len(models)
    for category in categories:
        counts=[sum(r['manifest']['model_id']==m and r['result']['termination_reason']==category for r in rows) for m in models]
        ax.bar(models,counts,bottom=bottom,label=category);bottom=[a+b for a,b in zip(bottom,counts)]
    ax.set_ylabel('Completed episodes');ax.set_title('Termination reasons (submitted includes wrong answers)')
    if categories:ax.legend(loc='upper left',bbox_to_anchor=(1,1))
    fig.tight_layout();fig.savefig(output/'termination.png',dpi=180);fig.savefig(output/'termination.svg');plt.close(fig)
    # Deterministic example selection includes successful and failed episodes.
    representatives=[]
    for model in models:
        for success in (False,True):
            z=[r for r in rows if r['manifest']['model_id']==model and bool(r['result']['deadline_success'])==success]
            if z:representatives.append(z[0])
    fig,ax=plt.subplots(figsize=(11,max(3,.65*len(representatives)+1.4)))
    for i,row in enumerate(representatives):
        result=row['result']
        for event in result['events']:
            if event.get('event_type')=='model_request' and 'response_end_offset_s' in event:
                start=event['request_start_offset_s'];end=event['response_end_offset_s'];color='#94a3b8'
            elif event.get('event_type')=='tool' and 'tool_end_offset_s' in event:
                start=event['tool_start_offset_s'];end=event['tool_end_offset_s'];color='#167d9a'
            else:continue
            ax.barh(i,max(0,end-start),left=start,height=.55,color=color,alpha=.85)
        ax.plot(result['elapsed_s'],i,'o',color='#15803d' if result['deadline_success'] else '#b91c1c')
    ax.set_yticks(range(len(representatives)),[r['manifest']['model_id']+' / '+r['manifest']['task_id']+' / '+r['manifest']['condition'] for r in representatives],fontsize=8)
    ax.set_xlabel('Wall time since episode start (seconds)');ax.set_title('Examples: gray=model request, teal=tool; dot=episode end')
    fig.tight_layout();fig.savefig(output/'timelines.png',dpi=180);fig.savefig(output/'timelines.svg');plt.close(fig)
    lines=['# 三模型实验批次报告','',f'批次：`{batch.name}`；阶段：`{summary["stage"]}`。',
        f'计划 {summary["planned"]}，完成 {summary["completed"]}，截止前正确 {summary["success"]}；未完成 {len(summary["missing"])}。',
        '','开发/诊断结果用于可行性判断，不能当作冻结后的正式条件效果。服务失败、超时和错误提交均保留。',
        '',f'设置：预算 {config["budget_s"]} 秒，变化比例 {config["shift_fraction"]}，每模型并发 {config["concurrency"]["per_model"]}，全局最多 {config["concurrency"]["global"]}。',
        '',f'计费来源记录：`{summary["billing_sources"]}`；已报告套餐额度消耗合计 {summary["allowance_known_sum"]:.6f}。未报告部分不填零。',
        '','| 模型 | 任务族 | 模式 | 条件 | 正确/完成 |','|---|---|---|---|---:|']
    for c in summary['cells']:lines.append(f'| {c["model"]} | {c["family"]} | {c["profile"]} | {c["condition"]} | {c["success"]}/{c["n"]} |')
    lines+=['','## 准入检查','']
    for gate in summary['gates']:lines.append('- `'+json.dumps(gate,ensure_ascii=False)+'`')
    lines+=['',f'进入下一阶段：{summary["ready_for_next_stage"]}。此判断不替代正式冻结、模型设置、执行边界和资源检查。',
        '','## 图','', '![正确率](success.png)','', '![终止原因](termination.png)','', '![代表性时间线](timelines.png)']
    if config['stage']=='formal' and not summary['missing']:
        stats=primary_statistics(manifest,rows);write_new(output/'primary_statistics.json',stats)
        lines+=['','## 主要比较','', '```json',json.dumps(stats,ensure_ascii=False,indent=2),'```']
    write_new(output/'summary.json',summary)
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(output/'report.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('batch');p.add_argument('--output',required=True);a=p.parse_args();report(a.batch,a.output)
