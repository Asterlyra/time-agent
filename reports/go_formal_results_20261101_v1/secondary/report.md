# 次要指标与轨迹分析

完整冻结正式矩阵的次要描述性分析。

批次 `go-formal-20261031T041031911245Z`，完整 1080 次。主比较及其区间另见主报告。此处不作额外显著性宣称。

| 模型 | 模式 | C−B | C−A | B−A |
|---|---|---:|---:|---:|
| deepseek-v4.1-flash | stable_fast | +5.00 | +2.50 | -2.50 |
| deepseek-v4.1-flash | fast_to_slow | +0.00 | +7.50 | +7.50 |
| deepseek-v4.1-flash | slow_to_fast | +0.00 | -2.50 | -2.50 |
| glm-5.3-flash | stable_fast | -2.50 | +0.00 | +2.50 |
| glm-5.3-flash | fast_to_slow | +0.00 | +0.00 | +0.00 |
| glm-5.3-flash | slow_to_fast | +7.50 | -2.50 | -10.00 |
| qwen3.8-flash | stable_fast | -2.50 | -2.50 | +0.00 |
| qwen3.8-flash | fast_to_slow | +2.50 | +5.00 | +2.50 |
| qwen3.8-flash | slow_to_fast | +0.00 | -15.00 | -15.00 |

差值单位为百分点；所有 endpoint 差值包含完整清单，不只选已暴露或成功的任务。

## 错误、时间与暴露

| 模型 | 模式 | 条件 | 错误分类 | 请求中位耗时 | 工具中位耗时 | 暴露/有效后续动作 |
|---|---|---|---|---:|---:|---:|
| deepseek-v4.1-flash | stable_fast | A | {'correct': 39, 'environment_interruption': 1} | 20.40 | 11.01 | 40/39 |
| deepseek-v4.1-flash | stable_fast | B | {'correct': 38, 'value_only_error': 1, 'environment_interruption': 1} | 20.02 | 10.01 | 39/39 |
| deepseek-v4.1-flash | stable_fast | C | {'correct': 40} | 20.67 | 12.01 | 40/40 |
| deepseek-v4.1-flash | fast_to_slow | A | {'correct': 36, 'evidence_only_error': 2, 'timeout_model': 1, 'value_and_evidence_error': 1} | 20.28 | 51.01 | 39/39 |
| deepseek-v4.1-flash | fast_to_slow | B | {'correct': 39, 'evidence_only_error': 1} | 20.75 | 50.01 | 40/40 |
| deepseek-v4.1-flash | fast_to_slow | C | {'correct': 39, 'evidence_only_error': 1} | 20.04 | 50.01 | 40/40 |
| deepseek-v4.1-flash | slow_to_fast | A | {'correct': 39, 'evidence_only_error': 1} | 20.41 | 24.01 | 40/40 |
| deepseek-v4.1-flash | slow_to_fast | B | {'correct': 38, 'value_and_evidence_error': 1, 'evidence_only_error': 1} | 22.03 | 24.01 | 39/39 |
| deepseek-v4.1-flash | slow_to_fast | C | {'correct': 38, 'value_and_evidence_error': 1, 'step_limit': 1} | 21.26 | 23.01 | 39/39 |
| glm-5.3-flash | stable_fast | A | {'correct': 37, 'evidence_only_error': 3} | 19.77 | 12.01 | 40/40 |
| glm-5.3-flash | stable_fast | B | {'correct': 38, 'environment_interruption': 1, 'evidence_only_error': 1} | 20.56 | 12.01 | 39/39 |
| glm-5.3-flash | stable_fast | C | {'correct': 37, 'evidence_only_error': 3} | 19.84 | 12.01 | 40/40 |
| glm-5.3-flash | fast_to_slow | A | {'correct': 37, 'value_and_evidence_error': 1, 'evidence_only_error': 2} | 18.59 | 51.01 | 39/39 |
| glm-5.3-flash | fast_to_slow | B | {'correct': 37, 'evidence_only_error': 2, 'environment_interruption': 1} | 20.81 | 51.01 | 40/40 |
| glm-5.3-flash | fast_to_slow | C | {'correct': 37, 'evidence_only_error': 2, 'value_and_evidence_error': 1} | 21.45 | 51.01 | 40/40 |
| glm-5.3-flash | slow_to_fast | A | {'correct': 38, 'evidence_only_error': 2} | 19.72 | 25.01 | 40/40 |
| glm-5.3-flash | slow_to_fast | B | {'correct': 34, 'evidence_only_error': 4, 'value_and_evidence_error': 2} | 22.92 | 25.01 | 40/40 |
| glm-5.3-flash | slow_to_fast | C | {'evidence_only_error': 2, 'correct': 37, 'value_and_evidence_error': 1} | 23.14 | 25.01 | 40/40 |
| qwen3.8-flash | stable_fast | A | {'timeout_model': 5, 'correct': 35} | 72.36 | 12.01 | 40/40 |
| qwen3.8-flash | stable_fast | B | {'correct': 35, 'timeout_model': 5} | 76.69 | 12.01 | 40/40 |
| qwen3.8-flash | stable_fast | C | {'timeout_model': 6, 'correct': 34} | 70.74 | 12.01 | 40/40 |
| qwen3.8-flash | fast_to_slow | A | {'timeout_model': 22, 'correct': 13, 'timeout_tool': 5} | 88.98 | 59.73 | 40/39 |
| qwen3.8-flash | fast_to_slow | B | {'timeout_model': 20, 'correct': 14, 'timeout_tool': 6} | 87.02 | 61.01 | 40/39 |
| qwen3.8-flash | fast_to_slow | C | {'correct': 15, 'timeout_model': 20, 'timeout_tool': 3, 'environment_interruption': 2} | 84.81 | 60.18 | 40/35 |
| qwen3.8-flash | slow_to_fast | A | {'correct': 30, 'timeout_model': 8, 'environment_interruption': 2} | 91.00 | 17.00 | 38/38 |
| qwen3.8-flash | slow_to_fast | B | {'timeout_model': 14, 'correct': 24, 'environment_interruption': 2} | 100.72 | 12.01 | 40/37 |
| qwen3.8-flash | slow_to_fast | C | {'timeout_model': 16, 'correct': 24} | 107.49 | 13.01 | 40/38 |

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
