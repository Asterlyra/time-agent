# 固定上下文探针：按实际工具请求汇总

完整采样 144/144；来源 `go-probe-20261031T045206576627Z`。

重复请求按工具名及完全相同 arguments 判断，忽略宿主不用的额外顶层字段。原始动作、原始分类、超时与失败均保留。不同参数但等价的查询不自动算重复。

相较原始完整 JSON 对象分类，重分类 0 次；只修描述标签，没有改模型输入、原始答案或进行重新采样。

| 模型 | 条件 | 完成 | 请求分类 | 新必要事实 | 新导航 ID |
|---|---|---:|---|---:|---:|
| glm-5.3-flash | A | 16 | {'tool_new': 14, 'submit_correct': 1, 'submit_incorrect': 1} | 12 | 2 |
| glm-5.3-flash | B | 16 | {'tool_new': 14, 'submit_incorrect': 2} | 11 | 3 |
| glm-5.3-flash | C | 16 | {'tool_new': 13, 'submit_incorrect': 2, 'invalid': 1} | 10 | 2 |
| qwen3.8-flash | A | 16 | {'submit_correct': 1, 'tool_new': 12, 'invalid': 3} | 8 | 4 |
| qwen3.8-flash | B | 16 | {'invalid': 2, 'tool_new': 13, 'submit_correct': 1} | 10 | 3 |
| qwen3.8-flash | C | 16 | {'submit_correct': 2, 'invalid': 2, 'tool_new': 12} | 8 | 4 |
| deepseek-v4.1-flash | A | 16 | {'tool_new': 14, 'submit_correct': 2} | 12 | 2 |
| deepseek-v4.1-flash | B | 16 | {'tool_new': 14, 'submit_correct': 2} | 12 | 2 |
| deepseek-v4.1-flash | C | 16 | {'tool_new': 14, 'submit_correct': 2} | 11 | 3 |

这些是单步描述性计数，不能把少调用、新调用、重复调用或正确提交自动认定为更优策略，也不并入 1080 次主实验。两次重复不能支撑普遍机制或显著性宣称。

[分类明细及原始标签](sample_categories.json) · [汇总及方法边界](summary.json)
