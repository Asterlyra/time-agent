# S1 formal batch summary

episodes 1080, success 902

| model | profile | cond | n | success | mean elapsed | mean remaining |
|---|---|---|---:|---:|---:|---:|
| glm-5.3-flash | stable_fast | A | 40 | 37 | 34.7 | 115.3 |
| glm-5.3-flash | stable_fast | B | 40 | 38 | 49.0 | 101.0 |
| glm-5.3-flash | stable_fast | C | 40 | 37 | 34.7 | 115.3 |
| glm-5.3-flash | fast_to_slow | A | 40 | 37 | 76.5 | 73.5 |
| glm-5.3-flash | fast_to_slow | B | 40 | 37 | 93.2 | 56.8 |
| glm-5.3-flash | fast_to_slow | C | 40 | 37 | 83.4 | 66.6 |
| glm-5.3-flash | slow_to_fast | A | 40 | 38 | 46.9 | 103.1 |
| glm-5.3-flash | slow_to_fast | B | 40 | 34 | 50.9 | 99.1 |
| glm-5.3-flash | slow_to_fast | C | 40 | 37 | 50.3 | 99.7 |
| qwen3.8-flash | stable_fast | A | 40 | 35 | 98.2 | 51.8 |
| qwen3.8-flash | stable_fast | B | 40 | 35 | 98.0 | 52.0 |
| qwen3.8-flash | stable_fast | C | 40 | 34 | 96.4 | 53.6 |
| qwen3.8-flash | fast_to_slow | A | 40 | 13 | 144.4 | 5.6 |
| qwen3.8-flash | fast_to_slow | B | 40 | 14 | 143.7 | 6.3 |
| qwen3.8-flash | fast_to_slow | C | 40 | 15 | 182.2 | -32.2 |
| qwen3.8-flash | slow_to_fast | A | 40 | 30 | 138.0 | 12.0 |
| qwen3.8-flash | slow_to_fast | B | 40 | 24 | 153.9 | -3.9 |
| qwen3.8-flash | slow_to_fast | C | 40 | 24 | 116.6 | 33.4 |
| deepseek-v4.1-flash | stable_fast | A | 40 | 39 | 48.0 | 102.0 |
| deepseek-v4.1-flash | stable_fast | B | 40 | 38 | 44.8 | 105.2 |
| deepseek-v4.1-flash | stable_fast | C | 40 | 40 | 31.7 | 118.3 |
| deepseek-v4.1-flash | fast_to_slow | A | 40 | 36 | 70.9 | 79.1 |
| deepseek-v4.1-flash | fast_to_slow | B | 40 | 39 | 73.7 | 76.3 |
| deepseek-v4.1-flash | fast_to_slow | C | 40 | 39 | 68.7 | 81.3 |
| deepseek-v4.1-flash | slow_to_fast | A | 40 | 39 | 44.1 | 105.9 |
| deepseek-v4.1-flash | slow_to_fast | B | 40 | 38 | 44.6 | 105.4 |
| deepseek-v4.1-flash | slow_to_fast | C | 40 | 38 | 46.1 | 103.9 |

## request wall time (s)

- glm-5.3-flash: n=2411 median=2.81 p90=5.96
- qwen3.8-flash: n=2261 median=11.02 p90=29.53
- deepseek-v4.1-flash: n=2212 median=3.16 p90=5.23
