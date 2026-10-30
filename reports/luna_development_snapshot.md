# Luna 开发批次描述性报告

生成时间（UTC）：2026-10-29T08:31:31.930129+00:00
批次：`runs/development-20261029T080700025321Z`；模型：`gpt-6-luna`。

**仅为探索性开发数据，不是冻结后的正式实验，也不能用于推断条件效果。**

计划 72 条，已启动 9 条，已有结果 9 条，已启动未完成 0 条，尚未启动 63 条。
有结果但缺少启动标记：0 条。分析脚本的未完成数 63 包含已启动未完成和未启动。

每行成功率的分母是该行**已有结果**的 episode，未启动或尚未结束的不在该分母中。未完成批次的不同条件分母和任务可能不平衡。

| 延迟模式 | 条件 | 任务类 | 计划 | 已启动 | 已有结果 | 截止前正确 |
|---|---|---|---:|---:|---:|---:|
| fast_to_slow | A | evidence | 4 | 0 | 0 | 0/0 (—) |
| fast_to_slow | A | table | 4 | 0 | 0 | 0/0 (—) |
| fast_to_slow | B | evidence | 4 | 0 | 0 | 0/0 (—) |
| fast_to_slow | B | table | 4 | 0 | 0 | 0/0 (—) |
| fast_to_slow | C | evidence | 4 | 0 | 0 | 0/0 (—) |
| fast_to_slow | C | table | 4 | 0 | 0 | 0/0 (—) |
| slow_to_fast | A | evidence | 4 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | A | table | 4 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | B | evidence | 4 | 1 | 1 | 1/1 (100.0%) |
| slow_to_fast | B | table | 4 | 1 | 1 | 0/1 (0.0%) |
| slow_to_fast | C | evidence | 4 | 1 | 1 | 0/1 (0.0%) |
| slow_to_fast | C | table | 4 | 1 | 1 | 1/1 (100.0%) |
| stable_fast | A | evidence | 4 | 0 | 0 | 0/0 (—) |
| stable_fast | A | table | 4 | 1 | 1 | 1/1 (100.0%) |
| stable_fast | B | evidence | 4 | 0 | 0 | 0/0 (—) |
| stable_fast | B | table | 4 | 1 | 1 | 0/1 (0.0%) |
| stable_fast | C | evidence | 4 | 0 | 0 | 0/0 (—) |
| stable_fast | C | table | 4 | 1 | 1 | 0/1 (0.0%) |

## 终止原因

| 原因 | 数量 | 分母 |
|---|---:|---:|
| protocol_violation | 2 | 9 |
| submitted | 6 | 9 |
| timeout_model | 1 | 9 |

## 延迟变化可观察性

“观察变化”表示在变化点后开始的一次工具调用已完成并返回；“之后有决策”要求随后发出过模型请求。稳定快模式没有变化，记为不适用。该子集由模型行为决定，仅供描述。

| 延迟模式 | 条件 | 任务类 | 已有结果 | 观察变化 | 观察后有决策 |
|---|---|---|---:|---:|---:|
| fast_to_slow | A | evidence | 0 | 0 | 0 |
| fast_to_slow | A | table | 0 | 0 | 0 |
| fast_to_slow | B | evidence | 0 | 0 | 0 |
| fast_to_slow | B | table | 0 | 0 | 0 |
| fast_to_slow | C | evidence | 0 | 0 | 0 |
| fast_to_slow | C | table | 0 | 0 | 0 |
| slow_to_fast | A | evidence | 1 | 1 | 1 |
| slow_to_fast | A | table | 1 | 0 | 0 |
| slow_to_fast | B | evidence | 1 | 1 | 1 |
| slow_to_fast | B | table | 1 | 0 | 0 |
| slow_to_fast | C | evidence | 1 | 1 | 1 |
| slow_to_fast | C | table | 1 | 0 | 0 |
| stable_fast | A | evidence | 0 | — | — |
| stable_fast | A | table | 1 | — | — |
| stable_fast | B | evidence | 0 | — | — |
| stable_fast | B | table | 1 | — | — |
| stable_fast | C | evidence | 0 | — | — |
| stable_fast | C | table | 1 | — | — |

## 代表轨迹

本报告使用的选择规则（未在运行前预注册）：在相同模型、任务、延迟模式及重复编号的完整 B/C 配对中，按任务及配对键排序；每种 C/B 成败组合取第一组。不存在时明确标注。失败包含所有非成功终止，不能推断其原因相同。

### C/B 成功/失败

任务 `dev-table-00`；模式 `slow_to_fast`；重复 `0`。
- B：`66fae299ec1284ef950a99f8`，终止 `submitted`，耗时 46.9 秒；4.6s lookup_rows(完成)；26.5s lookup_rows(完成)；46.9s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/66fae299ec1284ef950a99f8.json)
- C：`6ed8221e5bc61f3e8e887afe`，终止 `submitted`，耗时 55.2 秒；5.9s lookup_rows(完成)；31.9s lookup_rows(完成)；55.2s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/6ed8221e5bc61f3e8e887afe.json)

### C/B 失败/成功

任务 `dev-evidence-03`；模式 `slow_to_fast`；重复 `0`。
- B：`77aa1e6a211d1b51b307a914`，终止 `submitted`，耗时 94.2 秒；4.3s search(完成)；28.7s search(完成)；48.7s read_document(完成)；69.3s read_document(完成)；76.5s search(完成)；85.7s read_document(完成)；94.2s 提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/77aa1e6a211d1b51b307a914.json)
- C：`3cd52486f2ef4ef6c57c7426`，终止 `timeout_model`，耗时 120.4 秒；6.9s search(完成)；31.4s search(完成)；51.8s search(完成)；73.3s read_document(完成)；80.2s search(完成)；87.5s read_document(完成)。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/3cd52486f2ef4ef6c57c7426.json)

### C/B 失败/失败

任务 `dev-table-03`；模式 `stable_fast`；重复 `0`。
- B：`03af10810c2cea4c1cf19d1a`，终止 `protocol_violation`，耗时 5.3 秒；无已记录工具或提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/03af10810c2cea4c1cf19d1a.json)
- C：`6e17b2cac9e601df12214f5a`，终止 `protocol_violation`，耗时 6.2 秒；无已记录工具或提交。 [完整轨迹](E:/Programs/codex/time/runs/development-20261029T080700025321Z/episodes/6e17b2cac9e601df12214f5a.json)

### C/B 成功/成功

当前快照没有符合条件的完整配对。

## 局限

- 单一模型、开发集、小样本及可能尚未完成的批次；结果不能推广或作为 C 对 B 的正式比较。
- CLI 自带指令及工具与其他模型接口不同；当前措施不足以证明操作系统级文件/网络隔离。
- 每次决策启动 CLI 进程，启动及推理时间计入预算；token 和费用字段若未知为 null。
- 任务模板的信息结构与行、证据 ID 规律存在局限，变化点前完成的任务不应排除。
- 并发预校准样本可能相关，人工复核与冻结配置尚未完成。
- 无正式配对 bootstrap、假设检验或效果结论。

本环境未检测到 matplotlib；本报告不生成图。上述表格保留原始分母。
