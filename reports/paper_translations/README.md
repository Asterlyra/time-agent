# 实验相关参考论文中文翻译

本目录翻译《Agent 工具延迟变化与时间预算适应》实验中明确引用的三篇近邻论文。翻译用于中文阅读与研究定位，**不能替代原文**；引用、参数和结论核对请以 arXiv 原文及作者代码为准。

## 文件清单

| 顺序 | 论文 | 中文译文 | 原文 |
|---|---|---|---|
| 1 | *On the Clock: Towards Punctual and Productive Time-Budgeted AI Agents* | [01_On_the_Clock_中文翻译.md](01_On_the_Clock_中文翻译.md) | <https://arxiv.org/html/2610.10833> |
| 2 | *Timely Machine: Awareness of Time Makes Test-Time Scaling Agentic* | [02_Timely_Machine_中文翻译.md](02_Timely_Machine_中文翻译.md) | <https://arxiv.org/html/2601.16486> |
| 3 | *Calibrate-Then-Act: Cost-Aware Exploration in LLM Agents* | [03_Calibrate_Then_Act_中文翻译.md](03_Calibrate_Then_Act_中文翻译.md) | <https://arxiv.org/html/2602.16699v3> |

另有便于检索和分发的合集：[三篇参考论文_中文翻译合集.md](三篇参考论文_中文翻译合集.md)。

面向初读论文读者的长篇导读：[三篇论文_入门详解.md](三篇论文_入门详解.md)。该文从 Agent 时间、测试时扩展、RL 和评估指标讲起，再逐篇解释问题、方法、结果、局限及其与本实验的关系。

## 三篇论文与实验的关系

| 论文 | 与实验直接相关的内容 | 对本实验的约束 |
|---|---|---|
| **On the Clock** | 把时间预算表现拆成“遵守预算”与“有效利用时间”；比较提示词、运行框架反馈/执行和 GRPO 训练 | 不能把“给 Agent 加时间反馈”“按时不等于高质量”当作本实验的独创发现；本实验应同时报告超时、错误提交和任务质量 |
| **Timely Machine** | 工具延迟使测试时不能只用生成长度定义；在低频/高频工具、不同延迟和预算下评估；提出 Timely-Eval/Timely-RL | 不能把“工具延迟影响策略”或“让 Agent 感知时间”本身当作全新主张；本实验的增量应放在同一任务内延迟切换、固定参考 vs 近期参考的比较上 |
| **Calibrate-Then-Act** | 将成本感知探索形式化为不确定性下的序贯决策；把推断先验显式提供给 Agent，比较提示和 RL | 本实验的近期耗时统计只是观察数据摘要，不应称为首次提供成本先验或首次让 Agent 感知环境成本 |

## 翻译范围与阅读提示

- **摘要与正文**：三篇均完整翻译。
- **附录**：说明性附录翻译；完整提示词模板、代码、案例对话截图和 NeurIPS 检查表保留原文或仅译标题，以免改变可复现协议。
- **公式**：使用 LaTeX 记号；表格数字、模型名和指标名保留原意。
- **引文**：正文中的 `[n]` 保持原文编号，参考文献列表请查原文。
- **术语**：`harness` 译作“运行框架/框架”，`adherence` 译作“遵守（预算）”，`productive use` 译作“有效利用”，`discount factor` 译作“折扣因子”，`commit` 译作“提交”，`Pandora's Box` 译作“潘多拉魔盒”。

## 生成说明

三份译文由 AI 辅助生成并经结构检查。若将译文用于论文相关工作章节，请回到原文核对数值、引用与断句；尤其是各论文的具体模型版本、预算单位、统计口径和提示词，不应从译文转引。
