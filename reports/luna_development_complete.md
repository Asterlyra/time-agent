# Luna 开发批次描述性报告

生成时间（UTC）：2026-10-29T09:56:24.778851+00:00
批次：`runs/development-20261029T082822321141Z`；模型：`gpt-6-luna`。

**仅为探索性开发数据，不是冻结后的正式实验，也不能用于推断条件效果。**

计划 72 条，已启动 72 条，已有结果 72 条，已启动未完成 0 条，尚未启动 0 条。
有结果但缺少启动标记：0 条。分析脚本的未完成数 0 包含已启动未完成和未启动。

每行成功率的分母是该行**已有结果**的 episode，未启动或尚未结束的不在该分母中。未完成批次的不同条件分母和任务可能不平衡。

| 延迟模式 | 条件 | 任务类 | 计划 | 已启动 | 已有结果 | 截止前正确 |
|---|---|---|---:|---:|---:|---:|
| fast_to_slow | A | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| fast_to_slow | A | table | 4 | 4 | 4 | 4/4 (100.0%) |
| fast_to_slow | B | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| fast_to_slow | B | table | 4 | 4 | 4 | 3/4 (75.0%) |
| fast_to_slow | C | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| fast_to_slow | C | table | 4 | 4 | 4 | 4/4 (100.0%) |
| slow_to_fast | A | evidence | 4 | 4 | 4 | 1/4 (25.0%) |
| slow_to_fast | A | table | 4 | 4 | 4 | 4/4 (100.0%) |
| slow_to_fast | B | evidence | 4 | 4 | 4 | 3/4 (75.0%) |
| slow_to_fast | B | table | 4 | 4 | 4 | 3/4 (75.0%) |
| slow_to_fast | C | evidence | 4 | 4 | 4 | 3/4 (75.0%) |
| slow_to_fast | C | table | 4 | 4 | 4 | 4/4 (100.0%) |
| stable_fast | A | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| stable_fast | A | table | 4 | 4 | 4 | 2/4 (50.0%) |
| stable_fast | B | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| stable_fast | B | table | 4 | 4 | 4 | 4/4 (100.0%) |
| stable_fast | C | evidence | 4 | 4 | 4 | 4/4 (100.0%) |
| stable_fast | C | table | 4 | 4 | 4 | 3/4 (75.0%) |

## 终止原因

| 原因 | 数量 | 分母 |
|---|---:|---:|
| protocol_violation | 1 | 72 |
| submitted | 66 | 72 |
| timeout_model | 5 | 72 |

## 延迟变化可观察性

“观察变化”表示在变化点后开始的一次工具调用已完成并返回；“之后有决策”要求随后发出过模型请求。稳定快模式没有变化，记为不适用。该子集由模型行为决定，仅供描述。

| 延迟模式 | 条件 | 任务类 | 已有结果 | 观察变化 | 观察后有决策 |
|---|---|---|---:|---:|---:|
| fast_to_slow | A | evidence | 4 | 3 | 3 |
| fast_to_slow | A | table | 4 | 0 | 0 |
| fast_to_slow | B | evidence | 4 | 3 | 3 |
| fast_to_slow | B | table | 4 | 0 | 0 |
| fast_to_slow | C | evidence | 4 | 3 | 3 |
| fast_to_slow | C | table | 4 | 0 | 0 |
| slow_to_fast | A | evidence | 4 | 4 | 4 |
| slow_to_fast | A | table | 4 | 0 | 0 |
| slow_to_fast | B | evidence | 4 | 4 | 4 |
| slow_to_fast | B | table | 4 | 0 | 0 |
| slow_to_fast | C | evidence | 4 | 4 | 4 |
| slow_to_fast | C | table | 4 | 0 | 0 |
| stable_fast | A | evidence | 4 | — | — |
| stable_fast | A | table | 4 | — | — |
| stable_fast | B | evidence | 4 | — | — |
| stable_fast | B | table | 4 | — | — |
| stable_fast | C | evidence | 4 | — | — |
| stable_fast | C | table | 4 | — | — |

## 代表轨迹

本报告使用的选择规则（未在运行前预注册）：在相同模型、任务、延迟模式及重复编号的完整 B/C 配对中，按任务及配对键排序；每种 C/B 成败组合取第一组。不存在时明确标注。失败包含所有非成功终止，不能推断其原因相同。

### C/B 成功/失败

任务 `dev-table-03`；模式 `fast_to_slow`；重复 `0`。
- B：`7a5087c947f01eec8c994086`，终止 `submitted`，耗时 20.7 秒；4.8s lookup_rows(完成)；13.3s lookup_rows(完成)；20.7s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/7a5087c947f01eec8c994086.json)
- C：`7d77af27dcfc8717f1ea3f3a`，终止 `submitted`，耗时 31.0 秒；5.3s lookup_rows(完成)；21.4s lookup_rows(完成)；31.0s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/7d77af27dcfc8717f1ea3f3a.json)

### C/B 失败/成功

任务 `dev-table-00`；模式 `stable_fast`；重复 `0`。
- B：`b86e4204bf79f93d97710afa`，终止 `submitted`，耗时 26.4 秒；10.5s lookup_rows(完成)；18.1s lookup_rows(完成)；26.4s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/b86e4204bf79f93d97710afa.json)
- C：`f52cc43e1465a1ddfc51db66`，终止 `submitted`，耗时 22.4 秒；5.8s lookup_rows(完成)；14.1s lookup_rows(完成)；22.4s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/f52cc43e1465a1ddfc51db66.json)

### C/B 失败/失败

任务 `dev-evidence-02`；模式 `slow_to_fast`；重复 `0`。
- B：`77ba0ca47884ca56078e523d`，终止 `timeout_model`，耗时 120.4 秒；6.8s search(完成)；29.3s search(完成)；54.0s search(完成)；77.4s read_document(完成)；85.9s search(完成)；95.0s read_document(完成)；107.2s search(完成)；115.6s read_document(完成)。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/77ba0ca47884ca56078e523d.json)
- C：`dfdb8ba9707a16a38fdb3bf1`，终止 `timeout_model`，耗时 120.4 秒；8.1s search(完成)；29.8s search(完成)；53.6s search(完成)；75.6s read_document(完成)；85.4s search(完成)；95.9s read_document(完成)；104.2s search(完成)；113.9s read_document(完成)。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/dfdb8ba9707a16a38fdb3bf1.json)

### C/B 成功/成功

任务 `dev-evidence-00`；模式 `fast_to_slow`；重复 `0`。
- B：`4deeb6a054ac9d9e2bd408ae`，终止 `submitted`，耗时 116.5 秒；6.2s search(完成)；17.7s search(完成)；25.0s search(完成)；34.8s search(完成)；45.2s search(完成)；54.1s read_document(完成)；61.8s read_document(完成)；83.3s read_document(完成)；105.4s 提交；111.0s 提交；116.5s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/4deeb6a054ac9d9e2bd408ae.json)
- C：`7524f354c860fa59d9876e61`，终止 `submitted`，耗时 118.6 秒；8.7s search(完成)；19.2s search(完成)；26.9s search(完成)；35.6s search(完成)；53.5s read_document(完成)；67.5s read_document(完成)；97.6s read_document(完成)；118.6s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T082822321141Z/episodes/7524f354c860fa59d9876e61.json)

## 局限

- 单一模型、开发集、小样本及可能尚未完成的批次；结果不能推广或作为 C 对 B 的正式比较。
- CLI 自带指令及工具与其他模型接口不同；当前措施不足以证明操作系统级文件/网络隔离。
- 每次决策启动 CLI 进程，启动及推理时间计入预算；token 和费用字段若未知为 null。
- 任务模板的信息结构与行、证据 ID 规律存在局限，变化点前完成的任务不应排除。
- 并发预校准样本可能相关，人工复核与冻结配置尚未完成。
- 无正式配对 bootstrap、假设检验或效果结论。

本环境未检测到 matplotlib；本报告不生成图。上述表格保留原始分母。
