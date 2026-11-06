# 项目状态

2026-11-06 更新。S3 阶段 A 已收尾，全部 7,040 个计划运行 ID 都有结果文件。4,757 条用于去重后复算，2,283 条服务错误单独归档。S3 主对比为 +6.13 分，95% 区间 [+5.20, +7.01]。

见[终态核对和资料索引](doc/README.md)。后续查看优先使用[复算结果](reports/s3_final_20261106/stats_summary.json)和[实验归档](archive/README.md)。

<details>
<summary>展开 2026-11-04 的历史交接记录</summary>

以下记录保留当时的数字和操作步骤。


更新时间：2026-11-04 18:10

## 目标

完成 S3 实验并产出可投稿 SCI Q2 / CCF-B 的论文，整合 S1（信息接口无效）、S2（接口改变被告知的估计，没改变实际用的估计）、S3（信息是装饰，执行才是约束）。

## 三个研究

| 研究 | 批次 | 规模 | 状态 |
|---|---|---|---|
| S1 | runs/go-formal-20261031T041031911245Z | 1,080 | 完成，零结果 |
| S2 | runs/s2-formal-20261102T035658599154Z | 432 | 完成（426 计分 + 6 环境失败） |
| S3 | runs/s3-A-20261102T094306204655Z | 7,040 | **已结束**：7,040 条全有记录，4,757 可观测（2,283 计费拒绝已排除；87 条已补跑） |

## S3 现状（2026-11-04 17:20 终态）

- **实验已结束，不再有进程**。7,040 条全部有 episode 记录（87 条通过派生批次补跑），僵尸 started 标记已清零。
- **重大数据修正**：2,283 条（33%）的 `termination_reason = service_error`，原因是供应商把请求从套餐额度（`billing_source: go`）切到余额计费（`balance`），适配器按策略拒绝付费请求，模型根本没被调用。这些 episode 不含任何行为，**已从分析中排除**（`scripts/study3_stats.py` 的 `load()` 与 `scripts/study3_metrics.py` 同步过滤），不是计 0。拒绝比例在五臂上一致（33% 对 33%），拒绝只整块吞掉 cell，不偏向任何一臂（各臂 32%）。
- **补跑（2026-11-04 17:28–18:00）**：`scripts/study3_topup.py` 在派生批次 `runs/s3-T-20261104T092802121223Z` 里重跑了 86 条从未起跑的条目，执行完把 86 个 episode 与 journal 移回主批次。适配器加了 `TIME_AGENT_ALLOW_PAID_BILLING=1` 开关（默认关闭，行为不变），因此派生批次有自己的 config/code_hash。结果：submitted 14、forced_submit 47、timeout_model 22、timeout_tool 3，无 service_error。补跑后 64 个 (task, regime) 格子全部五臂齐全（此前只有 49 个），配对样本从 49 对增至 64 对。
- 终值（hetero，全区制，n=4,757）：E−I0 = **+6.10** [+5.20, +6.98] p=0.0005；I1−I0 **−2.94** [−3.85, −1.94]；C−I0 +5.52 [+4.29, +6.85]；C−E −0.58 [−1.88, +0.67]（跨零）；E−O −0.64（跨零）；O−I0 +6.74。uniform：E−I0 +2.41 [1.88, 2.88]、I1−I0 −0.03（≈0）。
- 论文已重出：§5.4 开头写明"7,040 全部有记录 / 4,757 可观测 / 8 条休眠 / 2,283 条被拒并排除 / 64 个格子全满"，docx 已重建（593,190 字节）。
- 估计量已修正（2026-11-03 17:40）：`scripts/study3_stats.py` 的 `_paired()` 原先把每个 (model, task, arm) 格子的 2–3 次 repeat 静默压成"最后写入的那一条"。改为格子内先对 repeat 取均值再配对。
- 中期数（2,166 条）：E−I0 = **+5.74** [4.44, 7.14]（hetero，全区制）；I1−I0 = **−3.70** [−6.04, −1.95]；C−I0 = +5.16、C−E = −0.58、E−O = −0.67。
- `light_tail` 负对照**仍不成立**（E−I0 = +7.69 [4.75, 10.34]，四个区制里最大）——真实尾部来自模型自身请求延迟，不是工具耗时。
- 提交率 I0 43% / I1 34% / C 78% / E 90% / O 89%；I0/I1 超时率 42%/51%，三个强制臂 3–15%。
- **I1 为何更差仍是未解机制**：调用数、取的物品、请求时长（p50 11.3 vs 11.2 s）、按步序分层后的请求耗时都一致，唯独提交率掉 9 个点。已在 §5.4 与 §6 明确写成"报告成本、不声称机制"。
- 执行史：740 / 934 / 1,404 / 1,637 四次暂停，2026-11-03 17:20 发生凭据失效事故（见文末），17:22 修复后连续运行至今。

## 运行拓扑（2026-11-03 21:00 起）

- **launchd** `com.timeagent.s3watch`（`~/Library/LaunchAgents/com.timeagent.s3watch.plist`，StartInterval 600）每 10 分钟跑一次 `scripts/watch_supervisor.py <batch> 600 --once`：supervisor 不在就重启；遇 `STOP_SUPERVISOR` / `AUTH_FAILED.json` 则什么都不做；批次跑满则自动执行 `assemble_paper_s3` 并写 `AUTO_ASSEMBLED` 标记。
- supervisor（`scripts/supervise.py`）负责拉起 `scripts.study3_continue`；`caffeinate -dims -u` 防休眠。
- 手动杀掉那个常驻 watchdog 进程，避免和 launchd 双重管理；**要暂停批次，先 `launchctl bootout gui/$(id -u)/com.timeagent.s3watch`，再停 supervisor**。
- 日志：`/tmp/s3formal.log`（supervisor）、`/tmp/s3formal_watch.log`（重启）、`/tmp/s3watch_launchd.log`（launchd）、`/tmp/s3_auto_assemble.log`（自动出稿）。

## 论文管线（一条命令、可重复）

```bash
.venv/bin/python -m scripts.assemble_paper_s3 runs/s3-A-20261102T094306204655Z
```

依次执行 `study3_stats → study3_latency → study3_decisions → paper_results_section_s3 → paper_figures → 用 paper/main_template.md 重建 paper/main.md（填 [S3 RESULTS]）→ fill_paper_placeholders（填摘要/总结/贡献与集数）→ build_paper_docx`。

- `paper/main_template.md` 是唯一源文件（保留全部占位符）；`paper/main.md` 与 `paper/latency_summaries_paper.docx` 都是生成物。
- 9 张图全部嵌入：fig1–5（S1/S2）、fig6 各臂得分、fig7 结束方式、fig8 决策时刻、fig9 区制效应。

## 收尾步骤（批次跑完后按顺序执行）

驱动只认识"有 `started/` 标记"这一件事：被强杀时留下的标记永远不再重跑，而 `analyze()` 会把它们当成 0 分的 `environment_interruption`。截至 23:45 有 **86 条**这种僵尸标记（11-02 20:18 的 8 条、21:xx 的 22 条、22:xx 的 8 条，11-03 10/15/16/17 点的 8/8/8/24 条），臂分布 C19/E19/I0 15/I1 16/O 17——I0/I1 因为单局更长而更容易被砍，直接留在矩阵里会轻度低估 I0/I1。

```bash
# 1. 把僵尸标记连同同名 journal 挪到 retired_*（--min-age-s 默认 1800，只动确定废弃的）
.venv/bin/python -m scripts.study3_repair runs/s3-A-20261102T094306204655Z --apply
# 2. 补跑这 86 条（约 30–40 分钟，_continue 会重新调度它们）
.venv/bin/python -m scripts.study3_continue runs/s3-A-20261102T094306204655Z
# 3. 确认没有残留标记
.venv/bin/python -m scripts.study3_repair runs/s3-A-20261102T094306204655Z
# 4. 出终稿
.venv/bin/python -m scripts.assemble_paper_s3 runs/s3-A-20261102T094306204655Z
```

注意：因为存在这些僵尸标记，驱动跑完剩余条目后会认为"没有进展"并写 `STOP_SUPERVISOR` 退出，launchd 不会自动出稿——这是预期行为，收尾必须由上面四步完成。

## 终稿前的必做检查

1. 重跑 `assemble_paper_s3` 后，通读 §5.4、§5.5、§6 与摘要，确认与最终数字一致（所有对比措辞已按 CI 符号自适应，但仍要人眼过一遍）。
2. 若跑满前定稿，§5.3 的 "7,040 episodes planned; N were completed and scored" 会自动填 N，务必确认没有把部分数据说成完整矩阵。
3. `sensitivity()` 的"计 0 / 整对删除"两口径差异若在终稿超过 0.3 分，要在 Limitations 里说明。
4. I1 的负效应若到全量仍显著，讨论里保留"未解机制"的表述，不要编故事。

## 恢复命令

```bash
cd /Users/atlas/Programs/codex_programs/time-agent
launchctl bootout gui/$(id -u)/com.timeagent.s3watch 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.timeagent.s3watch.plist
rm -f runs/s3-A-20261102T094306204655Z/run_lock.json
nohup .venv/bin/python scripts/supervise.py runs/s3-A-20261102T094306204655Z \
  --module scripts.study3 --continue-module scripts.study3_continue --max-restarts 80 > /tmp/s3formal.log 2>&1 &
```

## 关键文件

- 论文：paper/main_template.md（源）、paper/main.md（生成）、paper/latency_summaries_paper.docx（生成）、paper/preliminary_draft.docx（1,637 条时的可读初稿）
- 实验：tasks/data_v7.py、src/runner_v4.py、src/time_policies.py、scripts/study3.py、scripts/study3_continue.py、scripts/supervise.py
- 分析：scripts/study3_stats.py、scripts/study3_latency.py、scripts/study3_decisions.py、scripts/paper_results_section_s3.py、scripts/paper_figures.py
- 记录：docs/S3实验方案_20261102.md、docs/执行记录S3_20261102.md、docs/S3_中期分析_20261103.md

## 2026-11-03 17:20 凭据失效事故（已处理）

- 旧 key 在 16:47 被吊销：所有模型 HTTP 401，冻结的 runner 把 401 记成 score-0 的 `service_error` 行，而 `halt.set()` 让子进程每 5 秒退出一次，supervisor 热循环重启 → 两分钟内写进 104 条垃圾 episode，并在 `journals/` 留下同名文件。
- 处理：`scripts/quarantine_auth_failures.py` 把 104 条 episode + started 标记 + journal 原样移到 `invalid_service_auth/`（含 MANIFEST.json），使驱动把它们当未启动重跑；旧 key 备份在 `.env.bak.20261103`。
- 防复发：`scripts/study3_continue.py` 的 `preflight_auth()`（401/403 直接写 AUTH_FAILED.json 并以 2 退出）；`scripts/supervise.py` 的"连续 3 次重启无新增 episode 就写 STOP_SUPERVISOR 退出"。
- 注意：`study3.analyze()` 把 started-无-episode 计为 environment_interruption（0 分）。只有**启动后真的没有 episode**的才是；401 的 104 条必须隔离，不能留。

## 已知约束

- 批次有源码哈希守卫：运行期不能改 src/tasks/scripts 里列进 CODE_PATHS 的文件，否则 "batch code/config/manifest changed"。`scripts/study3_continue.py`、`scripts/supervise.py`、`scripts/study3_stats.py`、`scripts/study3_latency.py`、`scripts/study3_decisions.py`、`scripts/watch_supervisor.py` 不在冻结集内。
- 宿主机易休眠：必须用 `caffeinate -dims -u` + pinger（`-s` 才提供 PreventSystemSleep）。
- 判定"已停"不能只看 `ps aux | grep '[s]tudy3'`，要三重确认：`pgrep -f scripts/supervise.py` 无输出、episode 计数 60 秒不变、`runtime_state.pid` 不存活。

</details>
