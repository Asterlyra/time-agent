| Profile | Model | A | B | C | O |
|---|---|---:|---:|---:|---:|
| constant 8 s | GLM | — | — | — | — |
| constant 8 s | Qwen | — | — | — | — |
| constant 8 s | DeepSeek | — | — | — | — |
| step 8->60 s | GLM | 8.0 | 0.0 | 0.0 | 11.0 |
| step 8->60 s | Qwen | 0.0 | 5.0 | 0.0 | 1.0 |
| step 8->60 s | DeepSeek | 9.0 | 0.0 | 7.0 | 7.0 |
| drift 8->60 s | GLM | — | — | — | — |
| drift 8->60 s | Qwen | — | — | — | — |
| drift 8->60 s | DeepSeek | — | — | — | — |

| Profile | Contrast | Pooled | 95% CI | p (sign-flip) | per model (GLM / Qwen / DS) |
|---|---|---:|---|---:|---|
| step 8->60 s | C-B | +0.7 | [+0.7, +0.7] | 1.000 | +0.0 / -5.0 / +7.0 |
| step 8->60 s | B-A | -4.0 | [-4.0, -4.0] | 1.000 | -8.0 / +5.0 / -9.0 |
| step 8->60 s | O-C | +4.0 | [+4.0, +4.0] | 1.000 | +11.0 / +1.0 / +0.0 |

| Profile | Cond | submitted | mean last-fetch remaining (s) | mean fetches |
|---|---|---:|---:|---:|
| step 8->60 s | A | 0.67 | 90.1 | 7.3 |
| step 8->60 s | B | 0.33 | 80.8 | 7.0 |
| step 8->60 s | C | 0.33 | 60.3 | 7.3 |
| step 8->60 s | O | 1.00 | 126.2 | 6.3 |
