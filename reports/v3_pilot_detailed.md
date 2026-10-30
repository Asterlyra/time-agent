# Luna 开发批次描述性报告

生成时间（UTC）：2026-10-29T15:09:21.475639+00:00
批次：`runs/v3-pilot-20261029T142119806339Z`；模型：`gpt-6-luna`。

**仅为探索性开发数据，不是冻结后的正式实验，也不能用于推断条件效果。**

计划 18 条，已启动 18 条，已有结果 18 条，已启动未完成 0 条，尚未启动 0 条。
有结果但缺少启动标记：0 条。分析脚本的未完成数 0 包含已启动未完成和未启动。

每行成功率的分母是该行**已有结果**的 episode，未启动或尚未结束的不在该分母中。未完成批次的不同条件分母和任务可能不平衡。

| 延迟模式 | 条件 | 任务类 | 计划 | 已启动 | 已有结果 | 截止前正确 |
|---|---|---|---:|---:|---:|---:|
| fast_to_slow | A | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| fast_to_slow | A | table | 1 | 1 | 1 | 1/1 (100.0%) |
| fast_to_slow | B | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| fast_to_slow | B | table | 1 | 1 | 1 | 1/1 (100.0%) |
| fast_to_slow | C | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| fast_to_slow | C | table | 1 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | A | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| slow_to_fast | A | table | 1 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | B | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| slow_to_fast | B | table | 1 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | C | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| slow_to_fast | C | table | 1 | 1 | 1 | 0/1 (0.0%) |
| stable_fast | A | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| stable_fast | A | table | 1 | 1 | 1 | 1/1 (100.0%) |
| stable_fast | B | evidence | 1 | 1 | 1 | 1/1 (100.0%) |
| stable_fast | B | table | 1 | 1 | 1 | 1/1 (100.0%) |
| stable_fast | C | evidence | 1 | 1 | 1 | 0/1 (0.0%) |
| stable_fast | C | table | 1 | 1 | 1 | 0/1 (0.0%) |

## 终止原因

| 原因 | 数量 | 分母 |
|---|---:|---:|
| submitted | 10 | 18 |
| timeout_model | 4 | 18 |
| timeout_tool | 4 | 18 |

## 延迟变化可观察性

“观察变化”表示在变化点后开始的一次工具调用已完成并返回；“之后有决策”要求随后发出过模型请求。稳定快模式没有变化，记为不适用。该子集由模型行为决定，仅供描述。

| 延迟模式 | 条件 | 任务类 | 已有结果 | 观察变化 | 观察后有决策 |
|---|---|---|---:|---:|---:|
| fast_to_slow | A | evidence | 1 | 1 | 1 |
| fast_to_slow | A | table | 1 | 1 | 1 |
| fast_to_slow | B | evidence | 1 | 1 | 1 |
| fast_to_slow | B | table | 1 | 1 | 1 |
| fast_to_slow | C | evidence | 1 | 1 | 1 |
| fast_to_slow | C | table | 1 | 1 | 1 |
| slow_to_fast | A | evidence | 1 | 1 | 1 |
| slow_to_fast | A | table | 1 | 1 | 1 |
| slow_to_fast | B | evidence | 1 | 1 | 1 |
| slow_to_fast | B | table | 1 | 1 | 1 |
| slow_to_fast | C | evidence | 1 | 1 | 1 |
| slow_to_fast | C | table | 1 | 1 | 1 |
| stable_fast | A | evidence | 1 | — | — |
| stable_fast | A | table | 1 | — | — |
| stable_fast | B | evidence | 1 | — | — |
| stable_fast | B | table | 1 | — | — |
| stable_fast | C | evidence | 1 | — | — |
| stable_fast | C | table | 1 | — | — |

## 代表轨迹

本报告使用的选择规则（未在运行前预注册）：在相同模型、任务、延迟模式及重复编号的完整 B/C 配对中，按任务及配对键排序；每种 C/B 成败组合取第一组。不存在时明确标注。失败包含所有非成功终止，不能推断其原因相同。

### C/B 成功/失败

当前快照没有符合条件的完整配对。

### C/B 失败/成功

任务 `dev-evidence-00`；模式 `stable_fast`；重复 `0`。
- B：`7725dd00e51462b98ca14d61`，终止 `submitted`，耗时 101.1 秒；10.5s search(完成)；24.6s search(完成)；37.3s search(完成)；47.8s search(完成)；57.0s read_document(完成)；67.5s read_document(完成)；85.7s read_document(完成)；101.1s 有效提交。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/7725dd00e51462b98ca14d61.json)
- C：`a30e7236dfdfb7e6119d1404`，终止 `timeout_tool`，耗时 120.0 秒；14.3s search(完成)；25.2s search(完成)；36.4s search(完成)；50.8s search(完成)；64.4s 无效提交尝试；75.4s read_document(完成)；90.1s read_document(完成)；104.5s search(完成)；118.1s read_document(删失)。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/a30e7236dfdfb7e6119d1404.json)

### C/B 失败/失败

任务 `dev-evidence-00`；模式 `fast_to_slow`；重复 `0`。
- B：`4deeb6a054ac9d9e2bd408ae`，终止 `timeout_tool`，耗时 120.0 秒；19.2s search(完成)；36.2s search(完成)；58.8s search(完成)；81.7s search(完成)；105.8s read_document(删失)。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/4deeb6a054ac9d9e2bd408ae.json)
- C：`7524f354c860fa59d9876e61`，终止 `timeout_model`，耗时 120.4 秒；9.7s search(完成)；22.0s search(完成)；33.2s search(完成)；42.7s read_document(完成)；72.9s search(完成)；95.2s read_document(完成)。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/7524f354c860fa59d9876e61.json)

### C/B 成功/成功

任务 `dev-table-00`；模式 `fast_to_slow`；重复 `0`。
- B：`2a735712560e815e8f003c72`，终止 `submitted`，耗时 92.3 秒；11.1s lookup_rows(完成)；20.1s lookup_rows(完成)；30.7s lookup_rows(完成)；41.2s lookup_rows(完成)；65.6s lookup_rows(完成)；92.3s 有效提交。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/2a735712560e815e8f003c72.json)
- C：`90135fd4fc4ee27ede0a7b6c`，终止 `submitted`，耗时 94.5 秒；11.2s lookup_rows(完成)；22.8s lookup_rows(完成)；33.9s lookup_rows(完成)；44.0s lookup_rows(完成)；65.7s lookup_rows(完成)；94.5s 有效提交。 [完整轨迹](E:/Programs/codex/time/runs/v3-pilot-20261029T142119806339Z/episodes/90135fd4fc4ee27ede0a7b6c.json)

## 局限

- 单一模型、开发集、小样本及可能尚未完成的批次；结果不能推广或作为 C 对 B 的正式比较。
- CLI 自带指令及工具与其他模型接口不同；当前措施不足以证明操作系统级文件/网络隔离。
- 每次决策启动 CLI 进程，启动及推理时间计入预算；token 和费用字段若未知为 null。
- 任务模板的信息结构与行、证据 ID 规律存在局限，变化点前完成的任务不应排除。
- 并发预校准样本可能相关，人工复核与冻结配置尚未完成。
- 无正式配对 bootstrap、假设检验或效果结论。

本环境未检测到 matplotlib；本报告不生成图。上述表格保留原始分母。
