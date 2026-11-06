# 固定公开上下文机制探针

计划 144 次单步采样，完成 144 次。三个模型使用相同的八个公开前缀和 60 秒剩余时间，只改变 A/B/C 摘要。

工具调用少或 tool_new 不能直接认定更好；提交正确也不能证明完整任务适应。没有将探针样本并入主实验。

| 模型 | 条件 | 完成 | 行动类别 |
|---|---|---:|---|
| glm-5.3-flash | A | 16 | {'tool_new': 14, 'submit_incorrect': 1, 'submit_correct': 1} |
| glm-5.3-flash | B | 16 | {'tool_new': 14, 'submit_incorrect': 2} |
| glm-5.3-flash | C | 16 | {'tool_new': 13, 'invalid': 1, 'submit_incorrect': 2} |
| qwen3.8-flash | A | 16 | {'submit_correct': 1, 'invalid': 3, 'tool_new': 12} |
| qwen3.8-flash | B | 16 | {'tool_new': 13, 'invalid': 2, 'submit_correct': 1} |
| qwen3.8-flash | C | 16 | {'submit_correct': 2, 'invalid': 2, 'tool_new': 12} |
| deepseek-v4.1-flash | A | 16 | {'tool_new': 14, 'submit_correct': 2} |
| deepseek-v4.1-flash | B | 16 | {'tool_new': 14, 'submit_correct': 2} |
| deepseek-v4.1-flash | C | 16 | {'tool_new': 14, 'submit_correct': 2} |
