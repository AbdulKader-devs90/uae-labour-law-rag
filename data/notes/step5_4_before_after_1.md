# Cell 5.4 — Before and after re-ranking

## What this code does
It compares the top 3 of hybrid search with the top 3 after re-ranking, for the 5 test questions.

## Our result
| Question | Hybrid top 3 | After re-rank (score) |
|---|---|---|
| Annual leave | 29, 29, regs 18 | 29 (0.99), regs 18 (0.87), 29 (0.84) ✅ |
| Article 51 | **amendment 1**, 51, regs 38 | **51 (0.87)**, 51 (0.74), regs 29 (0.54) ✅ |
| Salary not paid | 9, 30, 40 | 9 (0.54), 47 (0.15), 30 (0.12) ❌ |
| Gratuity | 51, 51, 52 | 51 (1.00), 51 (1.00), 52 (0.99) ✅ |
| Share personal data | pdpl 22, 5, 7 | pdpl 23 (0.83) "Cross-Border Transfer and **Sharing**", 22, 1 ✅ |

The re-ranker also gives a **useful score**: high when sure, very low when not. Step 5.5 uses it.
