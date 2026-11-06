# 次要指标与轨迹分析

开发描述性预览。

批次 `go-development-20261030T131526625261Z`，完整 216 次。主比较及其区间另见主报告。此处不作额外显著性宣称。

| 模型 | 模式 | C−B | C−A | B−A |
|---|---|---:|---:|---:|
| deepseek-v4.1-flash | stable_fast | +0.00 | +0.00 | +0.00 |
| deepseek-v4.1-flash | fast_to_slow | +0.00 | +0.00 | +0.00 |
| deepseek-v4.1-flash | slow_to_fast | +0.00 | +0.00 | +0.00 |
| glm-5.3-flash | stable_fast | +0.00 | +0.00 | +0.00 |
| glm-5.3-flash | fast_to_slow | -12.50 | +12.50 | +25.00 |
| glm-5.3-flash | slow_to_fast | +0.00 | +25.00 | +25.00 |
| qwen3.8-flash | stable_fast | -12.50 | +0.00 | +12.50 |
| qwen3.8-flash | fast_to_slow | +0.00 | +0.00 | +0.00 |
| qwen3.8-flash | slow_to_fast | +0.00 | -12.50 | -12.50 |

差值单位为百分点；所有 endpoint 差值包含完整清单，不只选已暴露或成功的任务。

## 错误、时间与暴露

| 模型 | 模式 | 条件 | 错误分类 | 请求中位耗时 | 工具中位耗时 | 暴露/有效后续动作 |
|---|---|---|---|---:|---:|---:|
| deepseek-v4.1-flash | stable_fast | A | {'correct': 8} | 32.07 | 10.01 | 8/8 |
| deepseek-v4.1-flash | stable_fast | B | {'correct': 8} | 22.37 | 10.01 | 8/8 |
| deepseek-v4.1-flash | stable_fast | C | {'correct': 8} | 27.21 | 11.01 | 8/8 |
| deepseek-v4.1-flash | fast_to_slow | A | {'correct': 8} | 29.15 | 55.51 | 8/8 |
| deepseek-v4.1-flash | fast_to_slow | B | {'correct': 8} | 26.71 | 49.01 | 8/8 |
| deepseek-v4.1-flash | fast_to_slow | C | {'correct': 8} | 28.72 | 55.51 | 8/8 |
| deepseek-v4.1-flash | slow_to_fast | A | {'correct': 8} | 27.52 | 23.01 | 8/8 |
| deepseek-v4.1-flash | slow_to_fast | B | {'correct': 8} | 30.04 | 23.01 | 8/8 |
| deepseek-v4.1-flash | slow_to_fast | C | {'correct': 8} | 35.40 | 24.01 | 8/8 |
| glm-5.3-flash | stable_fast | A | {'correct': 6, 'evidence_only_error': 1, 'value_and_evidence_error': 1} | 15.30 | 11.00 | 8/8 |
| glm-5.3-flash | stable_fast | B | {'correct': 6, 'value_and_evidence_error': 2} | 14.73 | 12.01 | 8/8 |
| glm-5.3-flash | stable_fast | C | {'evidence_only_error': 2, 'correct': 6} | 14.26 | 12.01 | 8/8 |
| glm-5.3-flash | fast_to_slow | A | {'correct': 4, 'evidence_only_error': 2, 'value_only_error': 2} | 18.01 | 51.01 | 8/8 |
| glm-5.3-flash | fast_to_slow | B | {'evidence_only_error': 2, 'correct': 6} | 20.11 | 51.01 | 8/8 |
| glm-5.3-flash | fast_to_slow | C | {'evidence_only_error': 2, 'value_only_error': 1, 'correct': 5} | 18.22 | 51.01 | 8/8 |
| glm-5.3-flash | slow_to_fast | A | {'value_only_error': 1, 'evidence_only_error': 2, 'correct': 4, 'value_and_evidence_error': 1} | 17.32 | 23.01 | 8/8 |
| glm-5.3-flash | slow_to_fast | B | {'correct': 6, 'evidence_only_error': 1, 'value_and_evidence_error': 1} | 15.16 | 25.01 | 8/8 |
| glm-5.3-flash | slow_to_fast | C | {'correct': 6, 'value_and_evidence_error': 1, 'evidence_only_error': 1} | 15.21 | 21.00 | 8/8 |
| qwen3.8-flash | stable_fast | A | {'correct': 6, 'timeout_model': 2} | 61.84 | 11.01 | 8/8 |
| qwen3.8-flash | stable_fast | B | {'correct': 7, 'timeout_model': 1} | 58.80 | 12.01 | 8/8 |
| qwen3.8-flash | stable_fast | C | {'timeout_model': 2, 'correct': 6} | 71.57 | 12.01 | 8/8 |
| qwen3.8-flash | fast_to_slow | A | {'timeout_model': 3, 'correct': 4, 'timeout_tool': 1} | 89.70 | 55.51 | 8/8 |
| qwen3.8-flash | fast_to_slow | B | {'timeout_model': 4, 'correct': 4} | 110.10 | 62.01 | 8/8 |
| qwen3.8-flash | fast_to_slow | C | {'timeout_model': 3, 'correct': 4, 'timeout_tool': 1} | 95.16 | 55.51 | 8/7 |
| qwen3.8-flash | slow_to_fast | A | {'correct': 7, 'timeout_model': 1} | 76.99 | 25.01 | 8/7 |
| qwen3.8-flash | slow_to_fast | B | {'correct': 6, 'timeout_model': 2} | 78.19 | 12.01 | 8/8 |
| qwen3.8-flash | slow_to_fast | C | {'correct': 6, 'timeout_model': 2} | 118.53 | 12.01 | 8/8 |

时间单位为每 episode 秒数，请求跨度含重试等待；详细分位数、删失、token、缓存和已知额度见 summary.json。

## 参考误差与后续动作

参考误差仅使用下一次同类完整工具耗时；删失数单列。它反映摘要统计器的滞后，不能解释为模型预测能力。变化反馈后的动作与证据可用性只作条件性描述，不能替代全样本主结果。

[参考误差](reference_errors.json) · [后续动作与来源覆盖](post_feedback_actions.json) · [各类错误的排序首例](error_examples.json)

## 限制

- No secondary confidence intervals or multiplicity-adjusted claims.
- Post-feedback subsets and completed-duration subsets are behavior-dependent descriptive samples.
- Full source IDs read is a necessary evidence-availability proxy, not proof of reasoning or sufficiency.
- Request spans include retry/backoff and network/provider/client time; censored spans are separate.
- Reported token/cost counters are not filled as actual zero where missing.
