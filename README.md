# time-agent · Agent 时间预算实验

项目研究智能体如何在现实时间截止前停止并交付。S1、S2 和 S3 阶段 A 已收尾。S3 的 7,040 个计划条目均有记录，4,757 条纳入分析。异质任务中，框架执行预留策略 E 相对基线 I0 平均多交付 **6.13 分**，95% 区间 **[+5.20, +7.01]**。

- [当前进度、三轮结果与资料导航](doc/README.md)
- [HTML 入门教程](doc/time_agent_beginner_guide_20261104.html)，下载后在浏览器打开
- [完整实验记录归档与恢复](archive/README.md)
- [论文工作稿](paper/main.md)与 [Word 版本](paper/latency_summaries_paper.docx)
- [S3 终态统计 JSON](reports/s3_final_20261106/stats_summary.json)

<details>
<summary>展开早期 README 和历史运行说明</summary>

以下内容保留当时的进度与运行说明。


本项目包含两轮受控实验，研究“把工具耗时告诉智能体”是否改变其在墙钟预算下的行为。

## 第二轮（S2，2026-11-02）：有决策杠杆的截止预算任务

S1 的零结果被归因于设计：v4 任务的正确路径唯一（收集全部必需行后提交），延迟估计不改变最优动作；且历史里已经逐条给出 `duration_s`，摘要只是把已有数据再算一遍。S2 重建了环境，使停止动作有代价也有效用。

- 环境：20 个不透明编号、200 s 预算、单一 `fetch` 工具、**部分计分**、宿主结算的无载荷 `submit`。继续取数增加得分，停止保住得分，因此“下一次调用要花多久”决定最优停止点。
- 条件（唯一差别是 observation 中一个字段）：A 无参考；B 开局校准的固定先验；C 最近一次完整调用耗时；O 宿主当前实际施加的耗时（完美瞬时预言机，信息上界）。
- 剖面：`stable_fast`（8 s）、`fast_to_slow`（30% 处 8→60 s）、`drift_up`（8→60 s 几何漂移，最近一次观测总是低估下一次）。
- 规模：3 模型 × 12 任务 × 3 剖面 × 4 条件 = 432 条，每模型并发 2。

结果：432/432 闭合（426 条有效 + 6 条宿主休眠环境失败）。主指标 `drift_up` 的 C−B 为 **−0.36 个物品，95% 区间 [−1.11, +0.42]，p = 0.44**；9 个预注册对比中没有一个显示收益。同期参考值误差为 8.0 s（B）、3.6 s（C）、1.5 s（O），而真实工具耗时从 8 s 漂移到 60 s——信息确实变了，行为没变：四个条件的停止阈值在 54.9–62.0 s 之间。给 B 先验时理性规划器只能取 2.0–2.3 个物品，而实际智能体取到 1.8–7.0，与只依赖“最近一次观测”的规划器同量级。

预注册方案见 [S2 预注册](docs/S2预注册方案_20261102.md)，执行记录（含 4 条 pilot 与一次作废批次）见 [S2 执行记录](docs/执行记录S2_20261102.md)，论文稿见 [paper/main.md](paper/main.md) 与 [paper/latency_summaries_paper.docx](paper/latency_summaries_paper.docx)。

入口：

```bash
.venv/bin/python -m scripts.study2 prepare formal --tasks-limit 12
/usr/bin/caffeinate -i .venv/bin/python -m scripts.study2 run runs/s2-formal-<stamp>
.venv/bin/python -m scripts.study2_stats runs/s2-formal-<stamp>
.venv/bin/python -m scripts.paper_figures --s2-batch runs/s2-formal-<stamp> \
    --s2-summary runs/s2-formal-<stamp>/stats_summary.json
```

`run` 支持 `--resume`：宿主休眠导致的已启动未完成条目按环境失败归档并计 0，不重跑、不删除。

## 第一轮（S1）：三模型 Go API 工具延迟实验

## 当前文档入口（2026-11-01）

- [实验最终报告](docs/实验最终报告_20261101.md)：主要配对区间、次要指标、探针、运行中断与后续计划。
- [最终验收清单](docs/最终交付验收清单_20261101.md)：逐项证据与边界。

- [三模型实际执行记录](docs/执行记录_20261030.md)：首轮开发 216 次、171 正确；SSE 开发停止于 192/216。连续钟及证据提示修订后的诊断 18/18 全部正确，新完整开发 216/216、166 正确且准入通过，正式1080次与144次探针均已完成。

- [Agent 构造说明](docs/Agent构造说明.md)：按当前 Go 链路及保留的历史 v5 介绍组件、动作协议、状态、时间控制、工具、评分和实现限制。
- [基于现有数据的后续实验计划](docs/后续实验计划_20261030.md)：复核 v2–v5 数据，定义研究目标、分阶段矩阵、开发门槛、指标和可能结论；已分阶段执行，完整结果及后续提议见最终报告。
- [开发数据汇总快照](reports/experiment_data_snapshot_20261030.json)：从现有配置、清单及结果重新统计，保留各批次分母和变化暴露口径。
- [OpenCode Go 接入建议](reports/opencode_go_experiment_proposal_20261030.md)：API 与 agent 路线比较；具体后续安排以以上实验计划为准。

历史 CLI 候选入口为 `scripts/run_v5_pilot.py`，使用 v4 任务、`runner_v2` 和仍要求 Windows 的 `CodexMXCV2`；旧正式入口尚未接上这条流水线。下文早期开发进展按历史保留，不能据此认定 Go API、多模型正式运行或跨平台隔离已经完成。

### Go API 实际执行入口

Go 入口现为 `scripts/go_study.py → runner_v2 → OpenCodeGo`；以上 v5 指历史 CLI 候选。首轮完整 Go 开发 `runs/go-development-20261030T131526625261Z` 已完成 216 次、171 次正确，未通过准入；此历史批次不并入新结果。连续钟与证据提示修订后的完整开发 `runs/go-development-20261031T025535202037Z` 已完成并通过；正式批次 `runs/go-formal-20261031T041031911245Z` 已1080/1080完成，902次成功。

使用 Python 3.13 和 `requirements.txt`。密钥由宿主从 `OPENCODE_GO_API_KEY` 或被忽略的项目 `.env` 读取，禁止写入命令行参数、实验配置和日志。采样后报告修复已改变当前源码哈希；旧批次不可直接用go_study执行入口续跑，也不得修改快照。归档只读分析命令示例：

```bash
# 仅离线分析；输出目录必须尚不存在。加载时验证归档源码及冻结配置。
.venv/bin/python -m scripts.publish_study_report runs/go-formal-20261031T041031911245Z --output /private/tmp/time-agent-formal-reproduction
.venv/bin/python -m scripts.environment_sensitivity runs/go-formal-20261031T041031911245Z --review reports/go_environment_resume-20261101T072557784168Z/review.json --output /private/tmp/time-agent-environment-reproduction.json
```

`prepare development` 要求诊断和离线验证证据；`prepare formal` 还要求完整开发全部准入检查通过。不要重复启动同一正在运行的批次；状态文件不是进程存活证明，应核对真实句柄。详细参数、源码快照和既有失败见执行记录。

## 历史 CLI 环境与命令

使用 Python 3.13；核心代码仅使用标准库。Codex CLI 需可执行、登录并允许使用 `gpt-6-luna`。在本机受限沙箱中 asyncio 事件循环不能初始化；测试和诊断需在允许异步运行及访问 Codex 的环境执行。

```powershell
python -m tasks.generate
python -m unittest discover -s tests -v
python -m scripts.run_diagnostic
```

生成器会重写相同种子的任务文件；不要将它用于覆盖已经冻结的数据。诊断每次新建 `runs/diagnostic-<UTC>`，依次尝试每类 1 道开发题（失败时停止），配置为条件 C、stable_fast、120 秒；每个工具并发采样 3 次实际调用及注入等待作为初始诊断参考。结果记录在该目录，密钥不写入代码。测试集与答案分开存储；仅题面与工具返回值应被送入模型。

## 方法和解释

计时覆盖模型调用、工具计算和异步注入等待；动作完整到达之后才可判定提交。延迟由工具开始时的墙钟阶段决定；A 不提供摘要，B 使用初始均值，C 使用最近最多三条已完成同类工具调用。结果和每轮模型可见状态保存在轨迹中；完整提交先于截止才评分。不得把此诊断视为正式 A/B/C 比较。

Codex CLI 带有自身系统指令与工具；本适配器禁止并检测额外工具调用，但只读沙箱不能保证阻止对外部路径的读取，检测也不能在工具执行前保证阻断。因此 CLI 结果仅供开发诊断；正式运行前需要独立验证文件、网络隔离和统一协议。CLI 每次决策启动新进程，启动时间计入预算，可能影响与其他 API 模型的可比性。CLI 版本、访问方式和模型参数都需在正式运行前登记。

## 后续流程与未完成事项

1. 对每个工具实际独立采样预校准，增加模拟模型成功、恢复和隔离检查；完善任务类型多样性，人工复核每类至少 3 题。
2. 修复隔离后，在每类 1 题进行协议检查，随后跑完整开发集、检查变化可观察性和时间预算；不得依据测试集结果调参。
3. 明确所有模型版本、接口、协议、资源限制和费用上限，保存提示、配置和哈希，建立随机化配对 manifest；冻结后再运行正式测试。
4. 实现无覆盖的断点恢复、完整批次运行、聚类配对 bootstrap、图表和中文结果报告，并保留全部失败。

正式批次入口仍受隔离验证阻断；统计与报告工具已有雏形，图表尚未完成；也未接入 DeepSeek、Terra 或 GLM。任务模板目前主要是聚合运算变化，不足以认定五种实质不同的推理结构。详见 [研究方案](Agent工具延迟变化与时间预算适应_实验执行方案.md) 和 [近邻工作核查](reports/related_work.md)。

## 2026-10-29 开发进展

候选任务 v2 位于 `tasks/data_v2.py`，与 v1 数据和轨迹独立，随机化证据 ID 与表格行顺序；目前还没有冻结。`python -m scripts.run_diagnostic` 现在使用 v2。开发批次入口是 `python -m scripts.run_development`；最多 72 条、单模型串行、各条件一次重复，仅用于开发，服务故障或额外工具事件会中止。每条正在执行的轨迹以追加 JSONL 逐事件写入 `journals/`，完成后单独保存 JSON；续跑前使用 `python -m scripts.resume_development_safe <批次目录>` 检查配置与记录；已启动但未完成的条目不会自动重跑。`python -m scripts.analyze_development <批次目录>` 生成描述性统计。

批次冻结、验证及不覆盖式恢复的底层接口位于 `scripts/matrix.py`；`scripts/analyze_matrix.py` 支持配对簇 bootstrap，但尚未接成正式运行入口。正式运行必须先核验隔离、人工复核并冻结模型和配置。旧版部分批次状态见 `reports/development_v1_partial.md`，不得与新任务混合。



## 完整 Luna 开发批次

`runs/development-20261029T082822321141Z` 已完成 72/72 条，最终报告见 `reports/luna_development_final.md`。这是探索性开发数据：62 条截止前正确；变化模式 48 条中仅 21 条在变化反馈后有后续决策，其中表格题 0/24。正式测试尚未运行，应先处理变化暴露、CLI 错误/截止记录以及端到端隔离验证。72 条轨迹与中途恢复复核均已保留。

</details>
