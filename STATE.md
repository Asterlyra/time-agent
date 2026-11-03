# 项目状态（供新会话接手）

更新时间：2026-11-03 17:12

## 目标

完成 S3 实验并产出可投稿 SCI Q2 / CCF-B 的论文，整合 S1（信息接口无效）、S2（接口改变被告知的估计，没改变实际用的估计）、S3（信息是装饰，执行才是约束）。

## 三个研究

| 研究 | 批次 | 规模 | 状态 |
|---|---|---|---|
| S1 | runs/go-formal-20261031T041031911245Z | 1,080 | 完成，零结果 |
| S2 | runs/s2-formal-20261102T035658599154Z | 432 | 完成（426 计分 + 6 环境失败） |
| S3 | runs/s3-A-20261102T094306204655Z | 7,040 计划 | **进行中 2,135** |

## S3 现状

- 估计量已修正（2026-11-03 17:40）：`scripts/study3_stats.py` 的 `_paired()` 原先把每个 (model, task, arm) 格子的 2–3 次 repeat 静默压成"最后写入的那一条"。改为格子内先对 repeat 取均值再配对。修正后中期数（1,660 条）：
  - E−I0 = **+5.55** [3.72, 7.32]，p=0.0005（修正前为 +8.51）
  - I1−I0 = **−4.01** [−5.71, −2.29]（修正前 ≈0）——告知自身延迟反而显著更差
  - C−I0 = +5.34、C−E = −0.71、E−O = −0.58、O−I0 = +6.13
- 新增 `sensitivity()`：中断条目"计 0" vs "整对删除"两种策略对比，当前差异 ≤0.2 分。
- `light_tail` 负对照仍不成立（E−I0 = +8.93 [6.40, 11.47]）。
- 中期行为：提交率 I0 0.43 / I1 0.32 / C 0.80 / E 0.91 / O 0.88；I0/I1 超时率 41%/52%，三个强制臂 3–15%。
- I1 为何更差的机制尚未确定（轨迹层面 I0/I1 几乎一致：fetch 次数、体量分布、剩余时间、末次请求耗时都相同，只有提交率不同）。详见 docs/S3_中期分析_20261103.md。
- 已完成 740 / 934 / 1,404 / 1,637 四次暂停与恢复，每次均清理 run_lock 并确认零进程。
- 2026-11-03 20:0x 起新增 `scripts/watch_supervisor.py`（10 分钟一查，supervisor 消失则重启；遇 STOP_SUPERVISOR / AUTH_FAILED / 跑满即退出）。暂停前必须先杀它，否则 20 分钟后批次会被重新拉起。
- 新增 `scripts/study3_latency.py`：逐模型请求延迟分位（工具调用之间的模型自身耗时）与"未护栏 episode 死时已取到的物品数"，产出 `latency_by_model.json`。
- 结果小节新增 §5.5「Who benefits from enforcement」（Table 10），由 `scripts/paper_results_section_s3.py` 自动生成：GLM 死 12%、每题 7.7s，增益 +0.24；Qwen 死 93%、死时仅拿到 1.2 件，增益 +5.94；DeepSeek +8.61、MiMo +9.29。护栏救的是"已经做完的工作"，Qwen 根本没走到那一步。

## 终稿前的必做检查（数字变了要改正文）

1. `paper/main.md` §6 Discussion 现在写着 "`I1` … moved the score by nothing" 与 "`C` and `E` … moved it by eight points"。全量数据下 I1−I0 已显著为负（−3.93 [−5.37, −2.61]），E−I0 为 +6.0。这两句必须按最终数字重写：信息不是中性装饰，而是没有帮助甚至有害。
2. §6 "Who sets the threshold matters less than that it is set" 段落里 "the two are indistinguishable" 对应 C−E = −1.33 [−3.77, +0.80]，要按最终区间重述。
3. 摘要里的 [S3 ABSTRACT RESULT]、[S3 SUMMARY]、[S3 CLAIM] 三处占位符由 `scripts/fill_paper_placeholders.py` 填，填完要读一遍是否与 §5.4/§5.5 一致。
4. Table 7–10 与 fig6/fig7 都从 `stats_summary.json` + `latency_by_model.json` 生成，终稿前重跑 `assemble_paper_s3` 即可；fig6/fig7 已改为经 `load()` 读入归档中断条目，堆叠和恒为 1.0。

## 恢复命令

```bash
cd /Users/atlas/Programs/codex_programs/time-agent
rm -f runs/s3-A-20261102T094306204655Z/run_lock.json
nohup .venv/bin/python scripts/supervise.py runs/s3-A-20261102T094306204655Z \
  --module scripts.study3 --continue-module scripts.study3_continue --max-restarts 80 > /tmp/s3formal.log 2>&1 &
```

跑满后出终稿：

```bash
.venv/bin/python -m scripts.assemble_paper_s3 runs/s3-A-20261102T094306204655Z
```

## 关键文件

- 论文：paper/main.md（正文，4 个 S3 占位符）、paper/main_preliminary.md + paper/preliminary_draft.docx（已填数初稿）
- 代码：tasks/data_v7.py、src/runner_v4.py、src/time_policies.py、scripts/study3.py、scripts/study3_stats.py、scripts/supervise.py
- 记录：docs/S3实验方案_20261102.md、docs/执行记录S3_20261102.md

## 2026-11-03 17:20 凭据失效事故（已处理）

- 旧 key 在 16:47 被吊销：所有模型 HTTP 401，冻结的 runner 把 401 记成 score-0 的 `service_error` 行，而 `halt.set()` 让子进程每 5 秒退出一次，supervisor 热循环重启 → 两分钟内写进 104 条垃圾 episode，并在 `journals/` 留下同名文件。
- 处理：`scripts/quarantine_auth_failures.py` 把 104 条 episode + started 标记 + journal 原样移到 `invalid_service_auth/`（含 MANIFEST.json），使驱动把它们当未启动重跑；旧 key 备份在 `.env.bak.20261103`。
- 防复发：`scripts/study3_continue.py` 增加 `preflight_auth()`（401/403 直接写 AUTH_FAILED.json 并以 2 退出，不再跑第一个 episode）；`scripts/supervise.py` 增加"连续 3 次重启无新增 episode 就写 STOP_SUPERVISOR 退出"的保护。
- 注意：`study3.analyze()` 把 started-无-episode 计为 environment_interruption（0 分）。只有**启动后真的没有 episode**的才是；401 的 104 条必须隔离，不能留。

## 已知约束

- 批次有源码哈希守卫：运行期不能改 src/tasks/scripts 里列进 CODE_PATHS 的文件，否则 "batch code/config/manifest changed"。`scripts/study3_continue.py`、`scripts/supervise.py`、`scripts/quarantine_auth_failures.py`、`scripts/study3_stats.py` 不在冻结集内。
- 宿主机易休眠：必须用 `caffeinate -dims -u` + pinger（`-s` 才提供 PreventSystemSleep）。
- 端口 8080（China Telecom Router）与 fetch 的 Host 头匹配，与 S3 无关。
